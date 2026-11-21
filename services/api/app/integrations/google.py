"""Google OAuth (authorization code with PKCE) and a small REST client for Gmail and
Google Calendar. Tokens are stored encrypted on the ConnectedAccount row."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.crypto import Encryptor
from app.models import ConnectedAccount

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3"

# The smallest scopes that cover triage, drafts, approved sends and calendar edits.
SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.events",
]
SCOPE_LABELS = {
    "https://www.googleapis.com/auth/gmail.readonly": "Read your email",
    "https://www.googleapis.com/auth/gmail.compose": "Write drafts and send approved emails",
    "https://www.googleapis.com/auth/calendar.events": "Read and change calendar events",
}

_transport: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Tests replace Google with a mock transport."""
    global _transport
    _transport = transport


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_transport, timeout=30)


class GoogleError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorization_url(state: str, challenge: str) -> str:
    s = get_settings()
    query = {
        "client_id": s.google_client_id,
        "redirect_uri": s.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(query)}"


async def _token_request(data: dict[str, str]) -> dict[str, Any]:
    s = get_settings()
    form = {
        **data,
        "client_id": s.google_client_id,
        "client_secret": s.google_client_secret.get_secret_value(),
    }
    async with _http() as http:
        r = await http.post(TOKEN_URL, data=form)
    if r.status_code != 200:
        try:
            err = r.json().get("error", "")
        except ValueError:
            err = ""
        raise GoogleError(f"Google refused the token request ({err or r.status_code}).", 400)
    out: dict[str, Any] = r.json()
    return out


async def exchange_code(code: str, verifier: str) -> dict[str, Any]:
    return await _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": get_settings().google_redirect_uri,
        }
    )


async def fetch_email(access_token: str) -> str:
    async with _http() as http:
        r = await http.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code != 200:
        raise GoogleError("Couldn't read your Google account address.", r.status_code)
    return str(r.json().get("email", "")).lower()


async def revoke(token: str) -> None:
    async with _http() as http:
        await http.post(REVOKE_URL, data={"token": token})


def store_tokens(account: ConnectedAccount, enc: Encryptor, tokens: dict[str, Any]) -> None:
    aad = account.id.bytes
    account.access_token_enc = enc.encrypt(tokens["access_token"], aad)
    if tokens.get("refresh_token"):
        account.refresh_token_enc = enc.encrypt(tokens["refresh_token"], aad)
    account.token_expires_at = datetime.now(UTC) + timedelta(
        seconds=int(tokens.get("expires_in", 3600)) - 60
    )
    if tokens.get("scope"):
        account.scopes = sorted(str(tokens["scope"]).split())


class GoogleClient:
    """Calls Google as one connected account, refreshing the access token when needed."""

    def __init__(self, account: ConnectedAccount, enc: Encryptor) -> None:
        self.account, self.enc = account, enc

    async def _access_token(self, force: bool = False) -> str:
        acc = self.account
        expired = acc.token_expires_at is None or acc.token_expires_at <= datetime.now(UTC)
        if (force or expired) and acc.refresh_token_enc:
            refresh = self.enc.decrypt(acc.refresh_token_enc, acc.id.bytes)
            try:
                tokens = await _token_request(
                    {"grant_type": "refresh_token", "refresh_token": refresh}
                )
            except GoogleError:
                acc.status = "error"
                acc.last_error = "Google sign-in expired. Reconnect Google in Settings."
                raise GoogleError(acc.last_error, 401) from None
            store_tokens(acc, self.enc, tokens)
        if acc.access_token_enc is None:
            raise GoogleError("No Google token stored. Reconnect Google.", 401)
        return self.enc.decrypt(acc.access_token_enc, acc.id.bytes)

    async def request(self, method: str, url: str, **kw: Any) -> dict[str, Any]:
        for attempt in range(2):
            token = await self._access_token(force=attempt == 1)
            async with _http() as http:
                r = await http.request(
                    method, url, headers={"Authorization": f"Bearer {token}"}, **kw
                )
            if r.status_code == 401 and attempt == 0:
                continue
            if r.status_code == 204:
                return {}
            if r.status_code >= 400:
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except (ValueError, AttributeError):
                    msg = ""
                raise GoogleError(f"Google returned {r.status_code}. {msg}".strip(), r.status_code)
            out: dict[str, Any] = r.json()
            return out
        raise GoogleError("Google rejected the token.", 401)

    # --- Gmail ---------------------------------------------------------------
    async def gmail_profile(self) -> dict[str, Any]:
        return await self.request("GET", f"{GMAIL}/profile")

    async def gmail_list(self, q: str, page_token: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"q": q, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        return await self.request("GET", f"{GMAIL}/messages", params=params)

    async def gmail_get(self, message_id: str) -> dict[str, Any]:
        return await self.request(
            "GET", f"{GMAIL}/messages/{message_id}", params={"format": "full"}
        )

    async def gmail_create_draft(self, raw: str, thread_id: str | None) -> dict[str, Any]:
        message: dict[str, Any] = {"raw": raw}
        if thread_id:
            message["threadId"] = thread_id
        return await self.request("POST", f"{GMAIL}/drafts", json={"message": message})

    async def gmail_update_draft(
        self, draft_id: str, raw: str, thread_id: str | None
    ) -> dict[str, Any]:
        message: dict[str, Any] = {"raw": raw}
        if thread_id:
            message["threadId"] = thread_id
        return await self.request(
            "PUT", f"{GMAIL}/drafts/{draft_id}", json={"id": draft_id, "message": message}
        )

    async def gmail_send_draft(self, draft_id: str) -> dict[str, Any]:
        return await self.request("POST", f"{GMAIL}/drafts/send", json={"id": draft_id})

    async def gmail_delete_draft(self, draft_id: str) -> None:
        await self.request("DELETE", f"{GMAIL}/drafts/{draft_id}")

    # --- Calendar ------------------------------------------------------------
    async def events_list(
        self, time_min: datetime, time_max: datetime, page_token: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "showDeleted": "true",
            "maxResults": 250,
        }
        if page_token:
            params["pageToken"] = page_token
        return await self.request("GET", f"{CALENDAR}/calendars/primary/events", params=params)

    async def event_insert(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"{CALENDAR}/calendars/primary/events", json=body)

    async def event_patch(self, event_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            "PATCH", f"{CALENDAR}/calendars/primary/events/{event_id}", json=body
        )

    async def event_delete(self, event_id: str) -> None:
        await self.request("DELETE", f"{CALENDAR}/calendars/primary/events/{event_id}")

    async def test(self) -> None:
        """A real call to each service. Raises GoogleError if either fails."""
        await self.gmail_profile()
        now = datetime.now(UTC)
        await self.request(
            "GET",
            f"{CALENDAR}/calendars/primary/events",
            params={"maxResults": 1, "timeMin": now.isoformat()},
        )
