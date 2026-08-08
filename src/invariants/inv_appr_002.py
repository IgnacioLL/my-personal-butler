"""INV-APPR-002 — denied and expired approvals never execute."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from harness.clock import FakeClock
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus

INV_ID = "INV-APPR-002"
DESCRIPTION = "denied and expired approvals never execute"


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock()
    gw = ActionGateway(clock=clock)
    failures: list[str] = []

    # Denied path
    denied_prop = gw.propose("book", "book haircut", {"slot": "2026-01-02T10:00:00Z"})
    assert denied_prop.approval_id
    gw.deny(denied_prop.approval_id)
    denied_item = gw.approvals.get(denied_prop.approval_id)
    if denied_item is None or denied_item.status != ApprovalStatus.DENIED:
        failures.append("deny did not set status=denied")
    denied_exec = gw.execute(denied_prop.approval_id)
    if denied_exec.ok:
        failures.append("denied approval executed")

    # Expired path (via clock; also covered by INV-APPR-004)
    exp_prop = gw.propose(
        "buy",
        "buy shoes",
        {"sku": "shoes"},
        expires_in=timedelta(hours=1),
    )
    assert exp_prop.approval_id
    clock.advance(timedelta(hours=2))
    exp_item = gw.approvals.get(exp_prop.approval_id)
    if exp_item is None or exp_item.status != ApprovalStatus.EXPIRED:
        failures.append(
            f"expected expired, got {exp_item.status.value if exp_item else None}"
        )
    exp_exec = gw.execute(exp_prop.approval_id)
    if exp_exec.ok:
        failures.append("expired approval executed")

    # Accept-after-expiry must also refuse
    try:
        gw.accept(exp_prop.approval_id)
        failures.append("accept after expiry should raise")
    except Exception as exc:  # noqa: BLE001
        if "expired" not in str(exc).lower() and getattr(exc, "code", "") != "expired":
            # ApprovalError code preferred
            code = getattr(exc, "code", "")
            if code != "expired":
                failures.append(f"unexpected accept-after-expiry error: {exc}")

    if gw.commerce.buy_count or gw.commerce.book_count:
        failures.append(
            f"adapters ran: buy={gw.commerce.buy_count} book={gw.commerce.book_count}"
        )

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": "denied+expired never execute; accept-after-expiry refused",
    }
