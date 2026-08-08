"""Booking service — stub portal slots → hard approve → book + calendar writeback."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from capabilities.bookings.parse import ParsedBookingRequest, looks_like_booking, parse_booking
from capabilities.bookings.portal import PortalSlot, StubBooksyPortal
from capabilities.bookings.store import BookingStatus, BookingStore, BookingTask
from capabilities.calendar.store import CalendarStore
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import ApprovalTier, tier_for

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PORTAL_FIXTURE = ROOT / "fixtures" / "browser" / "booksy-stub-slots.json"


@dataclass
class ProposeBookingResult:
    ok: bool
    parsed: Optional[ParsedBookingRequest]
    approval_id: Optional[str]
    task_id: Optional[str]
    tier: str
    reason: str
    confirm_body: str
    options: list[dict[str, Any]] = field(default_factory=list)
    gateway_result: Optional[ProposeResult] = None
    executed: bool = False
    book_count_at_propose: int = 0


def _format_options(options: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, opt in enumerate(options, start=1):
        start = datetime.fromisoformat(str(opt["start"]))
        end = datetime.fromisoformat(str(opt["end"]))
        lines.append(
            f"  {i}) {start.strftime('%A %Y-%m-%d %H:%M')}–{end.strftime('%H:%M')}"
            + (f" ({opt.get('stylist')})" if opt.get("stylist") else "")
        )
    return "\n".join(lines)


def _format_propose(
    *,
    shop: str,
    service: str,
    options: list[dict[str, Any]],
    estimated_price: float | None,
    currency: str,
    cancellation_policy: str,
) -> str:
    price = ""
    if estimated_price is not None:
        price = f" ~{estimated_price:g} {currency}"
    body = (
        f"Proposed booking: {service} at {shop}{price}. "
        f"Hard approve required.\nOptions:\n{_format_options(options)}"
    )
    if cancellation_policy:
        body += f"\nCancel policy: {cancellation_policy}"
    return body


class BookingService:
    """Propose Booksy stub slots (Hard approve). Execute only after Accept."""

    def __init__(
        self,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        *,
        gateway: ActionGateway | None = None,
        calendar_store: CalendarStore | None = None,
        portal: StubBooksyPortal | None = None,
        store: BookingStore | None = None,
        timezone: str = "UTC",
        recipient: str = "",
        option_limit: int = 3,
        portal_fixture: Path | str | None = None,
    ) -> None:
        self.clock = clock
        self.catcher = catcher
        self.gateway = gateway
        self.calendar_store = calendar_store if calendar_store is not None else CalendarStore()
        self.store = store if store is not None else BookingStore()
        self.timezone = timezone
        self.recipient = recipient
        self.option_limit = option_limit
        if portal is not None:
            self.portal = portal
        else:
            fixture = Path(portal_fixture) if portal_fixture else DEFAULT_PORTAL_FIXTURE
            self.portal = (
                StubBooksyPortal.from_fixture(fixture)
                if fixture.is_file()
                else StubBooksyPortal()
            )
        if self.gateway is not None:
            self.gateway.calendar.attach_store(self.calendar_store)
            self.gateway.attach_bookings(self.store, outbound=self.catcher)

    def propose_from_utterance(
        self,
        utterance: str,
        *,
        timezone: str | None = None,
        recipient: str | None = None,
        source_channel: str = "whatsapp",
        chosen_slot_index: int = 0,
    ) -> ProposeBookingResult:
        """Parse NL → stub slots → pending hard approve. book_count stays 0."""
        tz = timezone or self.timezone
        to = recipient if recipient is not None else self.recipient
        now = self.clock.now()
        tier = tier_for("book")
        if tier != ApprovalTier.HARD_APPROVE:
            return ProposeBookingResult(
                ok=False,
                parsed=None,
                approval_id=None,
                task_id=None,
                tier=tier.value,
                reason=f"expected_hard_approve_got_{tier.value}",
                confirm_body="",
            )

        try:
            parsed = parse_booking(utterance, now=now, timezone=tz)
        except ValueError as exc:
            return ProposeBookingResult(
                ok=False,
                parsed=None,
                approval_id=None,
                task_id=None,
                tier=tier.value,
                reason=f"parse_error:{exc}",
                confirm_body="",
            )

        return self.propose_for_request(
            parsed,
            recipient=to,
            source_channel=source_channel,
            source_utterance=utterance,
            chosen_slot_index=chosen_slot_index,
        )

    def propose_for_request(
        self,
        parsed: ParsedBookingRequest,
        *,
        recipient: str = "",
        source_channel: str = "whatsapp",
        source_utterance: str | None = None,
        chosen_slot_index: int = 0,
    ) -> ProposeBookingResult:
        tier = tier_for("book")
        card = self.portal.shop_card()
        raw_slots = self.portal.list_slots(
            window_start=parsed.window_start,
            window_end=parsed.window_end,
            period=parsed.period,
            limit=max(self.option_limit * 2, 6),
        )
        # Prefer slots that do not conflict with calendar.
        free_slots: list[PortalSlot] = []
        for slot in raw_slots:
            conflicts = self.calendar_store.find_conflicts(
                slot.start, slot.end, title=f"{parsed.service} @ {card['shop']}"
            )
            if not conflicts:
                free_slots.append(slot)
            if len(free_slots) >= self.option_limit:
                break

        if not free_slots:
            # Fall back to portal slots even if busy — still no execute; surface conflict.
            free_slots = raw_slots[: self.option_limit]

        if not free_slots:
            return ProposeBookingResult(
                ok=False,
                parsed=parsed,
                approval_id=None,
                task_id=None,
                tier=tier.value,
                reason="no_slots_available",
                confirm_body="",
            )

        options: list[dict[str, Any]] = []
        for slot in free_slots[: self.option_limit]:
            options.append(
                {
                    **slot.to_dict(),
                    "shop": card["shop"],
                    "service": parsed.service or card["service"],
                    "stylist": card["stylist"],
                    "estimated_price": card["estimated_price"],
                    "currency": card["currency"],
                    "cancellation_policy": card["cancellation_policy"],
                }
            )

        idx = max(0, min(chosen_slot_index, len(options) - 1))
        chosen = options[idx]
        task = self.store.create(
            shop=str(card["shop"]),
            service=str(parsed.service or card["service"]),
            options=options,
            status=BookingStatus.PROPOSED,
            chosen_slot_index=idx,
            created_at=self.clock.now(),
            meta={"period": parsed.period, "timezone": parsed.timezone},
        )

        payload: dict[str, Any] = {
            "booking_task_id": task.id,
            "shop": card["shop"],
            "shop_url": card["shop_url"],
            "service": parsed.service or card["service"],
            "stylist": card["stylist"],
            "estimated_price": card["estimated_price"],
            "currency": card["currency"],
            "cancellation_policy": card["cancellation_policy"],
            "duration_minutes": card["duration_minutes"],
            "options": options,
            "chosen_slot_index": idx,
            "start": chosen["start"],
            "end": chosen["end"],
            "slot_id": chosen.get("id"),
            "timezone": parsed.timezone,
            "recipient": recipient,
            "calendar_title": f"{parsed.service or card['service']} @ {card['shop']}",
        }

        summary = (
            f"Book {payload['service']} at {payload['shop']} "
            f"on {datetime.fromisoformat(str(chosen['start'])).strftime('%a %Y-%m-%d %H:%M')}"
        )
        confirm = _format_propose(
            shop=str(card["shop"]),
            service=str(payload["service"]),
            options=options,
            estimated_price=float(card["estimated_price"]) if card.get("estimated_price") is not None else None,
            currency=str(card["currency"]),
            cancellation_policy=str(card["cancellation_policy"] or ""),
        )

        if self.gateway is None:
            return ProposeBookingResult(
                ok=False,
                parsed=parsed,
                approval_id=None,
                task_id=task.id,
                tier=tier.value,
                reason="gateway_required_for_hard_approve",
                confirm_body=confirm,
                options=options,
            )

        book_before = self.gateway.commerce.book_count
        gw_result = self.gateway.propose(
            "book",
            summary,
            payload,
            estimated_cost=float(card["estimated_price"] or 0),
            source_channel=source_channel,
            source_utterance=source_utterance or parsed.raw,
        )

        if not gw_result.ok or not gw_result.approval_id:
            return ProposeBookingResult(
                ok=False,
                parsed=parsed,
                approval_id=gw_result.approval_id,
                task_id=task.id,
                tier=gw_result.tier or tier.value,
                reason=gw_result.reason,
                confirm_body="",
                options=options,
                gateway_result=gw_result,
                executed=gw_result.executed,
                book_count_at_propose=self.gateway.commerce.book_count,
            )

        # Hard approve must NOT execute — INV-BOOK-001.
        leaked = (
            gw_result.executed or self.gateway.commerce.book_count != book_before
        )
        if leaked:
            return ProposeBookingResult(
                ok=False,
                parsed=parsed,
                approval_id=gw_result.approval_id,
                task_id=task.id,
                tier=gw_result.tier or tier.value,
                reason="hard_approve_leaked_book",
                confirm_body="",
                options=options,
                gateway_result=gw_result,
                executed=True,
                book_count_at_propose=self.gateway.commerce.book_count,
            )

        self.store.set_approval(task.id, gw_result.approval_id, at=self.clock.now())

        self.catcher.send(
            "whatsapp",
            recipient or "owner",
            confirm,
            ts=self.clock.now(),
            kind="booking_propose",
            approval_id=gw_result.approval_id,
            booking_task_id=task.id,
            options=len(options),
        )

        return ProposeBookingResult(
            ok=True,
            parsed=parsed,
            approval_id=gw_result.approval_id,
            task_id=task.id,
            tier=gw_result.tier or tier.value,
            reason="pending_hard_approve",
            confirm_body=confirm,
            options=options,
            gateway_result=gw_result,
            executed=False,
            book_count_at_propose=self.gateway.commerce.book_count,
        )

    def mark_denied_for_approval(self, approval_id: str) -> Optional[BookingTask]:
        for task in self.store.list_all():
            if task.approval_id == approval_id:
                return self.store.mark_denied(task.id, at=self.clock.now())
        return None


# Re-export helpers used by VirtualUser routing.
__all__ = [
    "BookingService",
    "ProposeBookingResult",
    "looks_like_booking",
    "parse_booking",
]
