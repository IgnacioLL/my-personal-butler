"""Habit escalation ladder — WhatsApp → Android → outbound call (E2E-02).

Hooks the three delivery channels so a missed high-priority habit climbs
the ladder on each fire without completion. Call step uses MockVoiceProvider
and queues an after-call WhatsApp summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from capabilities.reminders.store import (
    EscalationChannel,
    Habit,
    Reminder,
    ReminderStore,
)
from channels.android.notifications import AndroidNotificationCatcher
from channels.voice.provider import CallSession, MockVoiceProvider
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher


@dataclass
class EscalationDelivery:
    channel: str
    body: str
    emitted: bool
    reason: str
    reminder_id: str
    habit_id: Optional[str] = None
    escalation_step: Optional[int] = None
    call_id: Optional[str] = None
    notification_id: Optional[str] = None
    summary_queued: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "body": self.body,
            "emitted": self.emitted,
            "reason": self.reason,
            "reminder_id": self.reminder_id,
            "habit_id": self.habit_id,
            "escalation_step": self.escalation_step,
            "call_id": self.call_id,
            "notification_id": self.notification_id,
            "summary_queued": self.summary_queued,
            "meta": dict(self.meta),
        }


def format_escalation_body(rem: Reminder, habit: Habit | None) -> str:
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


class EscalationLadder:
    """Deliver habit fire via current escalation channel; advance on miss."""

    def __init__(
        self,
        store: ReminderStore,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        *,
        voice: MockVoiceProvider | None = None,
        android: AndroidNotificationCatcher | None = None,
        default_recipient: str = "",
        auto_complete_call: bool = True,
    ) -> None:
        self.store = store
        self.clock = clock
        self.catcher = catcher
        self.voice = voice or MockVoiceProvider(
            catcher, clock, default_to=default_recipient
        )
        self.android = android or AndroidNotificationCatcher(
            clock, catcher, default_to=default_recipient or "owner"
        )
        self.default_recipient = default_recipient
        self.auto_complete_call = auto_complete_call
        self.deliveries: list[EscalationDelivery] = []

    def deliver(
        self,
        rem: Reminder,
        habit: Habit | None = None,
        *,
        mark_fired: bool = True,
    ) -> EscalationDelivery:
        """Send via current channel for *habit* (or WhatsApp for plain reminders)."""
        now = self.clock.now()
        resolved = habit
        if resolved is None and rem.habit_id:
            resolved = self.store.get_habit(rem.habit_id)

        to = rem.recipient or self.default_recipient or "owner"
        body = format_escalation_body(rem, resolved)

        if resolved is not None and resolved.escalation_enabled:
            channel = resolved.current_channel()
            step = resolved.escalation_step
            if channel is EscalationChannel.WHATSAPP:
                delivery = self._deliver_whatsapp(
                    rem, resolved, to=to, body=body, now=now, step=step
                )
            elif channel is EscalationChannel.ANDROID:
                delivery = self._deliver_android(
                    rem, resolved, to=to, body=body, now=now, step=step
                )
            elif channel is EscalationChannel.CALL:
                delivery = self._deliver_call(
                    rem, resolved, to=to, body=body, now=now, step=step
                )
            else:
                exhaustive: never = channel
                raise RuntimeError(f"unhandled escalation channel: {exhaustive!r}")
        else:
            delivery = self._deliver_whatsapp(
                rem, resolved, to=to, body=body, now=now, step=None
            )

        if mark_fired:
            self.store.mark_fired(rem.id, now)
        self.deliveries.append(delivery)
        return delivery

    def run_ladder_until_call(
        self,
        habit_id: str,
        *,
        advance_fn,
    ) -> list[EscalationDelivery]:
        """Test helper: advance clock through WhatsApp → Android → call touches.

        *advance_fn* should advance FakeClock to the next due and return due reminders
        (typically scheduler.advance / advance_to). Returns ordered deliveries.
        """
        out: list[EscalationDelivery] = []
        habit = self.store.get_habit(habit_id)
        if habit is None:
            raise KeyError(f"unknown habit: {habit_id}")

        # Expect up to 3 steps (WA, Android, Call).
        for _ in range(len(EscalationChannel)):
            due_list = advance_fn()
            for rem in due_list:
                if rem.habit_id != habit_id:
                    continue
                h = self.store.get_habit(habit_id)
                delivery = self.deliver(rem, h, mark_fired=True)
                out.append(delivery)
                if delivery.channel == EscalationChannel.CALL.value:
                    return out
        return out

    def channel_touch_order(self) -> list[str]:
        return [d.channel for d in self.deliveries if d.emitted]

    def _deliver_whatsapp(
        self,
        rem: Reminder,
        habit: Habit | None,
        *,
        to: str,
        body: str,
        now: datetime,
        step: int | None,
    ) -> EscalationDelivery:
        self.catcher.send(
            "whatsapp",
            to,
            body,
            ts=now,
            kind="reminder_fire",
            reminder_id=rem.id,
            habit_id=habit.id if habit else None,
            escalation_step=step,
        )
        return EscalationDelivery(
            channel=EscalationChannel.WHATSAPP.value,
            body=body,
            emitted=True,
            reason="ok",
            reminder_id=rem.id,
            habit_id=habit.id if habit else None,
            escalation_step=step,
        )

    def _deliver_android(
        self,
        rem: Reminder,
        habit: Habit | None,
        *,
        to: str,
        body: str,
        now: datetime,
        step: int | None,
    ) -> EscalationDelivery:
        title = f"Habit: {rem.text}" if habit else "Reminder"
        note = self.android.notify(
            title,
            body,
            to=to,
            reminder_id=rem.id,
            habit_id=habit.id if habit else None,
            ts=now,
            escalation_step=step,
        )
        return EscalationDelivery(
            channel=EscalationChannel.ANDROID.value,
            body=body,
            emitted=True,
            reason="ok",
            reminder_id=rem.id,
            habit_id=habit.id if habit else None,
            escalation_step=step,
            notification_id=note.id,
        )

    def _deliver_call(
        self,
        rem: Reminder,
        habit: Habit | None,
        *,
        to: str,
        body: str,
        now: datetime,
        step: int | None,
    ) -> EscalationDelivery:
        _ = now  # call uses voice.clock
        if self.auto_complete_call:
            session: CallSession = self.voice.place_and_complete(
                to=to,
                script=body,
                reminder_id=rem.id,
                habit_id=habit.id if habit else None,
                outcome="reminder_delivered",
                meta={"escalation_step": step},
            )
            return EscalationDelivery(
                channel=EscalationChannel.CALL.value,
                body=body,
                emitted=True,
                reason="ok",
                reminder_id=rem.id,
                habit_id=habit.id if habit else None,
                escalation_step=step,
                call_id=session.id,
                summary_queued=session.summary_queued,
            )

        session = self.voice.place_call(
            to=to,
            script=body,
            reminder_id=rem.id,
            habit_id=habit.id if habit else None,
            meta={"escalation_step": step},
        )
        return EscalationDelivery(
            channel=EscalationChannel.CALL.value,
            body=body,
            emitted=True,
            reason="ok",
            reminder_id=rem.id,
            habit_id=habit.id if habit else None,
            escalation_step=step,
            call_id=session.id,
            summary_queued=False,
        )
