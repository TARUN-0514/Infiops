"""Security workspaces: boards with their own statuses and fields, findings with SLA and
aging, escalations, follow-ups, and imports from Inspector, GHAS and DAST exports."""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Workspace, WorkspaceItem, WorkspaceItemEvent
from app.models.workspace import SEVERITIES
from app.services import notify

DEFAULT_SLA = {"critical": 7, "high": 30, "medium": 90, "low": 180}
VULN_SOURCES = ("inspector", "ghas", "dast", "guardium", "pentest", "manual")
MAX_IMPORT = 5000

# Starting boards. Empty: they hold only what the owner adds or imports.
DEFAULT_WORKSPACES: list[dict[str, Any]] = [
    {
        "kind": "vulns",
        "name": "Vulnerability management",
        "statuses": [
            "New",
            "Triaged",
            "In remediation",
            "Risk accepted",
            "Fixed",
            "False positive",
        ],
        "closed": ["Fixed", "False positive", "Risk accepted"],
        "fields": [],
        "sla_days": DEFAULT_SLA,
    },
    {
        "kind": "appsec",
        "name": "AppSec",
        "statuses": ["Backlog", "Threat model", "Review", "Fixes", "Done"],
        "closed": ["Done"],
        "fields": [
            {"key": "app", "label": "Application", "type": "text"},
            {
                "key": "review_type",
                "label": "Review type",
                "type": "select",
                "options": ["Design review", "Code review", "SAST triage", "Release sign-off"],
            },
        ],
        "sla_days": {},
    },
    {
        "kind": "cloud",
        "name": "Cloud security",
        "statuses": ["Backlog", "Investigating", "Fixing", "Done"],
        "closed": ["Done"],
        "fields": [
            {"key": "account", "label": "Account", "type": "text"},
            {"key": "service", "label": "Service", "type": "text"},
        ],
        "sla_days": DEFAULT_SLA,
    },
    {
        "kind": "pentest",
        "name": "Pentests",
        "statuses": ["Scoping", "Testing", "Reporting", "Retest", "Closed"],
        "closed": ["Closed"],
        "fields": [
            {"key": "target", "label": "Target", "type": "text"},
            {"key": "window", "label": "Test window", "type": "text"},
            {"key": "findings", "label": "Findings", "type": "number"},
        ],
        "sla_days": {},
    },
]


async def ensure_defaults(db: AsyncSession, user_id: uuid.UUID) -> None:
    if await db.scalar(select(Workspace.id).where(Workspace.user_id == user_id).limit(1)):
        return
    for i, w in enumerate(DEFAULT_WORKSPACES):
        db.add(Workspace(user_id=user_id, position=i, **w))
    await db.flush()


async def owned_workspace(db: AsyncSession, user_id: uuid.UUID, wid: uuid.UUID) -> Workspace:
    w = await db.get(Workspace, wid)
    if w is None or w.user_id != user_id:
        raise LookupError("Workspace not found.")
    return w


async def owned_item(db: AsyncSession, user_id: uuid.UUID, iid: uuid.UUID) -> WorkspaceItem:
    it = await db.get(WorkspaceItem, iid)
    if it is None or it.user_id != user_id:
        raise LookupError("Item not found.")
    return it


def due_for(ws: Workspace, severity: str, found_on: date) -> date | None:
    days = ws.sla_days.get(severity)
    return found_on + timedelta(days=int(days)) if days else None


def check_fields(ws: Workspace, data: dict[str, Any]) -> dict[str, Any]:
    """Keep only the workspace's own fields, with values of the right type."""
    out: dict[str, Any] = {}
    for f in ws.fields:
        v = data.get(f["key"])
        if v in (None, ""):
            continue
        if f["type"] == "number":
            try:
                v = float(v)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{f['label']} must be a number.") from exc
        elif f["type"] == "select" and v not in f.get("options", []):
            raise ValueError(f"{f['label']} must be one of: {', '.join(f.get('options', []))}.")
        else:
            v = str(v)[:300]
        out[f["key"]] = v
    return out


def event(item: WorkspaceItem, kind: str, text: str = "") -> WorkspaceItemEvent:
    return WorkspaceItemEvent(item_id=item.id, kind=kind, text=text[:2000])


