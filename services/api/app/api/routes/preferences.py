"""Owner preferences: the Home dashboard layout."""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DB, Auth
from app.models import UserPreferences

router = APIRouter(tags=["preferences"])


class Widget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z_]{1,31}$")
    size: Literal["s", "m", "l"] = "m"
    hidden: bool = False


class HomeLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["compact", "expanded"] = "expanded"
    widgets: list[Widget] = Field(default_factory=list, max_length=30)


async def _prefs(db: DB, auth: Auth) -> UserPreferences:
    prefs = await db.get(UserPreferences, auth.user.id)
    if prefs is None:
        prefs = UserPreferences(user_id=auth.user.id, settings={})
        db.add(prefs)
        await db.flush()
    return prefs


@router.get("/preferences/home", response_model=HomeLayout)
async def get_home(db: DB, auth: Auth) -> HomeLayout:
    prefs = await _prefs(db, auth)
    saved: dict[str, Any] = (prefs.settings or {}).get("home", {})
    mode = prefs.layout if prefs.layout in ("compact", "expanded") else "expanded"
    return HomeLayout(mode=mode, widgets=saved.get("widgets", []))


@router.put("/preferences/home", response_model=HomeLayout)
async def put_home(body: HomeLayout, db: DB, auth: Auth) -> HomeLayout:
    widgets: list[Widget] = []
    for w in body.widgets:
        if all(w.id != kept.id for kept in widgets):
            widgets.append(w)
    prefs = await _prefs(db, auth)
    prefs.layout = body.mode
    prefs.settings = {
        **(prefs.settings or {}),
        "home": {"widgets": [w.model_dump() for w in widgets]},
    }
    await db.commit()
    return HomeLayout(mode=body.mode, widgets=widgets)
