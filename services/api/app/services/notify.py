"""In-app notifications and Web Push. VAPID keys come from settings, or are generated
once and kept in the data folder so push works without extra setup."""

import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import log
from app.models import Notification, PushSubscription

_keys: tuple[str, str] | None = None


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_vapid() -> tuple[str, str]:
    """(public, private) as base64url: the uncompressed P-256 point and the raw scalar."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64url(public), _b64url(private)


def vapid_keys() -> tuple[str, str]:
    global _keys
    if _keys is not None:
        return _keys
    s = get_settings()
    if s.vapid_public_key and s.vapid_private_key.get_secret_value():
        _keys = (s.vapid_public_key, s.vapid_private_key.get_secret_value())
        return _keys
    path = Path(s.storage_dir).resolve().parent / "vapid.json"
    try:
        saved = json.loads(path.read_text())
        _keys = (saved["public"], saved["private"])
    except (OSError, ValueError, KeyError):
        public, private = generate_vapid()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"public": public, "private": private}))
        path.chmod(0o600)
        _keys = (public, private)
    return _keys


def _send_push(sub: PushSubscription, payload: dict[str, Any]) -> int | None:
    """Blocking send; returns an HTTP status when the push service rejected it."""
    from pywebpush import WebPushException, webpush

    _, private = vapid_keys()
    try:
        webpush(
            {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps(payload),
            vapid_private_key=private,
            vapid_claims={"sub": get_settings().vapid_subject},
            ttl=3600,
            timeout=10,
        )
    except WebPushException as exc:
        return exc.response.status_code if exc.response is not None else 0
    return None


async def push(db: AsyncSession, user_id: uuid.UUID, payload: dict[str, Any]) -> int:
    """Send to every subscribed device; drop subscriptions the browser revoked."""
    subs = list(
        await db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id))
    )
    sent = 0
    for sub in subs:
        status = await asyncio.to_thread(_send_push, sub, payload)
        if status in (404, 410):
            await db.delete(sub)
        elif status is None:
            sent += 1
        else:
            log.warning("push_failed", status=status)
    return sent


async def notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
    send_push: bool = True,
) -> Notification:
    n = Notification(user_id=user_id, kind=kind, title=title[:200], body=body, link=link)
    db.add(n)
    await db.flush()
    if send_push:
        try:
            n.pushed = (
                await push(
                    db,
                    user_id,
                    {"title": n.title, "body": body[:300], "url": link or "/", "tag": kind},
                )
                > 0
            )
        except Exception:
            log.exception("push_error")
    return n
