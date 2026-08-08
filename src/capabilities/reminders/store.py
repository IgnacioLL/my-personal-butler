"""Reminder + habit schedule store (in-memory, optional JSON persistence)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from capabilities.reminders.parse import next_weekly_after


class ReminderKind(str, Enum):
    ONE_SHOT = "one_shot"
    RECURRING = "recurring"


class ReminderStatus(str, Enum):
    ACTIVE = "active"
    FIRED = "fired"
    SNOOZED = "snoozed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class HabitStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class EscalationChannel(str, Enum):
    """E2E-02 ladder order — WhatsApp first."""

    WHATSAPP = "whatsapp"
    ANDROID = "android"
    CALL = "call"


ESCALATION_ORDER: tuple[EscalationChannel, ...] = (
    EscalationChannel.WHATSAPP,
    EscalationChannel.ANDROID,
    EscalationChannel.CALL,
)


def _parse_dt(value: str | datetime | None) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _fmt_dt(value: datetime | None) -> Optional[str]:
    return value.isoformat() if value is not None else None


@dataclass
class Reminder:
    id: str
    text: str
    timezone: str
    kind: ReminderKind
    status: ReminderStatus
    due_at: datetime
    created_at: datetime
    hour: int = 0
    minute: int = 0
    weekday: Optional[int] = None
    channel: str = "whatsapp"
    recipient: str = ""
    habit_id: Optional[str] = None
    fire_count: int = 0
    last_fired_at: Optional[datetime] = None
    snooze_until: Optional[datetime] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "timezone": self.timezone,
            "kind": self.kind.value,
            "status": self.status.value,
            "due_at": _fmt_dt(self.due_at),
            "created_at": _fmt_dt(self.created_at),
            "hour": self.hour,
            "minute": self.minute,
            "weekday": self.weekday,
            "channel": self.channel,
            "recipient": self.recipient,
            "habit_id": self.habit_id,
            "fire_count": self.fire_count,
            "last_fired_at": _fmt_dt(self.last_fired_at),
            "snooze_until": _fmt_dt(self.snooze_until),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reminder":
        return cls(
            id=data["id"],
            text=data["text"],
            timezone=data["timezone"],
            kind=ReminderKind(data["kind"]),
            status=ReminderStatus(data["status"]),
            due_at=_parse_dt(data["due_at"]) or datetime.min,
            created_at=_parse_dt(data["created_at"]) or datetime.min,
            hour=int(data.get("hour") or 0),
            minute=int(data.get("minute") or 0),
            weekday=data.get("weekday"),
            channel=data.get("channel") or "whatsapp",
            recipient=data.get("recipient") or "",
            habit_id=data.get("habit_id"),
            fire_count=int(data.get("fire_count") or 0),
            last_fired_at=_parse_dt(data.get("last_fired_at")),
            snooze_until=_parse_dt(data.get("snooze_until")),
            meta=dict(data.get("meta") or {}),
        )


@dataclass
class Habit:
    """Recurring habit with optional escalation ladder (E2E-02 scaffolding)."""

    id: str
    title: str
    timezone: str
    weekday: int
    hour: int
    minute: int
    reminder_id: str
    status: HabitStatus = HabitStatus.ACTIVE
    priority: str = "normal"  # "normal" | "high"
    escalation_enabled: bool = False
    escalation_step: int = 0  # index into ESCALATION_ORDER
    completed_this_cycle: bool = False
    created_at: Optional[datetime] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def current_channel(self) -> EscalationChannel:
        idx = max(0, min(self.escalation_step, len(ESCALATION_ORDER) - 1))
        return ESCALATION_ORDER[idx]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "timezone": self.timezone,
            "weekday": self.weekday,
            "hour": self.hour,
            "minute": self.minute,
            "reminder_id": self.reminder_id,
            "status": self.status.value,
            "priority": self.priority,
            "escalation_enabled": self.escalation_enabled,
            "escalation_step": self.escalation_step,
            "completed_this_cycle": self.completed_this_cycle,
            "created_at": _fmt_dt(self.created_at),
            "meta": dict(self.meta),
            "current_channel": self.current_channel().value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Habit":
        return cls(
            id=data["id"],
            title=data["title"],
            timezone=data["timezone"],
            weekday=int(data["weekday"]),
            hour=int(data["hour"]),
            minute=int(data["minute"]),
            reminder_id=data["reminder_id"],
            status=HabitStatus(data.get("status") or HabitStatus.ACTIVE.value),
            priority=data.get("priority") or "normal",
            escalation_enabled=bool(data.get("escalation_enabled")),
            escalation_step=int(data.get("escalation_step") or 0),
            completed_this_cycle=bool(data.get("completed_this_cycle")),
            created_at=_parse_dt(data.get("created_at")),
            meta=dict(data.get("meta") or {}),
        )


class ReminderStore:
    """Create / list / snooze / cancel reminders + habit schedules."""

    def __init__(self, persist_path: Path | str | None = None) -> None:
        self.persist_path = Path(persist_path) if persist_path else None
        self.reminders: dict[str, Reminder] = {}
        self.habits: dict[str, Habit] = {}
        if self.persist_path and self.persist_path.is_file():
            self._load()

    def create(
        self,
        *,
        text: str,
        timezone: str,
        kind: ReminderKind | str,
        due_at: datetime,
        created_at: datetime,
        hour: int = 0,
        minute: int = 0,
        weekday: Optional[int] = None,
        channel: str = "whatsapp",
        recipient: str = "",
        habit_id: Optional[str] = None,
        meta: dict[str, Any] | None = None,
        reminder_id: str | None = None,
    ) -> Reminder:
        kind_e = ReminderKind(kind) if not isinstance(kind, ReminderKind) else kind
        rem = Reminder(
            id=reminder_id or f"rem-{uuid4().hex[:12]}",
            text=text,
            timezone=timezone,
            kind=kind_e,
            status=ReminderStatus.ACTIVE,
            due_at=due_at,
            created_at=created_at,
            hour=hour,
            minute=minute,
            weekday=weekday,
            channel=channel,
            recipient=recipient,
            habit_id=habit_id,
            meta=dict(meta or {}),
        )
        self.reminders[rem.id] = rem
        self._save()
        return rem

    def create_habit(
        self,
        *,
        title: str,
        timezone: str,
        weekday: int,
        hour: int,
        minute: int,
        due_at: datetime,
        created_at: datetime,
        priority: str = "normal",
        escalation_enabled: bool = False,
        recipient: str = "",
        meta: dict[str, Any] | None = None,
    ) -> tuple[Habit, Reminder]:
        rem = self.create(
            text=title,
            timezone=timezone,
            kind=ReminderKind.RECURRING,
            due_at=due_at,
            created_at=created_at,
            hour=hour,
            minute=minute,
            weekday=weekday,
            recipient=recipient,
            meta={"habit_title": title, **(meta or {})},
        )
        habit = Habit(
            id=f"hab-{uuid4().hex[:12]}",
            title=title,
            timezone=timezone,
            weekday=weekday,
            hour=hour,
            minute=minute,
            reminder_id=rem.id,
            priority=priority,
            escalation_enabled=escalation_enabled,
            created_at=created_at,
            meta=dict(meta or {}),
        )
        rem.habit_id = habit.id
        self.habits[habit.id] = habit
        self._save()
        return habit, rem

    def get(self, reminder_id: str) -> Optional[Reminder]:
        return self.reminders.get(reminder_id)

    def get_habit(self, habit_id: str) -> Optional[Habit]:
        return self.habits.get(habit_id)

    def list_active(self) -> list[Reminder]:
        return [
            r
            for r in self.reminders.values()
            if r.status in {ReminderStatus.ACTIVE, ReminderStatus.SNOOZED}
        ]

    def due(self, now: datetime) -> list[Reminder]:
        """Reminders whose due_at <= now and still actionable."""
        out: list[Reminder] = []
        for rem in self.reminders.values():
            if rem.status == ReminderStatus.CANCELLED:
                continue
            if rem.status == ReminderStatus.COMPLETED:
                continue
            if rem.status == ReminderStatus.FIRED and rem.kind == ReminderKind.ONE_SHOT:
                continue
            effective = rem.snooze_until or rem.due_at
            # Compare in absolute instants.
            if effective <= now:
                out.append(rem)
        out.sort(key=lambda r: r.due_at)
        return out

    def snooze(self, reminder_id: str, until: datetime) -> Reminder:
        rem = self.reminders[reminder_id]
        if rem.status == ReminderStatus.CANCELLED:
            raise ValueError("cannot snooze cancelled reminder")
        rem.status = ReminderStatus.SNOOZED
        rem.snooze_until = until
        rem.due_at = until
        self._save()
        return rem

    def cancel(self, reminder_id: str) -> Reminder:
        rem = self.reminders[reminder_id]
        rem.status = ReminderStatus.CANCELLED
        rem.snooze_until = None
        if rem.habit_id and rem.habit_id in self.habits:
            self.habits[rem.habit_id].status = HabitStatus.CANCELLED
        self._save()
        return rem

    def mark_completed(self, reminder_id: str) -> Reminder:
        rem = self.reminders[reminder_id]
        rem.status = ReminderStatus.COMPLETED
        if rem.habit_id and rem.habit_id in self.habits:
            self.habits[rem.habit_id].completed_this_cycle = True
            self.habits[rem.habit_id].escalation_step = 0
        self._save()
        return rem

    def mark_fired(self, reminder_id: str, fired_at: datetime) -> Reminder:
        rem = self.reminders[reminder_id]
        rem.fire_count += 1
        rem.last_fired_at = fired_at
        rem.snooze_until = None
        if rem.kind == ReminderKind.ONE_SHOT:
            rem.status = ReminderStatus.FIRED
        else:
            rem.status = ReminderStatus.ACTIVE
            if rem.weekday is None:
                raise ValueError(f"recurring reminder {reminder_id} missing weekday")
            rem.due_at = next_weekly_after(
                rem.due_at,
                weekday=rem.weekday,
                hour=rem.hour,
                minute=rem.minute,
            )
            if rem.habit_id and rem.habit_id in self.habits:
                habit = self.habits[rem.habit_id]
                if not habit.completed_this_cycle and habit.escalation_enabled:
                    # Advance ladder for next miss cycle (WhatsApp already sent this fire).
                    if habit.escalation_step < len(ESCALATION_ORDER) - 1:
                        habit.escalation_step += 1
                habit.completed_this_cycle = False
        self._save()
        return rem

    def to_dict(self) -> dict[str, Any]:
        return {
            "reminders": [r.to_dict() for r in self.reminders.values()],
            "habits": [h.to_dict() for h in self.habits.values()],
        }

    def _save(self) -> None:
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist_path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load(self) -> None:
        assert self.persist_path is not None
        data = json.loads(self.persist_path.read_text(encoding="utf-8"))
        self.reminders = {
            r["id"]: Reminder.from_dict(r) for r in data.get("reminders", [])
        }
        self.habits = {h["id"]: Habit.from_dict(h) for h in data.get("habits", [])}
