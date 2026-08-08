"""INV-BOOK-001 — Booking adapter execute count stays 0 until Accept."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capabilities.bookings.service import BookingService
from channels.android.approvals import AndroidApprovalInboxApi
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus, ApprovalTier

INV_ID = "INV-BOOK-001"
DESCRIPTION = "Booking adapter execute count stays 0 until Accept"

ROOT = Path(__file__).resolve().parents[2]


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    gw = ActionGateway(clock=clock)
    svc = BookingService(
        clock=clock,
        catcher=catcher,
        gateway=gw,
        timezone="Europe/Madrid",
        recipient="+15550001111",
        portal_fixture=ROOT / "fixtures" / "browser" / "booksy-stub-slots.json",
    )

    # Direct bypass must not touch book adapter.
    bypass = gw.try_hard_action_without_approval(
        "book", {"shop": "x", "start": "2026-01-12T14:00:00+01:00", "end": "2026-01-12T14:45:00+01:00"}
    )
    if bypass.ok:
        failures.append("bypass book succeeded")
    if gw.commerce.book_count != 0:
        failures.append(f"bypass leaked book_count={gw.commerce.book_count}")

    proposed = svc.propose_from_utterance("Book a haircut next week afternoon.")
    if not proposed.ok or not proposed.approval_id:
        failures.append(f"propose failed: {proposed.reason}")
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}

    if proposed.tier != ApprovalTier.HARD_APPROVE.value:
        failures.append(f"expected hard_approve, got {proposed.tier}")
    if gw.commerce.book_count != 0:
        failures.append(f"propose leaked book_count={gw.commerce.book_count}")
    if len(proposed.options) < 2 or len(proposed.options) > 3:
        failures.append(f"expected 2–3 options, got {len(proposed.options)}")

    # Execute while pending must fail; count stays 0.
    pending_exec = gw.execute(proposed.approval_id)
    if pending_exec.ok:
        failures.append("execute while pending succeeded")
    if gw.commerce.book_count != 0:
        failures.append(f"pending execute leaked book_count={gw.commerce.book_count}")

    item = gw.approvals.get(proposed.approval_id)
    if item is None or item.status != ApprovalStatus.PENDING:
        failures.append(
            f"expected pending, got {item.status.value if item else None}"
        )

    # Accept → exactly one book execute.
    inbox = AndroidApprovalInboxApi(gw)
    accepted = inbox.accept(proposed.approval_id)
    if not accepted.ok:
        failures.append(f"accept failed: {accepted.reason}")
    if gw.commerce.book_count != 1:
        failures.append(f"after accept book_count={gw.commerce.book_count} (want 1)")

    # Second execute blocked (already executed).
    again = gw.execute(proposed.approval_id)
    if again.ok:
        failures.append("second execute succeeded")
    if gw.commerce.book_count != 1:
        failures.append(f"double execute book_count={gw.commerce.book_count}")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            f"book_count=0 until Accept; after Accept book_count=1; "
            f"options={len(proposed.options)}"
        ),
    }
