"""INV-SELF-002 — freeze self-mod disables apply/write tools immediately."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capabilities.selfmod.parse import EXPECTED_E2E08_UTTERANCE
from capabilities.selfmod.service import SelfModService
from channels.android.approvals import AndroidApprovalInboxApi
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus

INV_ID = "INV-SELF-002"
DESCRIPTION = "freeze self-mod disables apply/write tools immediately"

ROOT = Path(__file__).resolve().parents[2]


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    gw = ActionGateway(clock=clock)
    svc = SelfModService(
        clock=clock,
        catcher=catcher,
        gateway=gw,
        recipient="+15550001111",
        workspace_fixture=ROOT / "fixtures" / "selfmod" / "sample-workspace",
        allowlist_path=ROOT / "fixtures" / "selfmod" / "allowlist.json",
    )

    proposed = svc.propose_from_utterance(EXPECTED_E2E08_UTTERANCE)
    if not proposed.ok or not proposed.approval_id:
        svc.close()
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
    if gw.selfmod.apply_count != 0:
        failures.append(f"apply leaked before freeze execute: {gw.selfmod.apply_count}")

    tools = svc.tools_for_session()
    if tools.get("self_mod_apply") or tools.get("policy_change"):
        failures.append("apply tools must not be ambiently available pre-freeze")

    gw.freeze_self_mod()
    if not gw.kill.self_mod_frozen:
        failures.append("freeze_self_mod flag not set")

    tools_frozen = svc.tools_for_session()
    if tools_frozen.get("self_mod_apply") or tools_frozen.get("policy_change"):
        failures.append("apply tools still available under freeze")
    if not tools_frozen.get("source_read"):
        failures.append("source_read should remain available under freeze")
    if not tools_frozen.get("freeze_self_mod"):
        failures.append("tools snapshot missing freeze flag")

    # Stale accepted approval remains accepted (not cancelled).
    still = gw.approvals.get(proposed.approval_id)
    if still is None or still.status != ApprovalStatus.ACCEPTED:
        failures.append(
            "policy requires stale approval remain accepted "
            f"(got {still.status.value if still else None})"
        )

    blocked = gw.execute(proposed.approval_id)
    if blocked.ok:
        failures.append("execute succeeded under freeze_self_mod")
    if blocked.reason != "freeze_self_mod":
        failures.append(f"expected reason freeze_self_mod, got {blocked.reason!r}")
    if gw.selfmod.apply_count != 0:
        failures.append(f"freeze leaked apply_count={gw.selfmod.apply_count}")
    if not svc.workspace.working_tree_clean():
        failures.append("tree mutated under freeze")

    if not any(r.get("reason") == "freeze_self_mod" for r in gw.execute_rejections):
        failures.append("missing freeze_self_mod rejection artifact")

    # Android Accept while frozen also cannot apply.
    prop2 = svc.propose_from_utterance(EXPECTED_E2E08_UTTERANCE)
    if prop2.ok and prop2.approval_id:
        inbox = AndroidApprovalInboxApi(gw)
        accepted = inbox.accept(prop2.approval_id)
        if accepted.ok:
            failures.append("Android Accept applied patch while frozen")
        if accepted.execute and accepted.execute.reason != "freeze_self_mod":
            failures.append(
                f"Android Accept reason={accepted.execute.reason!r} "
                "(want freeze_self_mod)"
            )
    if gw.selfmod.apply_count != 0:
        failures.append(f"after Android Accept apply_count={gw.selfmod.apply_count}")

    # Unfreeze restores execute for the original stale accepted approval.
    gw.unfreeze_self_mod()
    done = gw.execute(proposed.approval_id)
    if not done.ok:
        failures.append(f"unfreeze should allow execute: {done.reason}")
    if gw.selfmod.apply_count != 1:
        failures.append(f"after unfreeze apply_count={gw.selfmod.apply_count} (want 1)")
    result = done.result if isinstance(done.result, dict) else {}
    if not result.get("rollback_ref"):
        failures.append("applied result missing rollback_ref")
    if not result.get("commit_sha"):
        failures.append("applied result missing commit_sha")

    svc.close()

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "freeze_self_mod blocks apply with stale accepted approval; "
            "read/propose still ok; unfreeze restores; rollback_ref present"
        ),
    }
