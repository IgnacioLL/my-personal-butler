"""Fake-clock cron: advance clock → fire due reminders → outbound catcher.

Never sleeps on the wall clock. Respects pause_agent kill switch for proactive emits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol

from capabilities.reminders.store import (
    EscalationChannel,
    Habit,
    Reminder,
    ReminderStore,
)
from harness.clock import Duration, FakeClock
from harness.outbound import OutboundMessage, OutboundMessageCatcher


class _PauseAware(Protocol):
    @property
    def is_paused(self) -> bool: ...


@dataclass
class FireEvent:
    reminder_id: str
    fired_at: datetime
    channel: str
    body: str
    emitted: bool
    reason: str
    habit_id: Optional[str] = None
    escalation_step: Optional[int] = None
    meta: dict[str, Any] = field(default_factory=dict)


def _format_fire_body(rem: Reminder, habit: Habit | None) -> str:
    if habit is None:
        return f"Reminder: {rem.text}"
    channel = habit.current_channel()
    if channel is EscalationChannel.WHATSAPP:
        return f"Habit reminder: {rem.text}"
    if channel is EscalationChannel.ANDROID:
        return f"Android nudge: {rem.text}"
    if channel is EscalationChannel.CALL:
        return f"Calling about: {rem.text}"
    exhaustive: never = channel
    raise RuntimeError(f"unhandled escalation channel: {exhaustive!r}")


class ReminderScheduler:
    """Tick / advance-driven reminder firer bound to FakeClock + outbound catcher."""

    def __init__(
        self,
        store: ReminderStore,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        *,
        kill: _PauseAware | None = None,
        default_recipient: str = "",
    ) -> None:
        self.store = store
        self.clock = clock
        self.catcher = catcher
        self.kill = kill
        self.default_recipient = default_recipient
        self.fires: list[FireEvent] = []

    def now(self) -> datetime:
        return self.clock.now()

    def advance(self, duration: Duration) -> list[FireEvent]:
        """Advance fake clock then fire anything now due. No wall-clock sleep."""
        self.clock.advance(duration)
        return self.tick()

    def advance_to(self, when: datetime) -> list[FireEvent]:
        """Jump clock forward to *when* (must be >= now) and fire due items."""
        now = self.clock.now()
        target = when if when.tzinfo else when.replace(tzinfo=now.tzinfo)
        if target < now:
            raise ValueError("advance_to cannot go backwards")
        delta = target - now
        # Avoid float second loss — use exact timedelta.
        self.clock.set(target)
        # Still run tick at the new time.
        _ = delta  # documented: we set absolute rather than advance for TZ edges
        return self.tick()

    def tick(self) -> list[FireEvent]:
        """Fire all reminders due at clock.now()."""
        now = self.clock.now()
        fired: list[FireEvent] = []

        if self.kill is not None and self.kill.is_paused:
            for rem in self.store.due(now):
                event = FireEvent(
                    reminder_id=rem.id,
                    fired_at=now,
                    channel=rem.channel,
                    body="",
                    emitted=False,
                    reason="pause_agent",
                    habit_id=rem.habit_id,
                )
                self.fires.append(event)
                fired.append(event)
            return fired

        for rem in list(self.store.due(now)):
            habit = self.store.get_habit(rem.habit_id) if rem.habit_id else None
            channel = rem.channel
            if habit is not None and habit.escalation_enabled:
                channel = habit.current_channel().value
            body = _format_fire_body(rem, habit)
            to = rem.recipient or self.default_recipient or "owner"
            step_used = habit.escalation_step if habit else None
            msg: OutboundMessage = self.catcher.send(
                channel,
                to,
                body,
                ts=now,
                kind="reminder_fire",
                reminder_id=rem.id,
                habit_id=rem.habit_id,
                reminder_kind=rem.kind.value,
            )

            self.store.mark_fired(rem.id, now)
            event = FireEvent(
                reminder_id=rem.id,
                fired_at=now,
                channel=channel,
                body=body,
                emitted=True,
                reason="ok",
                habit_id=rem.habit_id,
                escalation_step=step_used,
                meta={"outbound_ts": msg.ts},
            )
            self.fires.append(event)
            fired.append(event)
        return fired

    def emitted_count(self) -> int:
        return sum(1 for f in self.fires if f.emitted)
