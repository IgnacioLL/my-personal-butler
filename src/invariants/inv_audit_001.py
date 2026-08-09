"""INV-AUDIT-001 — successful gated side effect leaves audit with approval id."""

from __future__ import annotations

from typing import Any

from harness.clock import FakeClock
from policy.action_gateway import ActionGateway

INV_ID = "INV-AUDIT-001"
DESCRIPTION = (
    "Every successful side effect write leaves an audit record referencing "
    "approval id when gated"
)


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock()
    gw = ActionGateway(clock=clock)

    proposed = gw.propose(
        "book",
        "book dentist",
        {
            "provider": "booksy",
            "shop": "Main St Barber",
            "service": "dentist",
            "start": "2026-01-10T09:00:00+00:00",
            "end": "2026-01-10T09:45:00+00:00",
            "slot": "2026-01-10T09:00:00Z",
        },
    )
    assert proposed.approval_id
    gw.accept(proposed.approval_id)
    done = gw.execute(proposed.approval_id)
    if not done.ok:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"execute failed: {done.reason}",
        }

    records = gw.audit.for_approval(proposed.approval_id)
    if not records:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": "no audit record for approval id after gated success",
        }

    success = [r for r in records if r.success]
    if not success:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"audit rows exist but none success=True: {records}",
        }

    row = success[0]
    if row.approval_id != proposed.approval_id:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"audit approval_id mismatch: {row.approval_id}",
        }
    if row.action_type != "book":
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"audit action_type={row.action_type}",
        }

    # Denied path must not leave a successful gated audit
    denied = gw.propose("buy", "buy X", {"sku": "x"})
    assert denied.approval_id
    gw.deny(denied.approval_id)
    gw.execute(denied.approval_id)
    if gw.audit.for_approval(denied.approval_id):
        # execute failure may or may not audit — must not be success=True
        bad = [r for r in gw.audit.for_approval(denied.approval_id) if r.success]
        if bad:
            return {
                "id": INV_ID,
                "result": "FAIL",
                "detail": "denied path left successful audit",
            }

    gated = gw.audit.successful_gated()
    if not any(r.approval_id == proposed.approval_id for r in gated):
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": "successful_gated missing book approval",
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            f"gated book success audited with approval_id={proposed.approval_id} "
            f"(audit_id={done.audit_id})"
        ),
    }
