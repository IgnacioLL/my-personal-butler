"""PROD-05 Android companion unit checks — imported by scripts/run_test_ci.py.

Kept out of the giant CI runner so parallel PROD agents editing run_test_ci.py
do not clobber Status / config / self-mod card gates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from capabilities.todos.store import TodoStore
from channels.android.approvals import AndroidApprovalInboxApi
from channels.android.status import AndroidStatusApi
from harness.clock import FakeClock
from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalError, ApprovalStatus, ApprovalTier


def run_android_approval_unit_checks() -> list[dict[str, Any]]:
    """Android approval inbox API: list/Accept/Deny/Edit + soft calendar gate."""
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

    # Edit after deny must fail closed.
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

    return checks

def run_android_status_unit_checks() -> list[dict[str, Any]]:
    """Android Status screen API: kill switches + pending/todo counts."""
    checks: list[dict[str, Any]] = []
    clock = FakeClock()
    gw = ActionGateway(clock=clock)
    todo_store = TodoStore()
    todo_store.create(title="Status test", created_at=clock.now())
    gw.todos = todo_store
    status = AndroidStatusApi(gw)

    snap = status.get()
    base_ok = (
        snap.gateway_online
        and snap.paired
        and not snap.agent_paused
        and not snap.spend_frozen
        and not snap.self_mod_frozen
        and snap.open_todos == 1
        and snap.pending_approvals == 0
    )
    checks.append(
        {
            "id": "unit.android_status.initial_snapshot",
            "result": "PASS" if base_ok else "FAIL",
            "detail": (
                f"online={snap.gateway_online} todos={snap.open_todos} "
                f"pending={snap.pending_approvals}"
            ),
        }
    )

    prop = gw.propose(
        "calendar_create",
        "Status pending",
        {
            "title": "Status pending",
            "start": "2026-01-09T09:00:00+01:00",
            "end": "2026-01-09T10:00:00+01:00",
        },
    )
    snap2 = status.get()
    pending_ok = prop.ok and snap2.pending_approvals == 1
    checks.append(
        {
            "id": "unit.android_status.pending_count",
            "result": "PASS" if pending_ok else "FAIL",
            "detail": f"prop_ok={prop.ok} pending={snap2.pending_approvals}",
        }
    )

    paused = status.pause_agent()
    resumed = status.resume_agent()
    pause_ok = paused.agent_paused and not resumed.agent_paused
    checks.append(
        {
            "id": "unit.android_status.pause_resume",
            "result": "PASS" if pause_ok else "FAIL",
            "detail": (
                f"paused={paused.agent_paused} resumed={resumed.agent_paused}"
            ),
        }
    )

    frozen = status.freeze_spending()
    unfrozen = status.unfreeze_spending()
    spend_ok = frozen.spend_frozen and not unfrozen.spend_frozen
    checks.append(
        {
            "id": "unit.android_status.spend_freeze",
            "result": "PASS" if spend_ok else "FAIL",
            "detail": (
                f"frozen={frozen.spend_frozen} unfrozen={unfrozen.spend_frozen}"
            ),
        }
    )

    sm_frozen = status.freeze_self_mod()
    sm_unfrozen = status.unfreeze_self_mod()
    sm_ok = sm_frozen.self_mod_frozen and not sm_unfrozen.self_mod_frozen
    checks.append(
        {
            "id": "unit.android_status.self_mod_freeze",
            "result": "PASS" if sm_ok else "FAIL",
            "detail": (
                f"frozen={sm_frozen.self_mod_frozen} "
                f"unfrozen={sm_unfrozen.self_mod_frozen}"
            ),
        }
    )

    after_cancel, cancelled = status.cancel_pending()
    cancel_ok = after_cancel.pending_approvals == 0 and len(cancelled) >= 1
    checks.append(
        {
            "id": "unit.android_status.cancel_pending",
            "result": "PASS" if cancel_ok else "FAIL",
            "detail": (
                f"pending={after_cancel.pending_approvals} "
                f"cancelled={len(cancelled)}"
            ),
        }
    )

    snapshot = status.snapshot()
    dict_ok = (
        isinstance(snapshot, dict)
        and "kill_switches" in snapshot
        and snapshot["kill_switches"]["pause_agent"] is False
    )
    checks.append(
        {
            "id": "unit.android_status.snapshot_dict",
            "result": "PASS" if dict_ok else "FAIL",
            "detail": f"keys={sorted(snapshot.keys()) if isinstance(snapshot, dict) else 'n/a'}",
        }
    )

    return checks

def run_prod05_android_config_checks(root: Path) -> list[dict[str, Any]]:
    """PROD-05: production Android config + harness doubles present (no live device)."""
    checks: list[dict[str, Any]] = []
    paths = {
        "config/android.example.yaml": root / "config" / "android.example.yaml",
        "config/android.harness.json": root / "config" / "android.harness.json",
        "docs/android-pairing.md": root / "docs" / "android-pairing.md",
    }
    missing = [label for label, path in paths.items() if not path.is_file()]
    checks.append(
        {
            "id": "unit.prod05.android_files",
            "result": "PASS" if not missing else "FAIL",
            "detail": f"missing={missing or 'none'}",
        }
    )

    yaml_path = paths["config/android.example.yaml"]
    yaml_text = yaml_path.read_text(encoding="utf-8") if yaml_path.is_file() else ""
    yaml_markers = [
        "channels:",
        "android:",
        "features:",
        "approvals:",
        "kill_switches:",
        "pairing:",
    ]
    yaml_ok = yaml_path.is_file() and all(m in yaml_text for m in yaml_markers)
    checks.append(
        {
            "id": "unit.prod05.android_example_yaml",
            "result": "PASS" if yaml_ok else "FAIL",
            "detail": f"markers_ok={yaml_ok}",
        }
    )

    harness_path = paths["config/android.harness.json"]
    harness_ok = False
    harness_detail = "missing"
    if harness_path.is_file():
        try:
            harness = json.loads(harness_path.read_text(encoding="utf-8"))
            doubles = harness.get("doubles") or {}
            harness_ok = (
                harness.get("mode") == "harness"
                and "AndroidStatusApi" in str(doubles.get("status", ""))
                and "AndroidApprovalInboxApi" in str(doubles.get("approvals", ""))
                and harness.get("production_config") == "config/android.example.yaml"
                and harness.get("pairing_runbook") == "docs/android-pairing.md"
            )
            harness_detail = f"mode={harness.get('mode')} doubles={list(doubles.keys())}"
        except json.JSONDecodeError as exc:
            harness_detail = f"json_error={exc}"
    checks.append(
        {
            "id": "unit.prod05.android_harness_json",
            "result": "PASS" if harness_ok else "FAIL",
            "detail": harness_detail,
        }
    )

    doc_path = paths["docs/android-pairing.md"]
    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    doc_markers = [
        "openclaw devices approve",
        "nodes approve",
        "kill switch",
        "android.example.yaml",
    ]
    doc_ok = doc_path.is_file() and all(m.lower() in doc_text.lower() for m in doc_markers)
    checks.append(
        {
            "id": "unit.prod05.android_pairing_runbook",
            "result": "PASS" if doc_ok else "FAIL",
            "detail": f"sections_ok={doc_ok}",
        }
    )

    return checks
