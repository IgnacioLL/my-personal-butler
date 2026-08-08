"""High-level reminder create flow: parse → auto-approve → store → confirm outbound."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from capabilities.reminders.parse import ParsedReminder, parse_reminder
from capabilities.reminders.store import Habit, Reminder, ReminderKind, ReminderStore
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import ApprovalTier, tier_for


@dataclass
class CreateReminderResult:
    ok: bool
    reminder: Optional[Reminder]
    parsed: Optional[ParsedReminder]
    confirm_body: str
    approval_id: Optional[str]
    tier: str
    reason: str
    habit: Optional[Habit] = None
    gateway_result: Optional[ProposeResult] = None


def _format_confirm(parsed: ParsedReminder) -> str:
    local = parsed.due_at
    when = local.strftime("%A %Y-%m-%d %H:%M")
    tz = parsed.timezone
    kind = "recurring weekly" if parsed.kind == "recurring" else "one-shot"
    return f"Got it — {kind} reminder set for {when} ({tz}): {parsed.body}"


class ReminderService:
    """Create one-shot / recurring reminders and habit schedules (Auto tier)."""

    def __init__(
        self,
        store: ReminderStore,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        *,
        gateway: ActionGateway | None = None,
        timezone: str = "UTC",
        recipient: str = "",
    ) -> None:
        self.store = store
        self.clock = clock
        self.catcher = catcher
        self.gateway = gateway
        self.timezone = timezone
        self.recipient = recipient
        # Share store so gateway auto-adapter and service see the same records.
        if self.gateway is not None:
            self.gateway.reminders = self.store

    def create_from_utterance(
        self,
        utterance: str,
        *,
        timezone: str | None = None,
        recipient: str | None = None,
        as_habit: bool = False,
        habit_priority: str = "normal",
        escalation_enabled: bool = False,
    ) -> CreateReminderResult:
        tz = timezone or self.timezone
        to = recipient if recipient is not None else self.recipient
        now = self.clock.now()

        # Auto tier — never create a hard approval for reminder_create.
        action_type = "habit_create" if as_habit else "reminder_create"
        tier = tier_for(action_type)
        if tier != ApprovalTier.AUTO:
            return CreateReminderResult(
                ok=False,
                reminder=None,
                parsed=None,
                confirm_body="",
                approval_id=None,
                tier=tier.value,
                reason=f"expected_auto_tier_got_{tier.value}",
            )

        try:
            parsed = parse_reminder(utterance, now=now, timezone=tz)
        except ValueError as exc:
            return CreateReminderResult(
                ok=False,
                reminder=None,
                parsed=None,
                confirm_body="",
                approval_id=None,
                tier=tier.value,
                reason=f"parse_error:{exc}",
            )

        payload: dict[str, Any] = {
            "text": parsed.body,
            "timezone": parsed.timezone,
            "kind": parsed.kind,
            "due_at": parsed.due_at.isoformat(),
            "weekday": parsed.weekday,
            "hour": parsed.hour,
            "minute": parsed.minute,
            "recipient": to,
            "as_habit": as_habit,
            "habit_priority": habit_priority,
            "escalation_enabled": escalation_enabled,
        }

        gw_result: ProposeResult | None = None
        rem: Reminder | None = None
        habit: Habit | None = None

        if self.gateway is not None:
            gw_result = self.gateway.propose(
                action_type,
                f"Create reminder: {parsed.body}",
                payload,
            )
            if not gw_result.ok or not gw_result.executed:
                return CreateReminderResult(
                    ok=False,
                    reminder=None,
                    parsed=parsed,
                    confirm_body="",
                    approval_id=gw_result.approval_id,
                    tier=gw_result.tier or tier.value,
                    reason=gw_result.reason,
                    gateway_result=gw_result,
                )
            if gw_result.approval_id is not None:
                return CreateReminderResult(
                    ok=False,
                    reminder=None,
                    parsed=parsed,
                    confirm_body="",
                    approval_id=gw_result.approval_id,
                    tier=gw_result.tier or tier.value,
                    reason="unexpected_approval_item_for_auto",
                    gateway_result=gw_result,
                )
            auto = gw_result.auto_result or {}
            rem_id = auto.get("reminder_id")
            rem = self.store.get(rem_id) if rem_id else None
            hab_id = auto.get("habit_id")
            habit = self.store.get_habit(hab_id) if hab_id else None
            if rem is None:
                return CreateReminderResult(
                    ok=False,
                    reminder=None,
                    parsed=parsed,
                    confirm_body="",
                    approval_id=None,
                    tier=tier.value,
                    reason="gateway_auto_missing_reminder",
                    gateway_result=gw_result,
                )
        elif as_habit:
            if parsed.weekday is None:
                return CreateReminderResult(
                    ok=False,
                    reminder=None,
                    parsed=parsed,
                    confirm_body="",
                    approval_id=None,
                    tier=tier.value,
                    reason="habit_requires_weekday",
                )
            habit, rem = self.store.create_habit(
                title=parsed.body,
                timezone=parsed.timezone,
                weekday=parsed.weekday,
                hour=parsed.hour,
                minute=parsed.minute,
                due_at=parsed.due_at,
                created_at=now,
                priority=habit_priority,
                escalation_enabled=escalation_enabled,
                recipient=to,
            )
        else:
            rem = self.store.create(
                text=parsed.body,
                timezone=parsed.timezone,
                kind=ReminderKind(parsed.kind),
                due_at=parsed.due_at,
                created_at=now,
                hour=parsed.hour,
                minute=parsed.minute,
                weekday=parsed.weekday,
                recipient=to,
            )

        confirm = _format_confirm(parsed)
        self.catcher.send(
            "whatsapp",
            to or "owner",
            confirm,
            ts=now,
            kind="reminder_confirm",
            reminder_id=rem.id,
            habit_id=habit.id if habit else None,
        )
        return CreateReminderResult(
            ok=True,
            reminder=rem,
            parsed=parsed,
            confirm_body=confirm,
            approval_id=None,
            tier=tier.value,
            reason="created",
            habit=habit,
            gateway_result=gw_result,
        )