def set_status(ws: Workspace, item: WorkspaceItem, status: str, today: date) -> str | None:
    """Move an item; returns the history line, or None when nothing changed."""
    if status not in ws.statuses:
        raise ValueError(f"Status must be one of: {', '.join(ws.statuses)}.")
    if status == item.status:
        return None
    was_closed = item.status in ws.closed
    old, item.status = item.status, status
    if status in ws.closed:
        item.closed_on = item.closed_on or today
        item.follow_up_on = None
    elif was_closed:
        item.closed_on = None
        item.sla_notified_on = None
    return f"{old} → {status}"


def item_out(ws: Workspace, it: WorkspaceItem, today: date) -> dict[str, Any]:
    closed = it.status in ws.closed
    end = it.closed_on or today
    days_left = (it.due_on - today).days if it.due_on and not closed else None
    return {
        "id": str(it.id),
        "workspace_id": str(it.workspace_id),
        "title": it.title,
        "status": it.status,
        "closed": closed,
        "severity": it.severity,
        "source": it.source,
        "asset": it.asset,
        "identifier": it.identifier,
        "owner": it.owner,
        "description": it.description,
        "found_on": it.found_on.isoformat(),
        "due_on": it.due_on.isoformat() if it.due_on else None,
        "closed_on": it.closed_on.isoformat() if it.closed_on else None,
        "follow_up_on": it.follow_up_on.isoformat() if it.follow_up_on else None,
        "escalated_at": it.escalated_at.isoformat() if it.escalated_at else None,
        "escalated_to": it.escalated_to,
        "age_days": (end - it.found_on).days,
        "days_left": days_left,
        "breached": days_left is not None and days_left < 0,
        "data": it.data,
    }


def summary(ws: Workspace, items: list[WorkspaceItem], today: date) -> dict[str, Any]:
    """Counts for the dashboard, from the items as they are."""
    open_items = [i for i in items if i.status not in ws.closed]
    ages = [(today - i.found_on).days for i in open_items]
    breached = [i for i in open_items if i.due_on and i.due_on < today]
    due_soon = [i for i in open_items if i.due_on and 0 <= (i.due_on - today).days <= 7]
    closed = [i for i in items if i.status in ws.closed and i.closed_on]
    mttr = (
        round(sum((i.closed_on - i.found_on).days for i in closed if i.closed_on) / len(closed), 1)
        if closed
        else None
    )
    in_sla = [i for i in closed if i.due_on and i.closed_on and i.closed_on <= i.due_on]
    with_sla = [i for i in closed if i.due_on]
    return {
        "open": len(open_items),
        "closed": len(items) - len(open_items),
        "by_severity": {s: sum(1 for i in open_items if i.severity == s) for s in SEVERITIES},
        "by_source": dict(Counter(i.source for i in open_items).most_common()),
        "by_status": {s: sum(1 for i in items if i.status == s) for s in ws.statuses},
        "aging": {
            "0-30": sum(1 for a in ages if a <= 30),
            "31-60": sum(1 for a in ages if 30 < a <= 60),
            "61-90": sum(1 for a in ages if 60 < a <= 90),
            "90+": sum(1 for a in ages if a > 90),
        },
        "breached": len(breached),
        "due_soon": len(due_soon),
        "escalated": sum(1 for i in open_items if i.escalated_at),
        "mean_days_to_close": mttr,
        "closed_in_sla_pct": round(100 * len(in_sla) / len(with_sla)) if with_sla else None,
    }


async def sla_alerts(db: AsyncSession, user: User, today: date) -> int:
    """One notification per item when its SLA is breached, and on its follow-up date."""
    sent = 0
    rows = await db.execute(
        select(WorkspaceItem, Workspace)
        .join(Workspace, Workspace.id == WorkspaceItem.workspace_id)
        .where(WorkspaceItem.user_id == user.id, WorkspaceItem.closed_on.is_(None))
    )
    breached: list[WorkspaceItem] = []
    for it, ws in rows.tuples():
        if it.status in ws.closed:
            continue
        if it.due_on and it.due_on < today and it.sla_notified_on is None:
            breached.append(it)
            it.sla_notified_on = today
        if it.follow_up_on and it.follow_up_on <= today:
            await notify.notify(
                db,
                user.id,
                kind="workspace",
                title=f"Follow up: {it.title[:80]}",
                body=f"{it.severity.title()} · {it.status}"
                + (f" · {it.owner}" if it.owner else ""),
                link=f"/work?tab=ws&item={it.id}",
            )
            db.add(event(it, "follow_up", "Reminder sent"))
            it.follow_up_on = None
            sent += 1
    if breached:
        first = breached[0]
        await notify.notify(
            db,
            user.id,
            kind="workspace",
            title=f"{len(breached)} finding{'s' if len(breached) > 1 else ''} past SLA",
            body=first.title[:120]
            + (f" and {len(breached) - 1} more" if len(breached) > 1 else ""),
            link="/work?tab=ws",
        )
        sent += 1
    return sent


