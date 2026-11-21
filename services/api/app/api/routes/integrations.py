"""Connected services (Google): connect, test, sync now and disconnect."""

import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.core.config import get_settings
from app.core.logging import log
from app.integrations import google
from app.integrations.google import GoogleError
from app.models import ConnectedAccount, IntegrationSyncLog
from app.services import integrations as integ
from app.services import jobs

router = APIRouter(prefix="/integrations", tags=["integrations"])


def account_out(a: ConnectedAccount, logs: list[IntegrationSyncLog]) -> dict[str, Any]:
    def last(kind: str) -> dict[str, Any] | None:
        entry = next((x for x in logs if x.kind == kind), None)
        if entry is None:
            return None
        return {
            "status": entry.status,
            "items": entry.items,
            "error": entry.error,
            "at": (entry.finished_at or entry.started_at).isoformat(),
        }

    return {
        "id": str(a.id),
        "provider": a.provider,
        "account_email": a.account_email,
        "status": a.status,
        "last_error": a.last_error,
        "last_test_at": a.last_test_at.isoformat() if a.last_test_at else None,
        "last_sync_at": a.last_sync_at.isoformat() if a.last_sync_at else None,
        "permissions": [google.SCOPE_LABELS[s] for s in a.scopes if s in google.SCOPE_LABELS],
        "last_sync": {"gmail": last("gmail"), "calendar": last("calendar")},
        "connected_at": a.created_at.isoformat(),
    }


async def _logs(db: DB, account_id: uuid.UUID) -> list[IntegrationSyncLog]:
    rows = await db.scalars(
        select(IntegrationSyncLog)
        .where(IntegrationSyncLog.account_id == account_id)
        .order_by(IntegrationSyncLog.started_at.desc())
        .limit(10)
    )
    return list(rows)


@router.get("")
async def list_integrations(db: DB, auth: Auth) -> dict[str, Any]:
    accounts = await integ.list_accounts(db, auth.user.id)
    return {
        "google": {
            "configured": get_settings().google_ready,
            "redirect_uri": get_settings().google_redirect_uri,
            "permissions": list(google.SCOPE_LABELS.values()),
        },
        "accounts": [account_out(a, await _logs(db, a.id)) for a in accounts],
    }


@router.post("/google/start")
async def google_start(auth: Auth) -> dict[str, str]:
    try:
        return {"url": await integ.start_google(auth.user.id)}
    except ValueError as exc:
        bad_request(str(exc), code="not_configured")


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    db: DB,
    state: str = Query(""),
    code: str = Query(""),
    error: str = Query(""),
) -> RedirectResponse:
    """Google sends the browser here. The state value identifies the owner."""
    back = f"{get_settings().public_web_url.rstrip('/')}/settings/integrations"
    if error or not code or not state:
        return RedirectResponse(f"{back}?google=cancelled", status.HTTP_303_SEE_OTHER)
    try:
        account = await integ.finish_google(db, state, code)
    except (ValueError, GoogleError) as exc:
        await db.rollback()
        log.warning("google_connect_failed", reason=str(exc))
        return RedirectResponse(f"{back}?google=failed", status.HTTP_303_SEE_OTHER)
    await db.commit()
    if account.status == "connected":
        await jobs.enqueue("sync_account", account_id=str(account.id))
        return RedirectResponse(f"{back}?google=connected", status.HTTP_303_SEE_OTHER)
    return RedirectResponse(f"{back}?google=error", status.HTTP_303_SEE_OTHER)


async def _owned(db: DB, auth: Auth, account_id: uuid.UUID) -> ConnectedAccount:
    try:
        return await integ.get_owned(db, auth.user.id, account_id)
    except LookupError:
        not_found("Account not found.")


@router.post("/{account_id}/test")
async def test(account_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    acc = await _owned(db, auth, account_id)
    await integ.test_account(acc)
    await db.commit()
    return account_out(acc, await _logs(db, acc.id))


@router.post("/{account_id}/sync")
async def sync_now(account_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    from app.worker import run_account_sync

    acc = await _owned(db, auth, account_id)
    if acc.status != "connected":
        bad_request(acc.last_error or "Reconnect this account first.", code="not_connected")
    result = await run_account_sync(db, acc)
    await db.commit()
    await db.refresh(acc)
    return {**account_out(acc, await _logs(db, acc.id)), "result": result}


@router.delete("/{account_id}", status_code=204)
async def disconnect(account_id: uuid.UUID, db: DB, auth: Auth) -> None:
    acc = await _owned(db, auth, account_id)
    await integ.disconnect(db, acc)
    await db.commit()
