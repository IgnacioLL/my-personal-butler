"""INV-APPR-004 — approval expiry uses fake clock; advance → expired without execute."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from harness.clock import FakeClock
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus

INV_ID = "INV-APPR-004"
DESCRIPTION = (
    "Approval expiry uses the clock; advancing past expiry transitions status without execute"
)


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock()
    gw = ActionGateway(clock=clock)

    proposed = gw.propose(
        "self_mod_apply",
        "apply patch",
        {"diff": "+print('hi')", "files": ["src/tools/x.py"]},
        expires_in=timedelta(hours=3),
        diff_summary="+print",
        files_touched=["src/tools/x.py"],
    )
    assert proposed.approval_id
    item = gw.approvals.get(proposed.approval_id)
    if item is None or item.status != ApprovalStatus.PENDING:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": "expected pending after propose",
        }

    # Still before expiry
    clock.advance(timedelta(hours=2))
    mid = gw.approvals.get(proposed.approval_id)
    if mid is None or mid.status != ApprovalStatus.PENDING:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"should still be pending before expiry, got {mid}",
        }

    # Past expiry
    clock.advance(timedelta(hours=2))  # total +4h > 3h TTL
    expired = gw.approvals.expire_due()
    item2 = gw.approvals.get(proposed.approval_id)
    if item2 is None or item2.status != ApprovalStatus.EXPIRED:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": (
                f"expected expired after clock.advance, got "
                f"{item2.status.value if item2 else None}; expire_due={len(expired)}"
            ),
        }

    exec_result = gw.execute(proposed.approval_id)
    if exec_result.ok or gw.selfmod.apply_count != 0:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": (
                f"expired must not execute "
                f"(ok={exec_result.ok}, apply={gw.selfmod.apply_count})"
            ),
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": "clock.advance past TTL → expired; apply_count=0",
    }
