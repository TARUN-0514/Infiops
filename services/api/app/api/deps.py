import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.crypto import Encryptor
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User, UserSession

DB = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(auto_error=False)


def get_encryptor(settings: SettingsDep) -> Encryptor:
    return Encryptor(settings.encryption_key.get_secret_value())


EncryptorDep = Annotated[Encryptor, Depends(get_encryptor)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _unauthorized(message: str = "Sign in to continue.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


class CurrentAuth:
    def __init__(self, user: User, session: UserSession) -> None:
        self.user, self.session = user, session


async def current_auth(
    db: DB,
    settings: SettingsDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentAuth:
    if creds is None:
        raise _unauthorized()
    try:
        payload = decode_access_token(creds.credentials, settings.jwt_secret.get_secret_value())
        user_id, session_id = uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized() from None
    session = await db.get(UserSession, session_id)
    if session is None or session.revoked_at is not None or session.expires_at <= datetime.now(UTC):
        raise _unauthorized("Your session has ended. Sign in again.")
    user = await db.get(User, user_id)
    if user is None or not user.is_active or session.user_id != user.id:
        raise _unauthorized()
    return CurrentAuth(user, session)


Auth = Annotated[CurrentAuth, Depends(current_auth)]
