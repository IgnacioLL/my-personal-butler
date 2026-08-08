"""INV-PAY-001 — Spend freeze blocks commerce execute even with stale approval.

Policy (chosen and tested): freeze spending does NOT cancel approvals. An
already-accepted buy approval remains accepted; execute is refused with
reason `freeze_spending` until spending is unfrozen.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capabilities.shopping.service import ShoppingService
from channels.android.approvals import AndroidApprovalInboxApi
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus
from policy.spend_caps import SpendCapConfig

INV_ID = "INV-PAY-001"
DESCRIPTION = (
    "Spend freeze blocks commerce execute even if a stale approval exists "
    "(policy: do not cancel on freeze; refuse execute)"
)

ROOT = Path(__file__).resolve().parents[2]


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    gw = ActionGateway(clock=clock)
    svc = ShoppingService(
        clock=clock,
        catcher=catcher,
        gateway=gw,
        recipient="+15550001111",
        merchant_fixture=ROOT / "fixtures" / "shopping" / "merchant-catalog.json",
        spend_caps=SpendCapConfig(daily_limit=50.0, weekly_limit=150.0),
    )

    proposed = svc.propose_from_utterance("Buy my usual protein powder.")
    if not proposed.ok or not proposed.approval_id:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"propose failed: {proposed.reason}",
        }

    # Accept marks accepted but do NOT execute yet — stale accepted approval.
    gw.accept(proposed.approval_id)
    item = gw.approvals.get(proposed.approval_id)
    if item is None or item.status != ApprovalStatus.ACCEPTED:
        failures.append(
            f"expected accepted before freeze, got "
            f"{item.status.value if item else None}"
        )

    if gw.commerce.buy_count != 0:
        failures.append(f"buy leaked before freeze execute: {gw.commerce.buy_count}")

    # Freeze ON — approvals stay accepted (not cancelled).
    gw.freeze_spending()
    if not gw.kill.spending_frozen:
        failures.append("freeze_spending flag not set")

    still = gw.approvals.get(proposed.approval_id)
    if still is None or still.status != ApprovalStatus.ACCEPTED:
        failures.append(
            "policy requires stale approval remain accepted "
            f"(got {still.status.value if still else None})"
        )

    blocked = gw.execute(proposed.approval_id)
    if blocked.ok:
        failures.append("execute succeeded under freeze")
    if blocked.reason != "freeze_spending":
        failures.append(f"expected reason freeze_spending, got {blocked.reason!r}")
    if gw.commerce.buy_count != 0:
        failures.append(f"freeze leaked buy_count={gw.commerce.buy_count}")

    # Rejection artifact present.
    if not any(r.get("reason") == "freeze_spending" for r in gw.execute_rejections):
        failures.append("missing freeze rejection artifact")

    # Android Accept while frozen also cannot purchase.
    prop2 = svc.propose_from_utterance("Buy my usual protein powder.")
    if prop2.ok and prop2.approval_id:
        inbox = AndroidApprovalInboxApi(gw)
        accepted = inbox.accept(prop2.approval_id)
        if accepted.ok:
            failures.append("Android Accept executed purchase while frozen")
        if accepted.execute and accepted.execute.reason != "freeze_spending":
            failures.append(
                f"Android Accept reason={accepted.execute.reason!r} "
                "(want freeze_spending)"
            )
    if gw.commerce.buy_count != 0:
        failures.append(f"after Android Accept buy_count={gw.commerce.buy_count}")

    # Unfreeze restores execute for the original stale accepted approval.
    gw.unfreeze_spending()
    done = gw.execute(proposed.approval_id)
    if not done.ok:
        failures.append(f"unfreeze should allow execute: {done.reason}")
    if gw.commerce.buy_count != 1:
        failures.append(f"after unfreeze buy_count={gw.commerce.buy_count} (want 1)")
    receipt = done.result if isinstance(done.result, dict) else {}
    if not receipt.get("dry_run"):
        failures.append("expected dry_run receipt after unfreeze")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "freeze blocks execute with stale accepted approval; "
            "approvals not cancelled; unfreeze restores; dry-run receipt"
        ),
    }
