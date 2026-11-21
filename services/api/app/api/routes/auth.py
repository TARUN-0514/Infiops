import secrets
import uuid

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import DB, Auth, EncryptorDep, SettingsDep, client_ip
from app.api.schemas import (
    LoginIn,
    MfaCodeIn,
    MfaSetupOut,
    RegisterIn,
    SessionOut,
    StatusOut,
    TokenOut,
    UserOut,
)
from app.core.config import Settings
from app.core.security import new_csrf_token
from app.models import User, UserSession
from app.services import audit
from app.services import auth as auth_service
from app.services.rate_limit import enforce_rate_limit, reset_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "nexus_refresh"
CSRF_COOKIE = "nexus_csrf"
COOKIE_PATH = "/api/v1/auth"


def _error(err: auth_service.AuthError) -> HTTPException:
    return HTTPException(
        status_code=err.status_code, detail={"code": err.code, "message": err.message}
    )


def _set_cookies(response: Response, settings: Settings, refresh: str, csrf: str) -> None:
    max_age = settings.refresh_token_days * 86400
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=max_age,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    # Readable by the web app so it can echo it in X-CSRF-Token (double-submit pattern).
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")


def _check_csrf(request: Request) -> None:
    cookie, header = request.cookies.get(CSRF_COOKIE), request.headers.get("X-CSRF-Token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(
            status_code=403,
            detail={"code": "csrf_failed", "message": "Security check failed. Reload the page."},
        )


@router.get("/status", response_model=StatusOut)
async def auth_status(db: DB, settings: SettingsDep) -> StatusOut:
    return StatusOut(registration_open=await auth_service.registration_open(db, settings))


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, request: Request, db: DB, settings: SettingsDep) -> User:
    ip = client_ip(request)
    await enforce_rate_limit(f"register:{ip}", 5, 3600)
    try:
        return await auth_service.register(
            db,
            settings,
            email=body.email.lower(),
            password=body.password,
            display_name=body.display_name,
            timezone=body.timezone,
            ip=ip,
        )
    except auth_service.AuthError as err:
        raise _error(err) from None


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DB,
    settings: SettingsDep,
    enc: EncryptorDep,
) -> TokenOut:
    ip, email = client_ip(request), body.email.lower()
    await enforce_rate_limit(
        f"login:ip:{ip}", settings.login_rate_limit * 3, settings.rate_limit_window_seconds
    )
    await enforce_rate_limit(
        f"login:email:{email}", settings.login_rate_limit, settings.rate_limit_window_seconds
    )
    try:
        tokens = await auth_service.login(
            db,
            settings,
            enc,
            email=email,
            password=body.password,
            totp_code=body.totp_code,
            user_agent=request.headers.get("user-agent"),
            ip=ip,
        )
    except auth_service.AuthError as err:
        raise _error(err) from None
    await reset_rate_limit(f"login:email:{email}")
    csrf = new_csrf_token()
    _set_cookies(response, settings, tokens.refresh_token, csrf)
    user = await db.get(User, tokens.session.user_id)
    return TokenOut(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        csrf_token=csrf,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, response: Response, db: DB, settings: SettingsDep) -> TokenOut:
    _check_csrf(request)
    ip = client_ip(request)
    await enforce_rate_limit(f"refresh:{ip}", 60, 60)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(401, detail={"code": "invalid_refresh", "message": "Sign in again."})
    try:
        tokens, user = await auth_service.refresh(db, settings, refresh_token=token, ip=ip)
    except auth_service.AuthError as err:
        _clear_cookies(response)
        raise _error(err) from None
    csrf = new_csrf_token()
    _set_cookies(response, settings, tokens.refresh_token, csrf)
    return TokenOut(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        csrf_token=csrf,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(auth: Auth, request: Request, response: Response, db: DB) -> None:
    await auth_service.revoke_session(db, auth.session, "logout", ip=client_ip(request))
    _clear_cookies(response)


@router.get("/me", response_model=UserOut)
async def me(auth: Auth) -> User:
    return auth.user


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(auth: Auth, db: DB) -> list[SessionOut]:
    rows = (
        await db.scalars(
            select(UserSession)
            .where(UserSession.user_id == auth.user.id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.last_used_at.desc())
        )
    ).all()
    out = []
    for row in rows:
        item = SessionOut.model_validate(row)
        item.current = row.id == auth.session.id
        out.append(item)
    return out


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: uuid.UUID, auth: Auth, request: Request, db: DB) -> None:
    session = await db.get(UserSession, session_id)
    if session is None or session.user_id != auth.user.id:
        raise HTTPException(404, detail={"code": "not_found", "message": "Session not found."})
    await auth_service.revoke_session(db, session, "user_revoked", ip=client_ip(request))


@router.post("/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(auth: Auth, db: DB, enc: EncryptorDep, settings: SettingsDep) -> MfaSetupOut:
    if auth.user.mfa_enabled:
        raise HTTPException(
            409,
            detail={"code": "mfa_already_enabled", "message": "Two-factor sign-in is already on."},
        )
    secret, uri = auth_service.begin_mfa_setup(auth.user, enc, settings.app_name)
    await db.commit()
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/enable", response_model=UserOut)
async def mfa_enable(
    body: MfaCodeIn, auth: Auth, request: Request, db: DB, enc: EncryptorDep
) -> User:
    await enforce_rate_limit(f"mfa:{auth.user.id}", 10, 300)
    if not auth_service.confirm_mfa_setup(auth.user, enc, body.code):
        raise HTTPException(
            400, detail={"code": "invalid_mfa_code", "message": "That code is not valid."}
        )
    audit.record(db, "auth.mfa_enabled", user_id=auth.user.id, ip=client_ip(request))
    await db.commit()
    return auth.user


@router.post("/mfa/disable", response_model=UserOut)
async def mfa_disable(
    body: MfaCodeIn, auth: Auth, request: Request, db: DB, enc: EncryptorDep
) -> User:
    await enforce_rate_limit(f"mfa:{auth.user.id}", 10, 300)
    if not auth_service.disable_mfa(auth.user, enc, body.code):
        raise HTTPException(
            400, detail={"code": "invalid_mfa_code", "message": "That code is not valid."}
        )
    audit.record(db, "auth.mfa_disabled", user_id=auth.user.id, ip=client_ip(request))
    await db.commit()
    return auth.user
