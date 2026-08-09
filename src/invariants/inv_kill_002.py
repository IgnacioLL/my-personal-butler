"""INV-KILL-002 — cancel pending flips pending → cancelled and prevents execute."""

from __future__ import annotations

from typing import Any

from harness.clock import FakeClock
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus

INV_ID = "INV-KILL-002"
DESCRIPTION = (
    "cancel pending flips all pending approvals to cancelled and prevents execute"
)


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock()
    gw = ActionGateway(clock=clock)

    a = gw.propose("buy", "buy A", {"sku": "a"})
    b = gw.propose("book", "book B", {"slot": "x"})
    c = gw.propose("calendar_create", "event C", {"title": "C"})
    ids = [a.approval_id, b.approval_id, c.approval_id]
    if not all(ids):
        return {"id": INV_ID, "result": "FAIL", "detail": "propose missing ids"}

    # Accept one first — cancel_pending must not touch already-accepted.
    assert a.approval_id
    gw.accept(a.approval_id)

    cancelled_ids = gw.cancel_pending()
    if set(cancelled_ids) != {b.approval_id, c.approval_id}:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"expected cancel of pending B+C, got {cancelled_ids}",
        }

    for aid, expected in (
        (a.approval_id, ApprovalStatus.ACCEPTED),
        (b.approval_id, ApprovalStatus.CANCELLED),
        (c.approval_id, ApprovalStatus.CANCELLED),
    ):
        item = gw.approvals.get(aid)  # type: ignore[arg-type]
        if item is None or item.status != expected:
            return {
                "id": INV_ID,
                "result": "FAIL",
                "detail": (
                    f"{aid}: expected {expected.value}, "
                    f"got {item.status.value if item else None}"
                ),
            }

    # Cancelled cannot execute
    for aid in (b.approval_id, c.approval_id):
        result = gw.execute(aid)  # type: ignore[arg-type]
        if result.ok:
            return {
                "id": INV_ID,
                "result": "FAIL",
                "detail": f"cancelled {aid} executed",
            }

    if gw.commerce.book_count or gw.calendar.create_count:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": (
                f"cancelled side effects leaked "
                f"book={gw.commerce.book_count} cal={gw.calendar.create_count}"
            ),
        }

    # Accepted (pre-cancel) can still execute
    done = gw.execute(a.approval_id)
    if not done.ok or gw.commerce.buy_count != 1:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"pre-accepted buy should still execute (ok={done.ok})",
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": "pending→cancelled; execute blocked; pre-accepted untouched",
    }
