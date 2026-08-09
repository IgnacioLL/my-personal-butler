"""INV-BOOK-002 — Failed booking cannot mark the user-facing task as success."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capabilities.bookings.service import BookingService
from capabilities.bookings.store import BookingStatus
from channels.android.approvals import AndroidApprovalInboxApi
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus

INV_ID = "INV-BOOK-002"
DESCRIPTION = "Failed booking cannot mark the user-facing task as success"

ROOT = Path(__file__).resolve().parents[2]


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    gw = ActionGateway(clock=clock)
    gw.commerce.fail_next_book = True
    gw.commerce.fail_book_message = "slot_unavailable"
    svc = BookingService(
        clock=clock,
        catcher=catcher,
        gateway=gw,
        timezone="Europe/Madrid",
        recipient="+15550001111",
        portal_fixture=ROOT / "fixtures" / "browser" / "booksy-stub-slots.json",
    )

    proposed = svc.propose_from_utterance("Book a haircut next week afternoon.")
    if not proposed.ok or not proposed.approval_id or not proposed.task_id:
        failures.append(f"propose failed: {proposed.reason}")
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}

    create_before = gw.calendar.create_count
    confirm_before = len(
        [m for m in catcher.messages if m.meta.get("kind") == "booking_confirm"]
    )

    inbox = AndroidApprovalInboxApi(gw)
    accepted = inbox.accept(proposed.approval_id)

    # Accept attempted execute but portal failed.
    if accepted.ok:
        failures.append("accept/execute reported ok on forced booking failure")
    item = gw.approvals.get(proposed.approval_id)
    if item is None or item.status != ApprovalStatus.FAILED:
        failures.append(
            f"approval status want failed, got {item.status.value if item else None}"
        )

    task = svc.store.get(proposed.task_id)
    if task is None:
        failures.append("booking task missing")
    else:
        if task.is_success:
            failures.append(f"user-facing task marked success status={task.status.value}")
        if task.status != BookingStatus.FAILED:
            failures.append(f"task status want failed, got {task.status.value}")
        if task.booking_id is not None:
            failures.append(f"failed task has booking_id={task.booking_id}")

    # No successful book execute, no calendar writeback, no success WhatsApp.
    if gw.commerce.book_count != 0:
        failures.append(f"failed path book_count={gw.commerce.book_count} (want 0 success)")
    if gw.calendar.create_count != create_before:
        failures.append("failed booking wrote calendar event")
    confirm_after = len(
        [m for m in catcher.messages if m.meta.get("kind") == "booking_confirm"]
    )
    if confirm_after != confirm_before:
        failures.append("failed booking sent booking_confirm WhatsApp")

    # Positive control on a fresh gateway: success path can mark booked.
    clock2 = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher2 = OutboundMessageCatcher()
    gw2 = ActionGateway(clock=clock2)
    svc2 = BookingService(
        clock=clock2,
        catcher=catcher2,
        gateway=gw2,
        timezone="Europe/Madrid",
        recipient="+15550001111",
        portal_fixture=ROOT / "fixtures" / "browser" / "booksy-stub-slots.json",
    )
    ok_prop = svc2.propose_from_utterance("Book a haircut next week afternoon.")
    assert ok_prop.approval_id and ok_prop.task_id
    ok_accept = AndroidApprovalInboxApi(gw2).accept(ok_prop.approval_id)
    ok_task = svc2.store.get(ok_prop.task_id)
    if not ok_accept.ok or ok_task is None or not ok_task.is_success:
        failures.append("positive control: successful book should mark task booked")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "forced portal failure → approval=failed, task=failed, "
            "book_count=0, no calendar/confirm; success control booked"
        ),
    }
