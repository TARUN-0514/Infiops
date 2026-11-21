"""Connecting, testing and disconnecting Google. A connection is marked connected only
after a real Gmail and Calendar call succeeds."""

import json
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import Encryptor
from app.integrations import google
from app.models import ConnectedAccount, IntegrationSyncLog
from app.services import audit
from app.services.redis import get_redis

STATE_TTL_SECONDS = 600


def encryptor() -> Encryptor:
    return Encryptor(get_settings().encryption_key.get_secret_value())


async def start_google(user_id: uuid.UUID) -> str:
    if not get_settings().google_ready:
        raise ValueError(
            "Google isn't set up yet. Add NEXUS_GOOGLE_CLIENT_ID and "
            "NEXUS_GOOGLE_CLIENT_SECRET to .env (see the README)."
        )
    state = secrets.token_urlsafe(32)
    verifier, challenge = google.pkce_pair()
    await get_redis().set(
        f"oauth:google:{state}",
        json.dumps({"user_id": str(user_id), "verifier": verifier}),
        ex=STATE_TTL_SECONDS,
    )
    return google.authorization_url(state, challenge)


async def finish_google(db: AsyncSession, state: str, code: str) -> ConnectedAccount:
    raw = await get_redis().getdel(f"oauth:google:{state}")
    if not raw:
        raise ValueError("This sign-in link expired. Start again from Settings.")
    saved = json.loads(raw)
    user_id = uuid.UUID(saved["user_id"])
    tokens = await google.exchange_code(code, saved["verifier"])
    granted = set(str(tokens.get("scope", "")).split())
    missing = [s for s in google.SCOPES if s.startswith("https://") and s not in granted]
    email = await google.fetch_email(tokens["access_token"])
    account = await db.scalar(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == "google",
            ConnectedAccount.account_email == email,
        )
    )
    if account is None:
        account = ConnectedAccount(user_id=user_id, provider="google", account_email=email)
        db.add(account)
        await db.flush()
    enc = encryptor()
    google.store_tokens(account, enc, tokens)
    if missing:
        account.status = "error"
        account.last_error = (
            "Some permissions weren't granted: "
            + ", ".join(google.SCOPE_LABELS.get(s, s) for s in missing)
            + ". Connect again and tick every box."
        )
    else:
        await test_account(account)
    audit.record(
        db, "integration.connected", user_id=user_id, target=str(account.id), provider="google"
    )
    return account


async def test_account(account: ConnectedAccount) -> bool:
    try:
        await google.GoogleClient(account, encryptor()).test()
    except google.GoogleError as exc:
        account.status, account.last_error = "error", str(exc)
        return False
    account.status, account.last_error = "connected", None
    account.last_test_at = datetime.now(UTC)
    return True


async def list_accounts(db: AsyncSession, user_id: uuid.UUID) -> list[ConnectedAccount]:
    rows = await db.scalars(
        select(ConnectedAccount)
        .where(ConnectedAccount.user_id == user_id)
        .order_by(ConnectedAccount.created_at)
    )
    return list(rows)


async def get_owned(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> ConnectedAccount:
    acc = await db.get(ConnectedAccount, account_id)
    if acc is None or acc.user_id != user_id:
        raise LookupError("Account not found.")
    return acc


async def google_account(db: AsyncSession, user_id: uuid.UUID) -> ConnectedAccount | None:
    """The owner's connected Google account, if one is working."""
    acc: ConnectedAccount | None = await db.scalar(
        select(ConnectedAccount)
        .where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == "google",
            ConnectedAccount.status == "connected",
        )
        .order_by(ConnectedAccount.created_at)
        .limit(1)
    )
    return acc


async def require_google(db: AsyncSession, user_id: uuid.UUID) -> ConnectedAccount:
    acc = await google_account(db, user_id)
    if acc is None:
        raise ValueError("Connect Google in Settings › Integrations first.")
    return acc


def client(account: ConnectedAccount) -> google.GoogleClient:
    return google.GoogleClient(account, encryptor())


async def disconnect(db: AsyncSession, account: ConnectedAccount) -> None:
    enc = encryptor()
    for blob in (account.refresh_token_enc, account.access_token_enc):
        if blob:
            try:
                await google.revoke(enc.decrypt(blob, account.id.bytes))
            except Exception:  # noqa: S110 - revoking is best effort; we delete either way
                pass
            break
    audit.record(
        db,
        "integration.disconnected",
        user_id=account.user_id,
        target=str(account.id),
        provider=account.provider,
    )
    await db.delete(account)


def start_log(db: AsyncSession, account: ConnectedAccount, kind: str) -> IntegrationSyncLog:
    entry = IntegrationSyncLog(
        user_id=account.user_id, account_id=account.id, kind=kind, started_at=datetime.now(UTC)
    )
    db.add(entry)
    return entry


def finish_log(entry: IntegrationSyncLog, items: int, error: str | None = None) -> None:
    entry.items, entry.error = items, error
    entry.status = "failed" if error else "succeeded"
    entry.finished_at = datetime.now(UTC)
