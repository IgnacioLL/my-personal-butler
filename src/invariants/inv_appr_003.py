"""INV-APPR-003 — soft-confirm calendar writes do not hit adapter before confirm."""

from __future__ import annotations

from typing import Any

from harness.clock import FakeClock
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus

INV_ID = "INV-APPR-003"
DESCRIPTION = "Soft-confirm calendar writes do not hit the calendar adapter before confirm"


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock()
    gw = ActionGateway(clock=clock)

    proposed = gw.propose(
        "calendar_create",
        "Lunch with Sam",
        {"title": "Lunch with Sam", "start": "2026-01-05T12:00:00Z"},
    )
    if not proposed.ok or proposed.executed or not proposed.approval_id:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"propose should pend soft confirm, got {proposed}",
        }

    if gw.calendar.create_count != 0:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"calendar.create called before confirm (count={gw.calendar.create_count})",
        }

    # Execute while pending must not write
    pending_exec = gw.execute(proposed.approval_id)
    if pending_exec.ok or gw.calendar.create_count != 0:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": (
                f"pending execute leaked write "
                f"(ok={pending_exec.ok}, creates={gw.calendar.create_count})"
            ),
        }

    gw.accept(proposed.approval_id)
    item = gw.approvals.get(proposed.approval_id)
    if item is None or item.status != ApprovalStatus.ACCEPTED:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": "accept did not reach accepted",
        }

    done = gw.execute(proposed.approval_id)
    if not done.ok or gw.calendar.create_count != 1:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": (
                f"accepted soft confirm should create once "
                f"(ok={done.ok}, creates={gw.calendar.create_count})"
            ),
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": "calendar create_count=0 until accept; then create=1",
    }
