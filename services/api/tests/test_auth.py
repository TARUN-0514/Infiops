import time

import pyotp
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import AuditLog, User
from tests.conftest import OWNER, register_and_login

API = "/api/v1/auth"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_first_user_becomes_owner_and_registration_closes(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/status")).json() == {"registration_open": True}
    r = await client.post(f"{API}/register", json=OWNER)
    assert r.status_code == 201
    assert r.json()["role"] == "owner"
    assert "password_hash" not in r.json()
    assert (await client.get(f"{API}/status")).json() == {"registration_open": False}
    r = await client.post(f"{API}/register", json={**OWNER, "email": "second@example.com"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "registration_closed"


async def test_password_is_hashed_with_argon2(client: AsyncClient) -> None:
    await client.post(f"{API}/register", json=OWNER)
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert OWNER["password"] not in user.password_hash


async def test_register_validates_input(client: AsyncClient) -> None:
    r = await client.post(
        f"{API}/register", json={"email": "bad", "password": "short", "display_name": ""}
    )
    assert r.status_code == 422
    fields = {f["field"] for f in r.json()["error"]["fields"]}
    assert {"email", "password", "display_name"} <= fields
    r = await client.post(f"{API}/register", json={**OWNER, "timezone": "Mars/Base"})
    assert r.status_code == 422


async def test_login_success_sets_secure_cookies(client: AsyncClient) -> None:
    body = await register_and_login(client)
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == OWNER["email"]
    assert client.cookies.get("nexus_refresh")
    assert client.cookies.get("nexus_csrf") == body["csrf_token"]
    me = await client.get(f"{API}/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["display_name"] == "Owner"


async def test_login_wrong_password_and_unknown_email_look_the_same(client: AsyncClient) -> None:
    await client.post(f"{API}/register", json=OWNER)
    a = await client.post(
        f"{API}/login", json={"email": OWNER["email"], "password": "wrong password"}
    )
    b = await client.post(f"{API}/login", json={"email": "nobody@example.com", "password": "x"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()
    async with get_sessionmaker()() as db:
        failures = (
            await db.scalars(select(AuditLog).where(AuditLog.action == "auth.login_failed"))
        ).all()
    assert len(failures) == 2


async def test_login_is_rate_limited(client: AsyncClient) -> None:
    await client.post(f"{API}/register", json=OWNER)
    codes = []
    for _ in range(12):
        r = await client.post(
            f"{API}/login", json={"email": OWNER["email"], "password": "wrong password"}
        )
        codes.append(r.status_code)
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    assert "Retry-After" in r.headers


async def test_me_requires_valid_token(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/me")).status_code == 401
    assert (await client.get(f"{API}/me", headers=bearer("not-a-jwt"))).status_code == 401


async def test_refresh_requires_csrf_and_rotates(client: AsyncClient) -> None:
    body = await register_and_login(client)
    old_refresh = client.cookies.get("nexus_refresh")
    assert (await client.post(f"{API}/refresh")).status_code == 403
    r = await client.post(f"{API}/refresh", headers={"X-CSRF-Token": body["csrf_token"]})
    assert r.status_code == 200, r.text
    new = r.json()
    assert client.cookies.get("nexus_refresh") != old_refresh
    assert new["csrf_token"] != body["csrf_token"]
    assert (await client.get(f"{API}/me", headers=bearer(new["access_token"]))).status_code == 200


async def test_reusing_an_old_refresh_token_revokes_the_session(client: AsyncClient) -> None:
    body = await register_and_login(client)
    stolen = client.cookies.get("nexus_refresh")
    r = await client.post(f"{API}/refresh", headers={"X-CSRF-Token": body["csrf_token"]})
    fresh = r.json()
    # Attacker replays the old token.
    client.cookies.set("nexus_refresh", stolen, path="/api/v1/auth")
    r = await client.post(f"{API}/refresh", headers={"X-CSRF-Token": fresh["csrf_token"]})
    assert r.status_code == 401
    # The legitimate access token from that session no longer works either.
    assert (await client.get(f"{API}/me", headers=bearer(fresh["access_token"]))).status_code == 401


async def test_logout_revokes_session(client: AsyncClient) -> None:
    body = await register_and_login(client)
    h = bearer(body["access_token"])
    assert (await client.post(f"{API}/logout", headers=h)).status_code == 204
    assert (await client.get(f"{API}/me", headers=h)).status_code == 401


async def test_list_and_revoke_other_sessions(client: AsyncClient) -> None:
    first = await register_and_login(client)
    second = (
        await client.post(
            f"{API}/login", json={"email": OWNER["email"], "password": OWNER["password"]}
        )
    ).json()
    h = bearer(second["access_token"])
    sessions = (await client.get(f"{API}/sessions", headers=h)).json()
    assert len(sessions) == 2
    assert sum(s["current"] for s in sessions) == 1
    other = next(s for s in sessions if not s["current"])
    assert (await client.delete(f"{API}/sessions/{other['id']}", headers=h)).status_code == 204
    assert (await client.get(f"{API}/me", headers=bearer(first["access_token"]))).status_code == 401
    assert (await client.get(f"{API}/me", headers=h)).status_code == 200


async def test_mfa_enrolment_login_and_replay_protection(client: AsyncClient) -> None:
    body = await register_and_login(client)
    h = bearer(body["access_token"])
    setup = (await client.post(f"{API}/mfa/setup", headers=h)).json()
    totp = pyotp.TOTP(setup["secret"])
    assert (
        await client.post(f"{API}/mfa/enable", headers=h, json={"code": "000000"})
    ).status_code == 400
    r = await client.post(f"{API}/mfa/enable", headers=h, json={"code": totp.now()})
    assert r.status_code == 200 and r.json()["mfa_enabled"] is True

    creds = {"email": OWNER["email"], "password": OWNER["password"]}
    r = await client.post(f"{API}/login", json=creds)
    assert r.status_code == 401 and r.json()["error"]["code"] == "mfa_required"

    next_code = totp.at(time.time() + 30)  # a step after the one used at enrolment
    r = await client.post(f"{API}/login", json={**creds, "totp_code": next_code})
    assert r.status_code == 200, r.text
    # The same code cannot be used twice.
    r = await client.post(f"{API}/login", json={**creds, "totp_code": next_code})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_mfa_code"

    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User))
    assert user is not None and user.mfa_secret_enc is not None
    assert setup["secret"].encode() not in user.mfa_secret_enc
