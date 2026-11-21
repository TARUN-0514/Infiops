import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.ai.gateway import get_gateway
from app.ai.memory_agent import extract_and_store
from app.ai.providers import ScriptedProvider
from app.db.session import get_sessionmaker
from app.models import MemoryConflict, MemoryItem, MemorySource, User
from app.services import memory as mem
from tests.conftest import auth_headers

API = "/api/v1"


async def _user(client: AsyncClient) -> tuple[dict[str, str], uuid.UUID]:
    h = await auth_headers(client)
    me = (await client.get(f"{API}/auth/me", headers=h)).json()
    return h, uuid.UUID(me["id"])


async def test_remember_dedupes_and_adds_source(client: AsyncClient) -> None:
    _, uid = await _user(client)
    async with get_sessionmaker()() as db:
        a, created_a = await mem.remember(
            db, uid, "The user lives in Bengaluru.", category="profile"
        )
        b, created_b = await mem.remember(
            db, uid, "the user lives in bengaluru", source_type="chat", source_id="m1"
        )
        await db.commit()
        n_sources = len(list(await db.scalars(select(MemorySource))))
    assert created_a and not created_b and a.id == b.id and n_sources == 2


async def test_hybrid_search_ranks_relevant_first(client: AsyncClient) -> None:
    _, uid = await _user(client)
    async with get_sessionmaker()() as db:
        await mem.remember(db, uid, "The user works as a security engineer", category="work")
        await mem.remember(db, uid, "The user is allergic to peanuts", category="health")
        await mem.remember(db, uid, "Secret vault code", privacy="secret")
        await db.commit()
        hits = await mem.search(db, uid, "what is my job as an engineer")
        secret = await mem.search(db, uid, "vault code")
        secret_ok = await mem.search(db, uid, "vault code", allow_secret=True)
    assert hits[0].item.content == "The user works as a security engineer"
    assert secret == [] and len(secret_ok) == 1


async def test_edit_supersedes_and_keeps_history(client: AsyncClient) -> None:
    h, _ = await _user(client)
    r = await client.post(
        f"{API}/memory",
        json={"content": "The user drives a Honda City", "category": "profile"},
        headers=h,
    )
    old_id = r.json()["id"]
    r = await client.patch(
        f"{API}/memory/{old_id}", json={"content": "The user drives a Tata Nexon"}, headers=h
    )
    new = r.json()
    assert new["version"] == 2 and new["supersedes_id"] == old_id
    hist = (await client.get(f"{API}/memory/{new['id']}/history", headers=h)).json()
    assert [x["content"] for x in hist] == [
        "The user drives a Tata Nexon",
        "The user drives a Honda City",
    ]
    assert hist[1]["status"] == "superseded"
    # old version can't be edited again
    assert (
        await client.patch(f"{API}/memory/{old_id}", json={"content": "xyz abc"}, headers=h)
    ).status_code == 400
    listed = (await client.get(f"{API}/memory", headers=h)).json()
    assert [x["id"] for x in listed] == [new["id"]]


async def test_forget_removes_all_versions(client: AsyncClient) -> None:
    h, _ = await _user(client)
    old = (await client.post(f"{API}/memory", json={"content": "Fact one here"}, headers=h)).json()
    new = (
        await client.patch(
            f"{API}/memory/{old['id']}", json={"content": "Fact two here"}, headers=h
        )
    ).json()
    assert (await client.delete(f"{API}/memory/{new['id']}", headers=h)).status_code == 204
    async with get_sessionmaker()() as db:
        assert (await db.scalars(select(MemoryItem))).first() is None


