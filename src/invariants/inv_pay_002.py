"""INV-PAY-002 — Cap breach blocks execute and surfaces a clear rejection artifact."""

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

INV_ID = "INV-PAY-002"
DESCRIPTION = (
    "Cap breach blocks execute and surfaces a clear rejection artifact"
)

ROOT = Path(__file__).resolve().parents[2]


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    # Cap below protein powder price (29.99) so Accept is blocked.
    tight = SpendCapConfig(daily_limit=20.0, weekly_limit=150.0, currency="EUR")
    gw = ActionGateway(clock=clock)
    svc = ShoppingService(
        clock=clock,
        catcher=catcher,
        gateway=gw,
        recipient="+15550001111",
        merchant_fixture=ROOT / "fixtures" / "shopping" / "merchant-catalog.json",
        spend_caps=tight,
    )

    proposed = svc.propose_from_utterance("Buy my usual protein powder.")
    if not proposed.ok or not proposed.approval_id:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"propose failed: {proposed.reason}",
        }
    if proposed.price is None or proposed.price <= tight.daily_limit:
        failures.append(
            f"fixture price {proposed.price} must exceed daily_limit "
            f"{tight.daily_limit} for this check"
        )

    # Chat text cannot raise the cap — Accept still blocked at execute.
    inbox = AndroidApprovalInboxApi(gw)
    accepted = inbox.accept(proposed.approval_id)
    if accepted.ok:
        failures.append("Accept under over-cap should not execute")
    if accepted.execute is None or accepted.execute.reason != "spend_cap_daily":
        failures.append(
            f"expected spend_cap_daily, got "
            f"{getattr(accepted.execute, 'reason', None)!r}"
        )
    if gw.commerce.buy_count != 0:
        failures.append(f"cap breach leaked buy_count={gw.commerce.buy_count}")

    item = gw.approvals.get(proposed.approval_id)
    if item is None or item.status != ApprovalStatus.ACCEPTED:
        # Accept succeeded as status transition; execute failed — stay accepted.
        failures.append(
            f"expected accepted (stale) after cap block, got "
            f"{item.status.value if item else None}"
        )

    # Clear rejection artifact with cap math.
    rejections = [
        r
        for r in gw.execute_rejections
        if r.get("reason") == "spend_cap_daily"
        and r.get("approval_id") == proposed.approval_id
    ]
    if not rejections:
        failures.append("missing spend_cap_daily rejection artifact")
    else:
        row = rejections[0]
        if row.get("daily_limit") != tight.daily_limit:
            failures.append(f"rejection daily_limit={row.get('daily_limit')}")
        if float(row.get("amount") or 0) != float(proposed.price or 0):
            failures.append(
                f"rejection amount={row.get('amount')} want {proposed.price}"
            )

    audits = [
        a
        for a in gw.audit.for_approval(proposed.approval_id)
        if not a.success
        and (a.detail or {}).get("rejection", {}).get("reason") == "spend_cap_daily"
    ]
    if not audits:
        failures.append("missing audit rejection for spend_cap_daily")

    # Positive control: under-cap Accept succeeds with dry-run receipt.
    roomy = SpendCapConfig(daily_limit=50.0, weekly_limit=150.0)
    clock2 = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher2 = OutboundMessageCatcher()
    gw2 = ActionGateway(clock=clock2)
    svc2 = ShoppingService(
        clock=clock2,
        catcher=catcher2,
        gateway=gw2,
        recipient="+15550001111",
        merchant_fixture=ROOT / "fixtures" / "shopping" / "merchant-catalog.json",
        spend_caps=roomy,
    )
    ok_prop = svc2.propose_from_utterance("Buy my usual protein powder.")
    if not ok_prop.ok or not ok_prop.approval_id:
        failures.append(f"under-cap propose failed: {ok_prop.reason}")
    else:
        ok_accept = AndroidApprovalInboxApi(gw2).accept(ok_prop.approval_id)
        if not ok_accept.ok or gw2.commerce.buy_count != 1:
            failures.append(
                f"under-cap Accept should execute "
                f"(ok={ok_accept.ok} buy={gw2.commerce.buy_count})"
            )
        receipts = [
            m for m in catcher2.messages if m.meta.get("kind") == "shopping_receipt"
        ]
        if len(receipts) != 1:
            failures.append(f"expected 1 shopping_receipt, got {len(receipts)}")
        result = ok_accept.execute.result if ok_accept.execute else None
        if not isinstance(result, dict) or not result.get("dry_run"):
            failures.append("under-cap receipt missing dry_run=true")
        success_audits = [
            a for a in gw2.audit.for_approval(ok_prop.approval_id) if a.success
        ]
        if not success_audits:
            failures.append("under-cap missing success audit with approval id")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "spend_cap_daily blocks execute + rejection/audit artifacts; "
            "under-cap dry-run receipt + audit ok"
        ),
    }
