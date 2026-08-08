"""Calendar service — soft-confirm creates; conflict-aware proposals; reads Auto."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from capabilities.calendar.parse import ParsedCalendarEvent, parse_schedule
from capabilities.calendar.store import CalendarEvent, CalendarStore, Conflict, FreeSlot
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import ApprovalTier, tier_for


@dataclass
class ProposeCalendarResult:
    ok: bool
    parsed: Optional[ParsedCalendarEvent]
    approval_id: Optional[str]
    tier: str
    reason: str
    confirm_body: str
    conflicts: list[Conflict] = field(default_factory=list)
    suggestions: list[FreeSlot] = field(default_factory=list)
    gateway_result: Optional[ProposeResult] = None
    executed: bool = False


def _format_propose(
    parsed: ParsedCalendarEvent,
    *,
    conflicts: list[Conflict],
    suggestions: list[FreeSlot],
) -> str:
    when = f"{parsed.start.strftime('%A %Y-%m-%d %H:%M')}–{parsed.end.strftime('%H:%M')}"
    body = f"Proposed: {parsed.title} on {when} ({parsed.timezone}). Soft confirm required."
    if conflicts:
        names = ", ".join(c.existing_title for c in conflicts)
        body += f" Conflict with: {names}."
        if suggestions:
            alt = suggestions[0]
            body += (
                f" Suggested free: {alt.start.strftime('%H:%M')}–{alt.end.strftime('%H:%M')}."
            )
    return body


class CalendarService:
    """Propose calendar creates (Soft confirm) and read availability (Auto)."""

    def __init__(
        self,
        store: CalendarStore,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        *,
        gateway: ActionGateway | None = None,
        timezone: str = "UTC",
        recipient: str = "",
        suggest_limit: int = 3,
    ) -> None:
        self.store = store
        self.clock = clock
        self.catcher = catcher
        self.gateway = gateway
        self.timezone = timezone
        self.recipient = recipient
        self.suggest_limit = suggest_limit
        if self.gateway is not None:
            # Share store with adapter so Accept writes land in the same place.
            self.gateway.calendar.attach_store(self.store)

    def list_upcoming(self, *, limit: int = 20) -> list[CalendarEvent]:
        return self.store.upcoming(self.clock.now(), limit=limit)

    def find_conflicts(
        self,
        start: datetime,
        end: datetime,
        *,
        title: str = "",
    ) -> list[Conflict]:
        return self.store.find_conflicts(start, end, title=title)

    def suggest_free_slots(
        self,
        *,
        day: datetime,
        duration: timedelta,
        window_start_hour: int = 9,
        window_end_hour: int = 18,
        limit: int | None = None,
    ) -> list[FreeSlot]:
        day_start = day.replace(hour=window_start_hour, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=window_end_hour, minute=0, second=0, microsecond=0)
        return self.store.suggest_free_slots(
            day_start=day_start,
            day_end=day_end,
            duration=duration,
            limit=limit if limit is not None else self.suggest_limit,
        )

    def propose_from_utterance(
        self,
        utterance: str,
        *,
        timezone: str | None = None,
        recipient: str | None = None,
        source_channel: str = "whatsapp",
    ) -> ProposeCalendarResult:
        """Parse NL schedule → pending soft confirm. Adapter create_count stays 0."""
        tz = timezone or self.timezone
        to = recipient if recipient is not None else self.recipient
        now = self.clock.now()
        tier = tier_for("calendar_create")
        if tier != ApprovalTier.SOFT_CONFIRM:
            return ProposeCalendarResult(
                ok=False,
                parsed=None,
                approval_id=None,
                tier=tier.value,
                reason=f"expected_soft_confirm_got_{tier.value}",
                confirm_body="",
            )

        try:
            parsed = parse_schedule(utterance, now=now, timezone=tz)
        except ValueError as exc:
            return ProposeCalendarResult(
                ok=False,
                parsed=None,
                approval_id=None,
                tier=tier.value,
                reason=f"parse_error:{exc}",
                confirm_body="",
            )

        conflicts = self.store.find_conflicts(
            parsed.start, parsed.end, title=parsed.title
        )
        duration = parsed.end - parsed.start
        suggestions: list[FreeSlot] = []
        if conflicts:
            suggestions = self.suggest_free_slots(day=parsed.start, duration=duration)

        payload: dict[str, Any] = {
            "title": parsed.title,
            "start": parsed.start.isoformat(),
            "end": parsed.end.isoformat(),
            "timezone": parsed.timezone,
            "weekday": parsed.weekday,
            "recipient": to,
            "conflicts": [c.to_dict() for c in conflicts],
            "suggestions": [s.to_dict() for s in suggestions],
        }

        summary = f"Create calendar event: {parsed.title}"
        if conflicts:
            summary += f" (conflicts: {len(conflicts)})"

        confirm = _format_propose(parsed, conflicts=conflicts, suggestions=suggestions)

        if self.gateway is None:
            return ProposeCalendarResult(
                ok=False,
                parsed=parsed,
                approval_id=None,
                tier=tier.value,
                reason="gateway_required_for_soft_confirm",
                confirm_body=confirm,
                conflicts=conflicts,
                suggestions=suggestions,
            )

        create_before = self.gateway.calendar.create_count
        gw_result = self.gateway.propose(
            "calendar_create",
            summary,
            payload,
            source_channel=source_channel,
            source_utterance=utterance,
        )

        # Soft confirm must NOT execute — INV-APPR-003.
        if not gw_result.ok:
            return ProposeCalendarResult(
                ok=False,
                parsed=parsed,
                approval_id=gw_result.approval_id,
                tier=gw_result.tier or tier.value,
                reason=gw_result.reason,
                confirm_body="",
                conflicts=conflicts,
                suggestions=suggestions,
                gateway_result=gw_result,
                executed=gw_result.executed,
            )

        create_leaked = (
            gw_result.executed or self.gateway.calendar.create_count != create_before
        )
        if create_leaked:
            return ProposeCalendarResult(
                ok=False,
                parsed=parsed,
                approval_id=gw_result.approval_id,
                tier=gw_result.tier or tier.value,
                reason="soft_confirm_leaked_create",
                confirm_body="",
                conflicts=conflicts,
                suggestions=suggestions,
                gateway_result=gw_result,
                executed=True,
            )

        self.catcher.send(
            "whatsapp",
            to or "owner",
            confirm,
            ts=now,
            kind="calendar_propose",
            approval_id=gw_result.approval_id,
            conflicts=len(conflicts),
        )

        return ProposeCalendarResult(
            ok=True,
            parsed=parsed,
            approval_id=gw_result.approval_id,
            tier=gw_result.tier or tier.value,
            reason="pending_soft_confirm",
            confirm_body=confirm,
            conflicts=conflicts,
            suggestions=suggestions,
            gateway_result=gw_result,
            executed=False,
        )

    def propose_event(
        self,
        *,
        title: str,
        start: datetime | str,
        end: datetime | str,
        summary: str | None = None,
        source_utterance: str | None = None,
        source_channel: str = "whatsapp",
        **payload_extra: Any,
    ) -> ProposeCalendarResult:
        """Direct soft-confirm propose (E2E-04 / Android inbox hooks)."""
        tier = tier_for("calendar_create")
        start_dt = start if isinstance(start, datetime) else datetime.fromisoformat(str(start))
        end_dt = end if isinstance(end, datetime) else datetime.fromisoformat(str(end))
        conflicts = self.store.find_conflicts(start_dt, end_dt, title=title)
        duration = end_dt - start_dt
        suggestions = (
            self.suggest_free_slots(day=start_dt, duration=duration) if conflicts else []
        )
        payload: dict[str, Any] = {
            "title": title,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "conflicts": [c.to_dict() for c in conflicts],
            "suggestions": [s.to_dict() for s in suggestions],
            **payload_extra,
        }
        if self.gateway is None:
            return ProposeCalendarResult(
                ok=False,
                parsed=None,
                approval_id=None,
                tier=tier.value,
                reason="gateway_required_for_soft_confirm",
                confirm_body="",
                conflicts=conflicts,
                suggestions=suggestions,
            )
        create_before = self.gateway.calendar.create_count
        gw_result = self.gateway.propose(
            "calendar_create",
            summary or f"Create calendar event: {title}",
            payload,
            source_channel=source_channel,
            source_utterance=source_utterance,
        )
        create_leaked = (
            gw_result.executed or self.gateway.calendar.create_count != create_before
        )
        return ProposeCalendarResult(
            ok=bool(gw_result.ok and gw_result.approval_id and not create_leaked),
            parsed=None,
            approval_id=gw_result.approval_id,
            tier=gw_result.tier or tier.value,
            reason=(
                "soft_confirm_leaked_create"
                if create_leaked
                else ("pending_soft_confirm" if gw_result.ok else gw_result.reason)
            ),
            confirm_body=summary or f"Create calendar event: {title}",
            conflicts=conflicts,
            suggestions=suggestions,
            gateway_result=gw_result,
            executed=gw_result.executed,
        )