async def test_extraction_respects_consent(client: AsyncClient, model: ScriptedProvider) -> None:
    h, uid = await _user(client)
    model.push(
        {
            "facts": [
                {
                    "content": "The user's name is Tarun",
                    "category": "profile",
                    "kind": "semantic",
                    "confidence": 0.95,
                    "explicit": True,
                    "replaces_id": "",
                },
                {
                    "content": "The user has high blood pressure",
                    "category": "health",
                    "kind": "semantic",
                    "confidence": 0.95,
                    "explicit": True,
                    "replaces_id": "",
                },
                {
                    "content": "The user probably likes cricket",
                    "category": "preference",
                    "kind": "semantic",
                    "confidence": 0.6,
                    "explicit": False,
                    "replaces_id": "",
                },
            ]
        }
    )
    async with get_sessionmaker()() as db:
        user = await db.get(User, uid)
        assert user is not None
        counts = await extract_and_store(
            db,
            get_gateway(),
            user=user,
            user_text="I'm Tarun, I have high blood pressure",
            assistant_text="Noted.",
            message_id=None,
        )
        await db.commit()
        items = {i.content: i for i in await db.scalars(select(MemoryItem))}
    assert counts["created"] == 1 and counts["inferred"] == 2
    assert items["The user's name is Tarun"].status == "active"
    health = items["The user has high blood pressure"]
    assert health.status == "inferred" and health.privacy == "sensitive"  # health asks first
    assert items["The user probably likes cricket"].status == "inferred"
    # extraction prompt wraps the conversation as data
    assert "<user_message>" in model.requests[0].messages[0]["content"]

    pending = (await client.get(f"{API}/memory?status=inferred", headers=h)).json()
    r = await client.post(f"{API}/memory/{pending[0]['id']}/confirm", headers=h)
    assert r.json()["status"] == "active"


async def test_consent_off_skips_category(client: AsyncClient, model: ScriptedProvider) -> None:
    h, uid = await _user(client)
    r = await client.put(f"{API}/memory/consent", json={"finance": "off"}, headers=h)
    assert r.json()["finance"] == "off"
    model.push(
        {
            "facts": [
                {
                    "content": "The user earns a lot",
                    "category": "finance",
                    "kind": "semantic",
                    "confidence": 0.9,
                    "explicit": True,
                    "replaces_id": "",
                }
            ]
        }
    )
    async with get_sessionmaker()() as db:
        user = await db.get(User, uid)
        assert user is not None
        await extract_and_store(
            db,
            get_gateway(),
            user=user,
            user_text="My salary went up a lot",
            assistant_text="",
            message_id=None,
        )
        await db.commit()
        assert (await db.scalars(select(MemoryItem))).first() is None


async def test_update_supersedes_or_opens_conflict(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h, uid = await _user(client)
    async with get_sessionmaker()() as db:
        city, _ = await mem.remember(db, uid, "The user lives in Pune city", category="profile")
        boss, _ = await mem.remember(db, uid, "The user reports to Anil at work", category="people")
        await db.commit()
    model.push(
        {
            "facts": [
                {
                    "content": "The user lives in Mumbai city",
                    "category": "profile",
                    "kind": "semantic",
                    "confidence": 0.95,
                    "explicit": True,
                    "replaces_id": str(city.id),
                },
                {
                    "content": "The user reports to Meera at work",
                    "category": "people",
                    "kind": "semantic",
                    "confidence": 0.95,
                    "explicit": True,
                    "replaces_id": str(boss.id),
                },
            ]
        }
    )
    async with get_sessionmaker()() as db:
        user = await db.get(User, uid)
        assert user is not None
        counts = await extract_and_store(
            db,
            get_gateway(),
            user=user,
            user_text="I moved to Mumbai city and now report to Meera at work",
            assistant_text="",
            message_id=None,
        )
        await db.commit()
        conflict = (await db.scalars(select(MemoryConflict))).one()
    assert counts == {"created": 0, "inferred": 0, "merged": 0, "superseded": 1, "conflicts": 1}
    conflicts = (await client.get(f"{API}/memory/conflicts", headers=h)).json()
    assert conflicts[0]["memory"]["content"] == "The user reports to Anil at work"
    r = await client.post(
        f"{API}/memory/conflicts/{conflict.id}/resolve", json={"keep": "candidate"}, headers=h
    )
    assert r.json()["content"] == "The user reports to Meera at work"
    assert (await client.get(f"{API}/memory/conflicts", headers=h)).json() == []


async def test_memory_api_is_owner_scoped(client: AsyncClient) -> None:
    h, _ = await _user(client)
    r = await client.get(f"{API}/memory/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404
    assert (await client.get(f"{API}/memory")).status_code == 401