# --- imports ------------------------------------------------------------------------------


@dataclass
class Parsed:
    format: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


SEV_WORDS = {
    "critical": "critical",
    "high": "high",
    "error": "high",
    "medium": "medium",
    "moderate": "medium",
    "warning": "medium",
    "low": "low",
    "note": "low",
    "informational": "info",
    "info": "info",
    "untriaged": "medium",
}


def norm_severity(raw: Any) -> str:
    return SEV_WORDS.get(str(raw or "").strip().lower(), "medium")


def _date(raw: Any, fallback: date) -> date:
    s = str(raw or "").strip()
    if not s:
        return fallback
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%b %d, %Y %H:%M:%S",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(s[:26], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC).date()
    except ValueError:
        return fallback


def _ghas(alerts: list[dict[str, Any]], today: date) -> Parsed:
    """`gh api repos/OWNER/REPO/code-scanning/alerts` (or dependabot / secret-scanning)."""
    out = Parsed("ghas")
    for a in alerts[:MAX_IMPORT]:
        if not isinstance(a, dict):
            continue
        rule = a.get("rule") or {}
        repo = (a.get("repository") or {}).get("full_name") or ""
        loc = ((a.get("most_recent_instance") or {}).get("location") or {}).get("path", "")
        adv = a.get("security_advisory") or {}
        dep = (a.get("dependency") or {}).get("package") or {}
        title = rule.get("description") or adv.get("summary") or a.get("secret_type_display_name")
        if not title:
            out.errors.append(f"Alert {a.get('number', '?')}: no title.")
            continue
        sev = rule.get("security_severity_level") or rule.get("severity") or adv.get("severity")
        if a.get("secret_type"):
            sev = "high"
        state = str(a.get("state", "open"))
        out.rows.append(
            {
                "title": str(title)[:300],
                "severity": norm_severity(sev),
                "source": "ghas",
                "asset": (f"{repo}:{loc}" if loc else repo or dep.get("name") or None),
                "identifier": rule.get("id") or adv.get("cve_id") or adv.get("ghsa_id"),
                "found_on": _date(a.get("created_at"), today),
                "description": (rule.get("full_description") or adv.get("description") or "")[:4000]
                or None,
                "external_key": a.get("html_url") or f"ghas:{repo}:{a.get('number')}",
                "fixed": state in ("fixed", "dismissed", "resolved", "auto_dismissed"),
            }
        )
    return out


CSV_ROLES: dict[str, str] = {
    "title": r"^(title|finding|vulnerability|name|alert|issue|plugin name|rule)$",
    "severity": r"severity|risk|priority",
    "asset": r"^(resource|resource id|asset|host|url|target|instance|repository|db|database)",
    "identifier": r"^(cve|vulnerability id|cve id|cwe|id|finding arn|plugin id|rule id)$",
    "found_on": r"first (observed|seen)|discovered|found|created|date",
    "status": r"^(status|state)$",
    "description": r"description|details|evidence",
    "owner": r"owner|assignee",
}


