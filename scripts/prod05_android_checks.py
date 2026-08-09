"""PROD-05 Android companion unit checks — imported by scripts/run_test_ci.py.

Kept out of the giant CI runner so parallel PROD agents editing run_test_ci.py
do not clobber Status / config / self-mod card gates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from channels.android.approvals import AndroidApprovalInboxApi
from channels.android.status import AndroidStatusApi
from harness.clock import FakeClock
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalError, ApprovalStatus, ApprovalTier


def run_android_approval_unit_checks() -> list[dict[str, Any]]:
    """Android approval inbox API: list/Accept/Deny/Edit + self-mod cards."""
    checks: list[dict[str, Any]] = []
    clock = FakeClock()
    gw = ActionGateway(clock=clock)
    inbox = AndroidApprovalInboxApi(gw)

    soft = gw.propose(
        "calendar_create",
        "Focus block",
        {
            "title": "Focus block",
            "start": "2026-01-09T09:00:00+01:00",
            "end": "2026-01-09T11:00:00+01:00",
        },
    )
    pending = inbox.list_pending()
    list_ok = (
        soft.ok
        and soft.approval_id is not None
        and soft.tier == ApprovalTier.SOFT_CONFIRM.value
        and not soft.executed
        and gw.calendar.create_count == 0
        and len(pending) == 1
        and pending[0].id == soft.approval_id
        and pending[0].action_type == "calendar_create"
    )
    checks.append(
        {
            "id": "unit.android_approval.list_pending_soft",
            "result": "PASS" if list_ok else "FAIL",
            "detail": (
                f"tier={soft.tier} pending={len(pending)} "
                f"create={gw.calendar.create_count}"
            ),
        }
    )

    assert soft.approval_id is not None
    edited = inbox.edit(
        soft.approval_id,
        summary="Focus block (edited)",
        payload_patch={"title": "Focus block (edited)"},
    )
    edit_ok = (
        edited.summary == "Focus block (edited)"
        and edited.payload.get("title") == "Focus block (edited)"
        and edited.status == ApprovalStatus.PENDING.value
        and gw.calendar.create_count == 0
    )
    checks.append(
        {
            "id": "unit.android_approval.edit_pending",
            "result": "PASS" if edit_ok else "FAIL",
            "detail": f"summary={edited.summary!r} create={gw.calendar.create_count}",
        }
    )

    accepted = inbox.accept(soft.approval_id)
    accept_ok = (
        accepted.ok
        and accepted.approval.status == ApprovalStatus.EXECUTED.value
        and gw.calendar.create_count == 1
        and len(inbox.list_pending()) == 0
    )
    checks.append(
        {
            "id": "unit.android_approval.accept_executes",
            "result": "PASS" if accept_ok else "FAIL",
            "detail": (
                f"ok={accepted.ok} status={accepted.approval.status} "
                f"create={gw.calendar.create_count}"
            ),
        }
    )

    deny_prop = gw.propose(
        "calendar_create",
        "Dentist",
        {
            "title": "Dentist",
            "start": "2026-01-10T15:00:00+01:00",
            "end": "2026-01-10T16:00:00+01:00",
        },
    )
    assert deny_prop.approval_id is not None
    denied = inbox.deny(deny_prop.approval_id)
    late = gw.execute(deny_prop.approval_id)
    deny_ok = (
        denied.status == ApprovalStatus.DENIED.value
        and gw.calendar.create_count == 1
        and (not late.ok)
        and gw.calendar.create_count == 1
    )
    checks.append(
        {
            "id": "unit.android_approval.deny_blocks_execute",
            "result": "PASS" if deny_ok else "FAIL",
            "detail": (
                f"status={denied.status} late={late.reason} create={gw.calendar.create_count}"
            ),
        }
    )

    edit_blocked = False
    try:
        inbox.edit(deny_prop.approval_id, summary="nope")
    except ApprovalError:
        edit_blocked = True
    checks.append(
        {
            "id": "unit.android_approval.edit_terminal_blocked",
            "result": "PASS" if edit_blocked else "FAIL",
            "detail": f"edit_blocked={edit_blocked}",
        }
    )

    self_prop = gw.propose(
        "self_mod_apply",
        "Apply quiet hours patch",
        {"files": ["src/skills/reminders.py"]},
        diff_summary="Add quiet hours guard",
        files_touched=["src/skills/reminders.py"],
        rollback_ref="branch/selfmod-quiet-hours",
    )
    pol_prop = gw.propose(
        "policy_change",
        "Raise spend cap",
        {"cap": 100},
        subtype="policy-change",
        diff_summary="Raise daily cap",
        files_touched=["src/policy/spend_caps.py"],
        rollback_ref="branch/selfmod-policy-cap",
    )
    self_card = inbox.get(self_prop.approval_id) if self_prop.approval_id else None
    pol_card = inbox.get(pol_prop.approval_id) if pol_prop.approval_id else None
    self_ok = (
        self_prop.ok
        and self_card is not None
        and self_card.badge == "Code change"
        and self_card.diff_summary == "Add quiet hours guard"
        and self_card.files_touched == ["src/skills/reminders.py"]
        and self_card.rollback_ref == "branch/selfmod-quiet-hours"
    )
    pol_ok = (
        pol_prop.ok
        and pol_card is not None
        and pol_card.badge == "policy-change"
        and pol_card.subtype == "policy-change"
    )
    checks.append(
        {
            "id": "unit.android_approval.self_mod_card_fields",
            "result": "PASS" if (self_ok and pol_ok) else "FAIL",
            "detail": (
                f"self_badge={getattr(self_card, 'badge', None)!r} "
                f"pol_badge={getattr(pol_card, 'badge', None)!r}"
            ),
        }
    )
    return checks


def run_android_status_unit_checks() -> list[dict[str, Any]]:
    """Status screen projects kill switches + pending counts."""
    checks: list[dict[str, Any]] = []
    clock = FakeClock()
    gw = ActionGateway(clock=clock)
    status = AndroidStatusApi(gw)

    baseline = status.get()
    base_ok = (
        baseline.gateway_online
        and baseline.paired
        and not baseline.agent_paused
        and not baseline.spend_frozen
        and not baseline.self_mod_frozen
        and baseline.pending_approvals == 0
    )
    checks.append(
        {
            "id": "unit.android_status.baseline",
            "result": "PASS" if base_ok else "FAIL",
            "detail": f"snap={baseline.to_dict()}",
        }
    )

    paused = status.pause_agent()
    resumed = status.resume_agent()
    pause_ok = paused.agent_paused and not resumed.agent_paused
    checks.append(
        {
            "id": "unit.android_status.pause_resume",
            "result": "PASS" if pause_ok else "FAIL",
            "detail": f"paused={paused.agent_paused} resumed={resumed.agent_paused}",
        }
    )

    spend = status.freeze_spending()
    unspend = status.unfreeze_spending()
    spend_ok = spend.spend_frozen and not unspend.spend_frozen
    checks.append(
        {
            "id": "unit.android_status.freeze_spending",
            "result": "PASS" if spend_ok else "FAIL",
            "detail": f"frozen={spend.spend_frozen} unfrozen={unspend.spend_frozen}",
        }
    )

    sm = status.freeze_self_mod()
    unsm = status.unfreeze_self_mod()
    sm_ok = sm.self_mod_frozen and not unsm.self_mod_frozen
    checks.append(
        {
            "id": "unit.android_status.freeze_self_mod",
            "result": "PASS" if sm_ok else "FAIL",
            "detail": f"frozen={sm.self_mod_frozen} unfrozen={unsm.self_mod_frozen}",
        }
    )

    prop = gw.propose(
        "calendar_create",
        "Status pending probe",
        {
            "title": "Status pending probe",
            "start": "2026-01-09T09:00:00+01:00",
            "end": "2026-01-09T10:00:00+01:00",
        },
    )
    after_prop = status.get()
    cancelled_status, cancelled_ids = status.cancel_pending()
    cancel_ok = (
        prop.ok
        and after_prop.pending_approvals >= 1
        and cancelled_status.pending_approvals == 0
        and prop.approval_id in cancelled_ids
    )
    checks.append(
        {
            "id": "unit.android_status.cancel_pending",
            "result": "PASS" if cancel_ok else "FAIL",
            "detail": (
                f"pending_before={after_prop.pending_approvals} "
                f"pending_after={cancelled_status.pending_approvals} "
                f"cancelled={len(cancelled_ids)}"
            ),
        }
    )
    return checks


def run_prod05_android_config_checks(root: Path) -> list[dict[str, Any]]:
    """Production Android templates + Status API module present (CI doubles stay)."""
    checks: list[dict[str, Any]] = []
    example = root / "config" / "android.example.yaml"
    harness = root / "config" / "android.harness.json"
    pairing = root / "docs" / "android-pairing.md"
    status_mod = root / "src" / "channels" / "android" / "status.py"
    plan = root / "agent-plan" / "channels" / "android-companion.md"

    files_ok = all(p.is_file() for p in (example, harness, pairing, status_mod, plan))
    checks.append(
        {
            "id": "unit.android.prod05_files",
            "result": "PASS" if files_ok else "FAIL",
            "detail": (
                f"example={example.is_file()} harness={harness.is_file()} "
                f"pairing={pairing.is_file()} status={status_mod.is_file()} "
                f"plan={plan.is_file()}"
            ),
        }
    )

    try:
        harness_data = json.loads(harness.read_text(encoding="utf-8"))
        doubles = dict(harness_data.get("doubles") or {})
        features = dict(harness_data.get("features") or {})
        harness_ok = (
            doubles.get("status") == "channels.android.status.AndroidStatusApi"
            and doubles.get("approvals")
            == "channels.android.approvals.AndroidApprovalInboxApi"
            and features.get("status_kill_switches") is True
            and features.get("self_mod_cards") is True
        )
        example_text = example.read_text(encoding="utf-8")
        example_ok = (
            "freeze_self_mod" in example_text
            and "self_mod_cards" in example_text
            and "kill_switches" in example_text
            and "accept" in example_text
            and "deny" in example_text
            and "edit" in example_text
        )
        docs_ok = (
            "Operator checklist" in pairing.read_text(encoding="utf-8")
            and "PROD-05" in plan.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        checks.append(
            {
                "id": "unit.android.prod05_config_shape",
                "result": "FAIL",
                "detail": f"parse_error:{exc}",
            }
        )
        return checks

    checks.append(
        {
            "id": "unit.android.prod05_config_shape",
            "result": "PASS" if (harness_ok and example_ok and docs_ok) else "FAIL",
            "detail": (
                f"harness_ok={harness_ok} example_ok={example_ok} docs_ok={docs_ok}"
            ),
        }
    )
    return checks
