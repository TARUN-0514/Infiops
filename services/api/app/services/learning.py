"""Learning tracks: a syllabus with spaced review, and a study and lab log."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LearningSession, LearningTopic, LearningTrack

# Topic outline for OSCP preparation, grouped by area. Topic names only; the owner fills
# in notes, labs and progress.
OSCP_SYLLABUS: list[tuple[str, list[str]]] = [
    (
        "Foundations",
        [
            "Linux command line",
            "Windows command line",
            "Networking basics",
            "Bash and Python scripting",
            "Report writing and note taking",
        ],
    ),
    (
        "Recon",
        [
            "Passive information gathering",
            "Port scanning with Nmap",
            "Service enumeration (SMB, SNMP, SMTP, FTP)",
            "Vulnerability scanning",
        ],
    ),
    (
        "Web",
        [
            "Web app enumeration",
            "Directory traversal and file inclusion",
            "File upload attacks",
            "Command injection",
            "SQL injection",
            "Cross-site scripting",
        ],
    ),
    (
        "Exploitation",
        [
            "Finding public exploits",
            "Fixing and adapting exploits",
            "Client-side attacks",
            "Antivirus evasion basics",
            "Password attacks",
            "Metasploit",
        ],
    ),
    ("Privilege escalation", ["Linux privilege escalation", "Windows privilege escalation"]),
    ("Pivoting", ["Port forwarding and tunneling", "SSH and Chisel tunnels"]),
    (
        "Active Directory",
        [
            "AD enumeration",
            "AD authentication attacks (Kerberoasting, AS-REP)",
            "Lateral movement",
            "AD persistence",
            "Attacking AD end to end",
        ],
    ),
    ("Exam", ["Practice exam run", "Exam report template"]),
]

# Days until the next review after a review, by how well it went (0 = forgot, 5 = easy).
FIRST_INTERVAL = {0: 1, 1: 1, 2: 2, 3: 3, 4: 4, 5: 6}


def next_interval(current: int, confidence: int) -> int:
    """A simple spaced-repetition step: forgetting resets, good recall grows the gap."""
    if confidence <= 2:
        return 1
    if current <= 0:
        return FIRST_INTERVAL[confidence]
    factor = {3: 1.6, 4: 2.2, 5: 2.8}[confidence]
    return min(180, max(current + 1, round(current * factor)))


def review(topic: LearningTopic, confidence: int, today: date) -> None:
    if not 0 <= confidence <= 5:
        raise ValueError("Confidence is 0 to 5.")
    topic.interval_days = next_interval(topic.interval_days, confidence)
    topic.next_review_on = today + timedelta(days=topic.interval_days)
    topic.confidence = confidence
    topic.reviews += 1
    if topic.status == "todo":
        topic.status = "learning"


async def create_track(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    *,
    template: str | None,
    goal: str | None = None,
    target_date: date | None = None,
) -> LearningTrack:
    t = LearningTrack(user_id=user_id, name=name, goal=goal, target_date=target_date)
    db.add(t)
    await db.flush()
    if template == "oscp":
        pos = 0
        for section, titles in OSCP_SYLLABUS:
            for title in titles:
                db.add(LearningTopic(track_id=t.id, section=section, title=title, position=pos))
                pos += 1
        await db.flush()
    elif template:
        raise ValueError("Unknown template.")
    return t


async def owned_track(db: AsyncSession, user_id: uuid.UUID, tid: uuid.UUID) -> LearningTrack:
    t = await db.get(LearningTrack, tid)
    if t is None or t.user_id != user_id:
        raise LookupError("Track not found.")
    return t


async def owned_topic(db: AsyncSession, user_id: uuid.UUID, tid: uuid.UUID) -> LearningTopic:
    topic = await db.get(LearningTopic, tid)
    if topic is None or (await owned_track(db, user_id, topic.track_id)) is None:
        raise LookupError("Topic not found.")
    return topic


def topic_out(t: LearningTopic, today: date) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "section": t.section,
        "title": t.title,
        "status": t.status,
        "confidence": t.confidence,
        "notes": t.notes,
        "next_review_on": t.next_review_on.isoformat() if t.next_review_on else None,
        "due": bool(t.next_review_on and t.next_review_on <= today),
        "reviews": t.reviews,
    }


def session_out(s: LearningSession, titles: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "day": s.day.isoformat(),
        "kind": s.kind,
        "minutes": s.minutes,
        "topic_id": str(s.topic_id) if s.topic_id else None,
        "topic": titles.get(s.topic_id) if s.topic_id else None,
        "machine": s.machine,
        "outcome": s.outcome,
        "notes": s.notes,
    }


async def track_detail(db: AsyncSession, t: LearningTrack, today: date) -> dict[str, Any]:
    topics = list(
        await db.scalars(
            select(LearningTopic)
            .where(LearningTopic.track_id == t.id)
            .order_by(LearningTopic.position, LearningTopic.created_at)
        )
    )
    sessions = list(
        await db.scalars(
            select(LearningSession)
            .where(LearningSession.track_id == t.id)
            .order_by(LearningSession.day.desc(), LearningSession.created_at.desc())
        )
    )
    titles = {x.id: x.title for x in topics}
    week_ago = today - timedelta(days=6)
    labs = [s for s in sessions if s.kind == "lab"]
    return {
        "id": str(t.id),
        "name": t.name,
        "goal": t.goal,
        "target_date": t.target_date.isoformat() if t.target_date else None,
        "days_left": (t.target_date - today).days if t.target_date else None,
        "topics": [topic_out(x, today) for x in topics],
        "sessions": [session_out(s, titles) for s in sessions[:100]],
        "stats": {
            "topics": len(topics),
            "done": sum(1 for x in topics if x.status == "done"),
            "learning": sum(1 for x in topics if x.status == "learning"),
            "due_reviews": sum(1 for x in topics if x.next_review_on and x.next_review_on <= today),
            "hours_total": round(sum(s.minutes for s in sessions) / 60, 1),
            "hours_week": round(sum(s.minutes for s in sessions if s.day >= week_ago) / 60, 1),
            "labs": len({(s.machine or "").lower() for s in labs if s.machine}),
            "rooted": len(
                {(s.machine or "").lower() for s in labs if s.machine and s.outcome == "root"}
            ),
        },
    }
