"""Android notification catcher — habit escalation step 2 (E2E-02).

Records local/push nudges without a live device. Outbound catcher also
mirrors channel=android for ordered channel-touch assertions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher


@dataclass
class AndroidNotification:
    id: str
    title: str
    body: str
    ts: str
    reminder_id: Optional[str] = None
    habit_id: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "ts": self.ts,
            "reminder_id": self.reminder_id,
            "habit_id": self.habit_id,
            "meta": dict(self.meta),
        }


class AndroidNotificationCatcher:
    """Spy for Android habit nudges (escalation ladder step 2)."""

    def __init__(
        self,
        clock: FakeClock,
        catcher: OutboundMessageCatcher | None = None,
        *,
        default_to: str = "owner",
    ) -> None:
        self.clock = clock
        self.catcher = catcher
        self.default_to = default_to
        self.notifications: list[AndroidNotification] = []

    def notify(
        self,
        title: str,
        body: str,
        *,
        to: str | None = None,
        reminder_id: str | None = None,
        habit_id: str | None = None,
        ts: datetime | None = None,
        **meta: Any,
    ) -> AndroidNotification:
        when = ts or self.clock.now()
        note = AndroidNotification(
            id=f"android-nudge-{uuid4().hex[:10]}",
            title=title,
            body=body,
            ts=when.isoformat(),
            reminder_id=reminder_id,
            habit_id=habit_id,
            meta=dict(meta),
        )
        self.notifications.append(note)
        if self.catcher is not None:
            self.catcher.send(
                "android",
                to or self.default_to,
                body,
                ts=when,
                kind="android_nudge",
                notification_id=note.id,
                reminder_id=reminder_id,
                habit_id=habit_id,
                title=title,
            )
        return note

    def count(self) -> int:
        return len(self.notifications)

    def clear(self) -> None:
        self.notifications.clear()

    def to_list(self) -> list[dict[str, Any]]:
        return [n.to_dict() for n in self.notifications]
