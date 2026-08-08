"""INV-SELF-003 — Apply without Accept is impossible in harness."""

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

INV_ID = "INV-SELF-003"
DESCRIPTION = "Apply without Accept is impossible in harness"

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

    # Baseline tree clean.
    if not svc.workspace.working_tree_clean():
        failures.append("fixture workspace not clean at start")

    proposed = svc.propose_from_utterance(EXPECTED_E2E08_UTTERANCE)
    if not proposed.ok or not proposed.approval_id:
        svc.close()
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"propose failed: {proposed.reason}",
        }

    # Propose must not apply (apply tools unavailable until Accept).
    if proposed.apply_available:
        failures.append("apply_available should be False after propose")
    if gw.selfmod.apply_count != 0:
        failures.append(f"propose leaked apply_count={gw.selfmod.apply_count}")
    if not proposed.tree_clean or not svc.workspace.working_tree_clean():
        failures.append("working tree changed before Accept")
    if not proposed.rollback_ref:
        failures.append("proposal missing rollback_ref")

    tools = svc.tools_for_session()
    if tools.get("self_mod_apply") or tools.get("policy_change"):
        failures.append("apply tools ambiently available before Accept")

    # Execute while still pending must fail.
    pending_exec = gw.execute(proposed.approval_id)
    if pending_exec.ok:
        failures.append("execute while pending succeeded")
    if gw.selfmod.apply_count != 0:
        failures.append("pending execute leaked apply")

    # Direct hard-action bypass impossible.
    bypass = gw.try_hard_action_without_approval(
        "self_mod_apply",
        {"files": ["skills/reminders.md"], "diff": "+evil"},
    )
    if bypass.ok or bypass.reason != "hard_action_requires_accepted_approval":
        failures.append(f"bypass not blocked: {bypass}")
    if gw.selfmod.apply_count != 0:
        failures.append("bypass leaked apply_count")

    # Deny leaves tree unchanged.
    deny_clock = FakeClock(start=datetime(2026, 1, 5, 11, 0, 0, tzinfo=tz))
    deny_catcher = OutboundMessageCatcher()
    deny_gw = ActionGateway(clock=deny_clock)
    deny_svc = SelfModService(
        clock=deny_clock,
        catcher=deny_catcher,
        gateway=deny_gw,
        recipient="+15550001111",
        workspace_fixture=ROOT / "fixtures" / "selfmod" / "sample-workspace",
        allowlist_path=ROOT / "fixtures" / "selfmod" / "allowlist.json",
    )
    deny_prop = deny_svc.propose_from_utterance(EXPECTED_E2E08_UTTERANCE)
    if deny_prop.ok and deny_prop.approval_id:
        AndroidApprovalInboxApi(deny_gw).deny(deny_prop.approval_id)
        denied_item = deny_gw.approvals.get(deny_prop.approval_id)
        if denied_item is None or denied_item.status != ApprovalStatus.DENIED:
            failures.append("deny did not mark denied")
        deny_exec = deny_gw.execute(deny_prop.approval_id)
        if deny_exec.ok:
            failures.append("execute after deny succeeded")
        if deny_gw.selfmod.apply_count != 0:
            failures.append("deny path apply_count != 0")
        if not deny_svc.workspace.working_tree_clean():
            failures.append("Deny left working tree dirty")
    else:
        failures.append(f"deny propose failed: {deny_prop.reason}")
    deny_svc.close()

    # Accept → apply on branch; audit has approval id; rollback_ref present.
    inbox = AndroidApprovalInboxApi(gw)
    accepted = inbox.accept(proposed.approval_id)
    if not accepted.ok:
        failures.append(f"Accept/execute failed: {accepted.reason}")
    if gw.selfmod.apply_count != 1:
        failures.append(f"after Accept apply_count={gw.selfmod.apply_count} (want 1)")
    result = accepted.execute.result if accepted.execute else None
    if not isinstance(result, dict):
        failures.append("missing apply result dict")
    else:
        if not result.get("rollback_ref"):
            failures.append("applied result missing rollback_ref")
        if result.get("rollback_ref") != proposed.rollback_ref:
            failures.append(
                f"rollback_ref mismatch propose={proposed.rollback_ref} "
                f"apply={result.get('rollback_ref')}"
            )
        if not result.get("commit_sha"):
            failures.append("missing commit_sha after apply")
        if not result.get("branch", "").startswith("cursor/agent-self-"):
            failures.append(f"unexpected branch {result.get('branch')!r}")
        # Tree should reflect quiet hours after apply (no longer matches baseline).
        reminders = svc.workspace.read("skills/reminders.md")
        if "enabled: true" not in reminders or "block_calls: true" not in reminders:
            failures.append("quiet hours patch not present after Accept")

    audits = gw.audit.for_approval(proposed.approval_id)
    success = [a for a in audits if a.success]
    if not success:
        failures.append("missing successful audit with approval id")
    elif success[0].approval_id != proposed.approval_id:
        failures.append("audit approval_id mismatch")

    # Accept-once: second execute blocked.
    second = gw.execute(proposed.approval_id)
    if second.ok:
        failures.append("second execute after executed should fail")
    if gw.selfmod.apply_count != 1:
        failures.append(f"second execute re-applied: {gw.selfmod.apply_count}")

    svc.close()

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "propose leaves tree clean; pending/bypass cannot apply; "
            "Deny unchanged; Accept applies once with audit + rollback_ref"
        ),
    }
