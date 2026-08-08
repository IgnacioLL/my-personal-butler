"""In-memory calendar store — read events, detect conflicts, suggest free slots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    timezone: str = "UTC"
    location: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "timezone": self.timezone,
            "location": self.location,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalendarEvent":
        start_raw = data.get("start")
        end_raw = data.get("end")
        if not start_raw or not end_raw:
            raise ValueError("calendar event requires start and end")
        start = start_raw if isinstance(start_raw, datetime) else datetime.fromisoformat(str(start_raw))
        end = end_raw if isinstance(end_raw, datetime) else datetime.fromisoformat(str(end_raw))
        return cls(
            id=str(data.get("id") or f"evt-{uuid4().hex[:12]}"),
            title=str(data.get("title") or ""),
            start=start,
            end=end,
            timezone=str(data.get("timezone") or "UTC"),
            location=str(data.get("location") or ""),
            meta=dict(data.get("meta") or {}),
        )


@dataclass(frozen=True)
class Conflict:
    proposed_title: str
    proposed_start: datetime
    proposed_end: datetime
    existing_id: str
    existing_title: str
    existing_start: datetime
    existing_end: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposed_title": self.proposed_title,
            "proposed_start": self.proposed_start.isoformat(),
            "proposed_end": self.proposed_end.isoformat(),
            "existing_id": self.existing_id,
            "existing_title": self.existing_title,
            "existing_start": self.existing_start.isoformat(),
            "existing_end": self.existing_end.isoformat(),
        }


@dataclass(frozen=True)
class FreeSlot:
    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_minutes": int(self.duration.total_seconds() // 60),
        }


def intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open overlap: [start, end). Touching endpoints do not conflict."""
    return a_start < b_end and b_start < a_end


def _as_aware(dt: datetime, fallback_tz: Any = None) -> datetime:
    if dt.tzinfo is not None:
        return dt
    if fallback_tz is not None:
        return dt.replace(tzinfo=fallback_tz)
    return dt


class CalendarStore:
    """Authoritative in-memory calendar events for harness / soft-confirm writes."""

    def __init__(self) -> None:
        self.events: dict[str, CalendarEvent] = {}

    def create(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        timezone: str = "UTC",
        location: str = "",
        meta: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> CalendarEvent:
        if end <= start:
            raise ValueError("event end must be after start")
        evt = CalendarEvent(
            id=event_id or f"evt-{uuid4().hex[:12]}",
            title=title.strip(),
            start=start,
            end=end,
            timezone=timezone,
            location=location,
            meta=dict(meta or {}),
        )
        self.events[evt.id] = evt
        return evt

    def upsert_from_payload(self, payload: dict[str, Any], *, event_id: str | None = None) -> CalendarEvent:
        """Create or replace from adapter payload (ISO strings or datetime)."""
        data = dict(payload)
        if event_id:
            data["id"] = event_id
        elif "id" not in data:
            data.setdefault("id", f"evt-{uuid4().hex[:12]}")
        # Soft-confirm harness payloads may omit end — default 1h block.
        if not data.get("end") and data.get("start"):
            start_raw = data["start"]
            start_dt = (
                start_raw
                if isinstance(start_raw, datetime)
                else datetime.fromisoformat(str(start_raw))
            )
            data["end"] = (start_dt + timedelta(hours=1)).isoformat()
        evt = CalendarEvent.from_dict(data)
        if evt.end <= evt.start:
            raise ValueError("event end must be after start")
        self.events[evt.id] = evt
        return evt

    def get(self, event_id: str) -> Optional[CalendarEvent]:
        return self.events.get(event_id)

    def list_all(self) -> list[CalendarEvent]:
        return sorted(self.events.values(), key=lambda e: e.start)

    def list_between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return [e for e in self.list_all() if intervals_overlap(e.start, e.end, start, end)]

    def upcoming(self, now: datetime, *, limit: int = 20) -> list[CalendarEvent]:
        return [e for e in self.list_all() if e.end > now][:limit]

    def modify(self, event_id: str, patch: dict[str, Any]) -> CalendarEvent:
        existing = self.events.get(event_id)
        if existing is None:
            return self.upsert_from_payload({**patch, "id": event_id})
        data = existing.to_dict()
        data.update({k: v for k, v in patch.items() if v is not None})
        data["id"] = event_id
        updated = CalendarEvent.from_dict(data)
        self.events[event_id] = updated
        return updated

    def cancel(self, event_id: str) -> bool:
        if event_id not in self.events:
            return False
        del self.events[event_id]
        return True

    def find_conflicts(
        self,
        start: datetime,
        end: datetime,
        *,
        title: str = "",
        exclude_id: str | None = None,
    ) -> list[Conflict]:
        conflicts: list[Conflict] = []
        for evt in self.list_all():
            if exclude_id and evt.id == exclude_id:
                continue
            if intervals_overlap(start, end, evt.start, evt.end):
                conflicts.append(
                    Conflict(
                        proposed_title=title,
                        proposed_start=start,
                        proposed_end=end,
                        existing_id=evt.id,
                        existing_title=evt.title,
                        existing_start=evt.start,
                        existing_end=evt.end,
                    )
                )
        return conflicts

    def suggest_free_slots(
        self,
        *,
        day_start: datetime,
        day_end: datetime,
        duration: timedelta,
        step: timedelta | None = None,
        limit: int = 5,
    ) -> list[FreeSlot]:
        """Suggest free slots of `duration` within [day_start, day_end)."""
        if duration <= timedelta(0):
            raise ValueError("duration must be positive")
        if day_end <= day_start:
            return []
        step = step or timedelta(minutes=30)
        busy = [
            (e.start, e.end)
            for e in self.list_between(day_start, day_end)
        ]
        busy.sort(key=lambda x: x[0])

        # Merge busy intervals for simpler scanning.
        merged: list[tuple[datetime, datetime]] = []
        for b_start, b_end in busy:
            if not merged or b_start > merged[-1][1]:
                merged.append((b_start, b_end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b_end))

        free_windows: list[tuple[datetime, datetime]] = []
        cursor = day_start
        for b_start, b_end in merged:
            if cursor < b_start:
                free_windows.append((cursor, b_start))
            cursor = max(cursor, b_end)
        if cursor < day_end:
            free_windows.append((cursor, day_end))

        slots: list[FreeSlot] = []
        for w_start, w_end in free_windows:
            candidate = w_start
            while candidate + duration <= w_end:
                slots.append(FreeSlot(start=candidate, end=candidate + duration))
                if len(slots) >= limit:
                    return slots
                candidate = candidate + step
        return slots

    def clear(self) -> None:
        self.events.clear()

    def to_dict(self) -> dict[str, Any]:
        return {"events": [e.to_dict() for e in self.list_all()]}

    def seed_from_dicts(self, events: list[dict[str, Any]]) -> list[CalendarEvent]:
        seeded: list[CalendarEvent] = []
        for raw in events:
            evt = CalendarEvent.from_dict(raw)
            self.events[evt.id] = evt
            seeded.append(evt)
        return seeded

    def load_fixture(self, path: Path | str) -> list[CalendarEvent]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        events = data.get("events", data if isinstance(data, list) else [])
        return self.seed_from_dicts(list(events))