def _csv(raw: str, today: date, source: str) -> Parsed:
    out = Parsed(source)
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(raw), dialect))
    if not rows:
        out.errors.append("The file is empty.")
        return out
    header = [c.strip().lower() for c in rows[0]]
    col: dict[str, int] = {}
    for i, h in enumerate(header):
        for role, pat in CSV_ROLES.items():
            if role not in col and re.search(pat, h):
                col[role] = i
                break
    if "title" not in col:
        out.errors.append("Couldn't find a title column (Title, Finding, Vulnerability or Name).")
        return out
    if len(rows) > MAX_IMPORT + 1:
        out.errors.append(f"Only the first {MAX_IMPORT} rows are read.")
    for n, r in enumerate(rows[1 : MAX_IMPORT + 1], start=2):
        r = r + [""] * (len(header) - len(r))

        def get(role: str, row: list[str] = r) -> str:
            return row[col[role]].strip() if role in col else ""

        title = get("title")
        if not title:
            continue
        status = get("status").lower()
        asset, ident = get("asset") or None, get("identifier") or None
        out.rows.append(
            {
                "title": title[:300],
                "severity": norm_severity(get("severity")),
                "source": source,
                "asset": asset[:300] if asset else None,
                "identifier": ident[:120] if ident else None,
                "found_on": _date(get("found_on"), today),
                "description": get("description")[:4000] or None,
                "owner": get("owner")[:120] or None,
                "external_key": f"{source}:{ident or title}:{asset or ''}"[:300],
                "fixed": status in ("closed", "fixed", "resolved", "suppressed", "inactive"),
            }
        )
        if n > MAX_IMPORT + 1:
            break
    return out


def parse_import(raw: bytes, source: str, today: date) -> Parsed:
    if source not in VULN_SOURCES:
        raise ValueError("Pick where the file came from.")
    text = raw.decode("utf-8-sig", errors="replace").strip()
    if text.startswith("[") or text.startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("That JSON file couldn't be read.") from exc
        if isinstance(doc, dict) and "findings" in doc:  # Inspector JSON export
            return _inspector_json(doc["findings"], today)
        if isinstance(doc, list):
            return _ghas(doc, today) if source == "ghas" else _inspector_json(doc, today)
        raise ValueError("Expected a list of alerts or an Inspector findings export.")
    return _csv(text, today, source)


def _inspector_json(findings: list[dict[str, Any]], today: date) -> Parsed:
    out = Parsed("inspector")
    for f in findings[:MAX_IMPORT]:
        if not isinstance(f, dict) or not f.get("title"):
            continue
        res = (f.get("resources") or [{}])[0]
        pkg = f.get("packageVulnerabilityDetails") or {}
        out.rows.append(
            {
                "title": str(f["title"])[:300],
                "severity": norm_severity(f.get("severity")),
                "source": "inspector",
                "asset": res.get("id"),
                "identifier": pkg.get("vulnerabilityId"),
                "found_on": _date(f.get("firstObservedAt"), today),
                "description": (f.get("description") or "")[:4000] or None,
                "external_key": f.get("findingArn") or f"inspector:{f['title']}:{res.get('id')}",
                "fixed": str(f.get("status", "")).upper() in ("CLOSED", "SUPPRESSED"),
            }
        )
    return out


async def import_rows(
    db: AsyncSession, ws: Workspace, parsed: Parsed, today: date
) -> dict[str, int]:
    """Add new findings; for ones already here, close or reopen them to match the scanner."""
    keys = [r["external_key"] for r in parsed.rows]
    existing = (
        {
            i.external_key: i
            for i in await db.scalars(
                select(WorkspaceItem).where(
                    WorkspaceItem.workspace_id == ws.id, WorkspaceItem.external_key.in_(keys)
                )
            )
        }
        if keys
        else {}
    )
    done_status = next((s for s in ws.closed if s.lower() == "fixed"), ws.closed[0])
    open_status = ws.statuses[0]
    added = updated = unchanged = 0
    seen: set[str] = set()
    for r in parsed.rows:
        key = r["external_key"]
        if key in seen:
            continue
        seen.add(key)
        it = existing.get(key)
        if it is None:
            if r["fixed"]:
                unchanged += 1  # never seen open; nothing to track
                continue
            it = WorkspaceItem(
                user_id=ws.user_id,
                workspace_id=ws.id,
                status=open_status,
                due_on=due_for(ws, r["severity"], r["found_on"]),
                data={},
                **{k: v for k, v in r.items() if k != "fixed"},
            )
            db.add(it)
            await db.flush()
            db.add(event(it, "imported", f"Imported from {r['source']}"))
            added += 1
            continue
        target = done_status if r["fixed"] else (open_status if it.status in ws.closed else None)
        line = set_status(ws, it, target, today) if target else None
        if line:
            db.add(event(it, "status", f"{line} (from {r['source']} import)"))
            updated += 1
        else:
            unchanged += 1
    return {"added": added, "updated": updated, "unchanged": unchanged}
