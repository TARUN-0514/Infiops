"""Authentication logic: owner registration, login with optional TOTP, session rotation."""

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import Encryptor
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    hash_token,
    needs_rehash,
    new_refresh_token,
    verify_password,
)
from app.models import User, UserPreferences, UserSession
from app.services import audit


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    session: UserSession
    expires_in: int


def _now() -> datetime:
    return datetime.now(UTC)


async def registration_open(db: AsyncSession, settings: Settings) -> bool:
    count = await db.scalar(select(func.count()).select_from(User))
    return count == 0 or settings.allow_registration_after_owner


async def register(
    db: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    display_name: str,
    timezone: str,
    ip: str | None,
) -> User:
    if not await registration_open(db, settings):
        raise AuthError("registration_closed", "Registration is closed.", 403)
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise AuthError("email_taken", "An account with this email already exists.", 409)
    count = await db.scalar(select(func.count()).select_from(User))
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        timezone=timezone,
        role="owner" if count == 0 else "member",
    )
    db.add(user)
    await db.flush()
    db.add(UserPreferences(user_id=user.id))
    audit.record(db, "auth.register", user_id=user.id, ip=ip)
    await db.commit()
    return user


def _verify_totp(user: User, code: str, enc: Encryptor) -> bool:
    if user.mfa_secret_enc is None:
        return False
    totp = pyotp.TOTP(enc.decrypt(user.mfa_secret_enc, user.id.bytes))
    now = time.time()
    for offset in (-1, 0, 1):  # allow 30 s clock drift either way
        step = int(now // 30) + offset
        if totp.at(step * 30) == code and (user.mfa_last_used_step or -1) < step:
            user.mfa_last_used_step = step
            return True
    return False


async def _issue(
    db: AsyncSession, settings: Settings, user: User, *, user_agent: str | None, ip: str | None
) -> IssuedTokens:
    refresh = new_refresh_token()
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh),
        user_agent=(user_agent or "")[:400] or None,
        ip=ip,
        last_used_at=_now(),
        expires_at=_now() + timedelta(days=settings.refresh_token_days),
    )
    db.add(session)
    await db.flush()
    access = create_access_token(
        user.id, session.id, settings.jwt_secret.get_secret_value(), settings.access_token_minutes
    )
    return IssuedTokens(access, refresh, session, settings.access_token_minutes * 60)


async def login(
    db: AsyncSession,
    settings: Settings,
    enc: Encryptor,
    *,
    email: str,
    password: str,
    totp_code: str | None,
    user_agent: str | None,
    ip: str | None,
) -> IssuedTokens:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        verify_password(DUMMY_HASH, password)  # equal timing for unknown accounts
        audit.record(db, "auth.login_failed", actor="anonymous", ip=ip, reason="bad_credentials")
        await db.commit()
        raise AuthError("invalid_credentials", "Email or password is incorrect.")
    if not verify_password(user.password_hash, password):
        audit.record(db, "auth.login_failed", user_id=user.id, ip=ip, reason="bad_credentials")
        await db.commit()
        raise AuthError("invalid_credentials", "Email or password is incorrect.")
    if user.mfa_enabled:
        if not totp_code:
            raise AuthError("mfa_required", "Enter the code from your authenticator app.")
        if not _verify_totp(user, totp_code, enc):
            audit.record(db, "auth.login_failed", user_id=user.id, ip=ip, reason="bad_totp")
            await db.commit()
            raise AuthError("invalid_mfa_code", "That code is not valid.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    tokens = await _issue(db, settings, user, user_agent=user_agent, ip=ip)
    audit.record(db, "auth.login", user_id=user.id, ip=ip, session_id=str(tokens.session.id))
    await db.commit()
    return tokens


async def refresh(
    db: AsyncSession, settings: Settings, *, refresh_token: str, ip: str | None
) -> tuple[IssuedTokens, User]:
    token_hash = hash_token(refresh_token)
    session = await db.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == token_hash).with_for_update()
    )
    if session is None:
        reused = await db.scalar(
            select(UserSession).where(UserSession.previous_token_hash == token_hash)
        )
        if reused is not None and reused.revoked_at is None:
            # An already-rotated token came back: assume theft and end that session.
            reused.revoked_at, reused.revoke_reason = _now(), "refresh_reuse"
            audit.record(
                db, "auth.refresh_reuse", user_id=reused.user_id, ip=ip, session_id=str(reused.id)
            )
            await db.commit()
        raise AuthError("invalid_refresh", "Your session has ended. Sign in again.")
    if session.revoked_at is not None or session.expires_at <= _now():
        raise AuthError("invalid_refresh", "Your session has ended. Sign in again.")
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthError("invalid_refresh", "Your session has ended. Sign in again.")
    new_refresh = new_refresh_token()
    session.previous_token_hash = token_hash
    session.refresh_token_hash = hash_token(new_refresh)
    session.last_used_at = _now()
    session.ip = ip
    access = create_access_token(
        user.id, session.id, settings.jwt_secret.get_secret_value(), settings.access_token_minutes
    )
    await db.commit()
    return IssuedTokens(access, new_refresh, session, settings.access_token_minutes * 60), user


async def revoke_session(
    db: AsyncSession, session: UserSession, reason: str, *, ip: str | None
) -> None:
    if session.revoked_at is None:
        session.revoked_at, session.revoke_reason = _now(), reason
        audit.record(
            db,
            "auth.session_revoked",
            user_id=session.user_id,
            ip=ip,
            session_id=str(session.id),
            reason=reason,
        )
    await db.commit()


def begin_mfa_setup(user: User, enc: Encryptor, issuer: str) -> tuple[str, str]:
    secret = pyotp.random_base32()
    user.mfa_pending_secret_enc = enc.encrypt(secret, user.id.bytes)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=issuer)
    return secret, uri


def confirm_mfa_setup(user: User, enc: Encryptor, code: str) -> bool:
    if user.mfa_pending_secret_enc is None:
        return False
    secret = enc.decrypt(user.mfa_pending_secret_enc, user.id.bytes)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return False
    user.mfa_secret_enc, user.mfa_pending_secret_enc = user.mfa_pending_secret_enc, None
    user.mfa_enabled = True
    user.mfa_last_used_step = int(time.time() // 30)
    return True


def disable_mfa(user: User, enc: Encryptor, code: str) -> bool:
    if not user.mfa_enabled or not _verify_totp(user, code, enc):
        return False
    user.mfa_enabled, user.mfa_secret_enc, user.mfa_last_used_step = False, None, None
    return True
