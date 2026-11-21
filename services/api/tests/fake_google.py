"""An in-memory stand-in for Google's OAuth, Gmail and Calendar endpoints."""

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx

from app.integrations import google

ALL_SCOPES = " ".join(google.SCOPES)


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def gmail_message(
    mid: str,
    *,
    subject: str,
    sender: str = "Priya Shah <priya@example.com>",
    body: str = "Hi, can you send the Q3 report by Friday?",
    labels: list[str] | None = None,
    when: datetime | None = None,
) -> dict[str, Any]:
    when = when or datetime.now(UTC) - timedelta(hours=2)
    return {
        "id": mid,
        "threadId": f"t-{mid}",
        "labelIds": labels if labels is not None else ["INBOX", "UNREAD"],
        "snippet": body[:80],
        "internalDate": str(int(when.timestamp() * 1000)),
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": "owner@example.com"},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": f"<{mid}@mail.example.com>"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64(body)}},
                {"mimeType": "text/html", "body": {"data": _b64(f"<p>{body}</p>")}},
            ],
        },
    }


class FakeGoogle:
    def __init__(self) -> None:
        self.scope = ALL_SCOPES
        self.email = "owner@gmail.com"
        self.messages: dict[str, dict[str, Any]] = {}
        self.events: dict[str, dict[str, Any]] = {}
        self.drafts: dict[str, dict[str, Any]] = {}
        self.sent: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str]] = []
        self.access_tokens = 0
        self.fail_calendar = False
        self._n = 0

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def add_event(self, summary: str, start: datetime, minutes: int = 60) -> str:
        eid = self._id("ev")
        self.events[eid] = {
            "id": eid,
            "status": "confirmed",
            "summary": summary,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat()},
            "htmlLink": f"https://calendar.google.com/event?eid={eid}",
        }
        return eid

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        url, method = request.url, request.method
        path = url.path
        self.calls.append((method, f"{url.host}{path}"))
        if url.host == "oauth2.googleapis.com" and path == "/token":
            form = parse_qs(request.content.decode())
            if form.get("code") == ["bad"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.access_tokens += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"ya29.token-{self.access_tokens}",
                    "refresh_token": "1//refresh-secret",
                    "expires_in": 3599,
                    "scope": self.scope,
                    "token_type": "Bearer",
                },
            )
        if path == "/revoke":
            return httpx.Response(200, json={})
        if url.host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"email": self.email})
        if url.host == "gmail.googleapis.com":
            return self._gmail(request, path.removeprefix("/gmail/v1/users/me"))
        if url.host == "www.googleapis.com" and path.startswith("/calendar/v3"):
            if self.fail_calendar:
                return httpx.Response(403, json={"error": {"message": "Calendar API disabled"}})
            return self._calendar(request, path.removeprefix("/calendar/v3/calendars/primary"))
        return httpx.Response(404, json={"error": {"message": f"no route {path}"}})

    def _gmail(self, request: httpx.Request, path: str) -> httpx.Response:
        if path == "/profile":
            return httpx.Response(200, json={"emailAddress": self.email})
        if path == "/messages" and request.method == "GET":
            ids = [{"id": m, "threadId": v["threadId"]} for m, v in self.messages.items()]
            return httpx.Response(200, json={"messages": ids})
        if path.startswith("/messages/"):
            return httpx.Response(200, json=self.messages[path.split("/")[2]])
        if path == "/drafts" and request.method == "POST":
            did = self._id("d")
            self.drafts[did] = json.loads(request.content)["message"]
            return httpx.Response(200, json={"id": did, "message": {"id": self._id("m")}})
        if path.startswith("/drafts/") and request.method == "PUT":
            did = path.split("/")[2]
            self.drafts[did] = json.loads(request.content)["message"]
            return httpx.Response(200, json={"id": did})
        if path.startswith("/drafts/") and request.method == "DELETE":
            self.drafts.pop(path.split("/")[2], None)
            return httpx.Response(204)
        if path == "/drafts/send":
            did = json.loads(request.content)["id"]
            msg = self.drafts.pop(did)
            raw = base64.urlsafe_b64decode(msg["raw"] + "==").decode()
            self.sent.append({"raw": raw, "threadId": msg.get("threadId")})
            return httpx.Response(200, json={"id": self._id("sent"), "labelIds": ["SENT"]})
        return httpx.Response(404, json={"error": {"message": "no gmail route"}})

    def _calendar(self, request: httpx.Request, path: str) -> httpx.Response:
        if path == "/events" and request.method == "GET":
            return httpx.Response(200, json={"items": list(self.events.values())})
        if path == "/events" and request.method == "POST":
            body = json.loads(request.content)
            eid = self._id("ev")
            self.events[eid] = {"id": eid, "status": "confirmed", **body, "htmlLink": "x"}
            return httpx.Response(200, json=self.events[eid])
        eid = path.split("/")[-1]
        if request.method == "PATCH":
            self.events[eid].update(json.loads(request.content))
            return httpx.Response(200, json=self.events[eid])
        if request.method == "DELETE":
            self.events.pop(eid, None)
            return httpx.Response(204)
        return httpx.Response(404, json={"error": {"message": "no calendar route"}})
