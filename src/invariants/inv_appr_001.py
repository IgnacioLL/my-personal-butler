"""INV-APPR-001 — hard actions cannot execute without approval.status == accepted."""

from __future__ import annotations

from typing import Any

from harness.clock import FakeClock
from policy.action_gateway import ActionGateway
from policy.approvals import HARD_ACTION_TYPES

INV_ID = "INV-APPR-001"
DESCRIPTION = (
    "Hard actions (buy, book, self-mod apply, policy change) cannot execute "
    "without approval.status == accepted"
)


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock()
    gw = ActionGateway(clock=clock)
    failures: list[str] = []

    for action_type in sorted(HARD_ACTION_TYPES):
        # 1) Direct bypass attempt — must be blocked; adapters untouched.
        bypass = gw.try_hard_action_without_approval(
            action_type, {"item": action_type}
        )
        if bypass.ok:
            failures.append(f"{action_type}: bypass succeeded")

        # 2) Propose creates pending; execute while pending must fail.
        proposed = gw.propose(
            action_type,
            f"do {action_type}",
            {"item": action_type},
        )
        if not proposed.ok or not proposed.approval_id:
            failures.append(f"{action_type}: propose failed ({proposed.reason})")
            continue

        pending_exec = gw.execute(proposed.approval_id)
        if pending_exec.ok:
            failures.append(f"{action_type}: execute while pending succeeded")

        item = gw.approvals.get(proposed.approval_id)
        if item is None or item.status.value != "pending":
            failures.append(
                f"{action_type}: expected pending, got "
                f"{item.status.value if item else None}"
            )

    # Adapter counters must remain zero — no hard side effects without Accept.
    if gw.commerce.buy_count or gw.commerce.book_count:
        failures.append(
            f"commerce counters non-zero: buy={gw.commerce.buy_count} "
            f"book={gw.commerce.book_count}"
        )
    if gw.selfmod.apply_count or gw.selfmod.policy_change_count:
        failures.append(
            f"selfmod counters non-zero: apply={gw.selfmod.apply_count} "
            f"policy={gw.selfmod.policy_change_count}"
        )

    # Positive control: accept then execute works (proves gate, not total lockout).
    buy = gw.propose("buy", "buy milk", {"sku": "milk", "price": 3.5})
    assert buy.approval_id
    gw.accept(buy.approval_id)
    done = gw.execute(buy.approval_id)
    if not done.ok or gw.commerce.buy_count != 1:
        failures.append(f"accepted buy should execute once (ok={done.ok})")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            f"hard actions gated; bypass+pending blocked; "
            f"accepted buy execute=1 (actions={sorted(HARD_ACTION_TYPES)})"
        ),
    }
