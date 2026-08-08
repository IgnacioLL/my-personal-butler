#!/usr/bin/env python3
"""CI layer runners: unit, contract (INV-*), integration stubs.

Writes artifacts under artifacts/test/ci/. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harness.artifacts import write_report  # noqa: E402
from harness.clock import FakeClock  # noqa: E402
from harness.gateway_harness import GatewayHarness  # noqa: E402
from harness.gateway_profile import gateway_data_paths, load_gateway_profile  # noqa: E402
from harness.ingress_sim import IngressSimulator  # noqa: E402
from harness.inv_runner import run_all  # noqa: E402
from harness.outbound import OutboundMessageCatcher  # noqa: E402
from harness.virtual_user import (  # noqa: E402
    EXPECTED_E2E04_UTTERANCE,
    EXPECTED_E2E05_UTTERANCE,
    EXPECTED_E2E06_UTTERANCE,
    VirtualUser,
    run_e2e_01,
    run_e2e_02,
    run_e2e_03,
    run_e2e_04,
    run_e2e_05,
    run_e2e_05_structure,
    run_e2e_06,
    run_e2e_07,
    run_e2e_09,
    run_t2_approval_inbox,
)
from harness.whatsapp_transport import MockWhatsAppTransport  # noqa: E402
from policy.action_gateway import ActionGateway  # noqa: E402
from policy.approvals import (  # noqa: E402
    ApprovalError,
    ApprovalStatus,
    ApprovalTier,
    tier_for,
)
from policy.ingress import evaluate_ingress, normalize_sender  # noqa: E402
from intelligence.memory.secrets import MemorySecretsError, redact_secrets  # noqa: E402
from intelligence.memory.store import MemoryStore  # noqa: E402
from intelligence.models.fixtures import load_routing_fixture  # noqa: E402
from intelligence.models.roles import ModelRole  # noqa: E402
from intelligence.models.router import RoutingSignals, route  # noqa: E402
from intelligence.models.stubs import ModelStubRegistry  # noqa: E402
from intelligence.transcription.pipeline import TranscriptionPipeline  # noqa: E402
from intelligence.transcription.stt import SttOutcome, SttStub, load_manifest  # noqa: E402
from intelligence.transcription.tts import TtsMode, TtsPolicySpy  # noqa: E402
from capabilities.reminders.parse import next_weekly_after, parse_reminder  # noqa: E402
from capabilities.reminders.scheduler import ReminderScheduler  # noqa: E402
from capabilities.reminders.service import ReminderService  # noqa: E402
from capabilities.reminders.store import (  # noqa: E402
    EscalationChannel,
    ReminderKind,
    ReminderStatus,
    ReminderStore,
)
from capabilities.calendar.parse import looks_like_schedule, parse_schedule  # noqa: E402
from capabilities.calendar.service import CalendarService  # noqa: E402
from capabilities.calendar.store import CalendarStore  # noqa: E402
from capabilities.bookings.parse import looks_like_booking, parse_booking  # noqa: E402
from capabilities.bookings.portal import StubBooksyPortal  # noqa: E402
from capabilities.bookings.service import BookingService  # noqa: E402
from capabilities.bookings.store import BookingStatus, BookingStore  # noqa: E402
from capabilities.diet.constraints import banned_terms, check_meal_plan, text_violations  # noqa: E402
from capabilities.diet.parse import looks_like_meal_plan, parse_meal_plan_request  # noqa: E402
from capabilities.diet.planner import build_meal_plan, schedule_hints  # noqa: E402
from capabilities.diet.service import DietService  # noqa: E402
from capabilities.shopping.merchant import DryRunMerchant  # noqa: E402
from capabilities.shopping.parse import (  # noqa: E402
    EXPECTED_E2E07_UTTERANCE,
    looks_like_shopping,
    parse_shopping,
)
from capabilities.shopping.service import ShoppingService  # noqa: E402
from capabilities.shopping.store import PurchaseStatus  # noqa: E402
from capabilities.todos.parse import looks_like_todo_add, parse_todo  # noqa: E402
from capabilities.todos.service import TodoService  # noqa: E402
from capabilities.todos.store import TodoSource, TodoStatus, TodoStore, normalize_title  # noqa: E402
from channels.android.approvals import AndroidApprovalInboxApi  # noqa: E402
from channels.android.notifications import AndroidNotificationCatcher  # noqa: E402
from channels.android.projection import AndroidProjectionApi  # noqa: E402
from channels.voice.allowlist import (  # noqa: E402
    CALL_MODE_ALLOWED_TOOLS,
    CALL_MODE_FORBIDDEN_TOOLS,
    call_mode_block_reason,
    is_call_mode_allowed,
)
from channels.voice.provider import MockVoiceProvider  # noqa: E402
from capabilities.reminders.escalation import EscalationLadder  # noqa: E402
from policy.spend_caps import SpendCapConfig, SpendLedger  # noqa: E402


def run_unit(out_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    clock = FakeClock()
    start = clock.now()
    clock.advance(timedelta(hours=1))
    ok = clock.now() - start == timedelta(hours=1)
    checks.append(
        {
            "id": "unit.fake_clock.advance",
            "result": "PASS" if ok else "FAIL",
            "detail": "advance(1h) moves now() by 1h" if ok else "clock skew",
        }
    )

    catcher = OutboundMessageCatcher()
    catcher.send("whatsapp", "+15550001111", "hello")
    ok2 = catcher.count() == 1 and catcher.messages[0].body == "hello"
    checks.append(
        {
            "id": "unit.outbound_catcher.capture",
            "result": "PASS" if ok2 else "FAIL",
            "detail": "catcher records one outbound message",
        }
    )

    # Approval matrix tiers (table-driven smoke)
    matrix_ok = (
        tier_for("todo_add") == ApprovalTier.AUTO
        and tier_for("calendar_create") == ApprovalTier.SOFT_CONFIRM
        and tier_for("buy") == ApprovalTier.HARD_APPROVE
        and tier_for("transfer_money") == ApprovalTier.FORBIDDEN
        and tier_for("self_mod_apply") == ApprovalTier.HARD_APPROVE
        and tier_for("policy_change") == ApprovalTier.HARD_APPROVE
    )
    checks.append(
        {
            "id": "unit.approval_matrix.tiers",
            "result": "PASS" if matrix_ok else "FAIL",
            "detail": "Auto/Soft/Hard/Forbidden mapping for sample actions",
        }
    )

    # Status machine: pending → accepted → executed; Accept once idempotent side-effect
    gw = ActionGateway(clock=FakeClock())
    prop = gw.propose("buy", "unit buy", {"sku": "u1", "price": 1.0})
    status_ok = False
    detail = "propose failed"
    if prop.approval_id:
        gw.accept(prop.approval_id)
        first = gw.execute(prop.approval_id)
        # Second accept on executed should fail closed (terminal)
        second_accept_blocked = False
        try:
            gw.accept(prop.approval_id)
        except Exception:  # noqa: BLE001
            second_accept_blocked = True
        item = gw.approvals.get(prop.approval_id)
        status_ok = (
            first.ok
            and gw.commerce.buy_count == 1
            and item is not None
            and item.status == ApprovalStatus.EXECUTED
            and second_accept_blocked
        )
        detail = (
            f"status={item.status.value if item else None} "
            f"buy_count={gw.commerce.buy_count} "
            f"second_accept_blocked={second_accept_blocked}"
        )
    checks.append(
        {
            "id": "unit.approval_status_machine",
            "result": "PASS" if status_ok else "FAIL",
            "detail": detail,
        }
    )

    # Kill switches snapshot
    gw2 = ActionGateway(clock=FakeClock())
    gw2.pause_agent()
    gw2.freeze_spending()
    gw2.freeze_self_mod()
    snap = gw2.kill.snapshot()
    kill_ok = (
        snap.get("pause_agent")
        and snap.get("freeze_spending")
        and snap.get("freeze_self_mod")
    )
    checks.append(
        {
            "id": "unit.kill_switches.flags",
            "result": "PASS" if kill_ok else "FAIL",
            "detail": f"snapshot={snap}",
        }
    )

    # Ingress normalize + empty allowlist fail-closed
    norm_ok = (
        normalize_sender("\u200b+15550001111") == "+15550001111"
        and normalize_sender("  +15550001111  ") == "+15550001111"
        and normalize_sender("") == ""
    )
    empty_dec = evaluate_ingress("+15550001111", [])
    group_dec = evaluate_ingress(
        "+15550001111",
        ["+15550001111"],
        is_group=False,
        group_id="120363@g.us",
        groups_enabled=False,
    )
    ingress_ok = (
        norm_ok
        and (not empty_dec.allowed)
        and empty_dec.reason == "empty_allowlist"
        and (not group_dec.allowed)
        and group_dec.reason == "groups_disabled"
    )
    checks.append(
        {
            "id": "unit.ingress.normalize_and_fail_closed",
            "result": "PASS" if ingress_ok else "FAIL",
            "detail": (
                f"norm_ok={norm_ok} empty={empty_dec.reason} group={group_dec.reason}"
            ),
        }
    )

    # Mock WhatsApp transport: reject → zero counters; allow → tools+outbound
    t_catcher = OutboundMessageCatcher()
    transport = MockWhatsAppTransport(
        allowlist=["+15550001111"], catcher=t_catcher, groups_enabled=False
    )
    denied = transport.inject_text("+19999999999", "nope")
    denied_ok = (
        (not denied.allowed)
        and transport.counters.tool_calls == 0
        and transport.counters.outbound_sends == 0
        and t_catcher.count() == 0
    )
    allowed = transport.inject_text("+15550001111", "ping")
    allowed_ok = (
        allowed.allowed
        and transport.counters.tool_calls == 1
        and transport.counters.outbound_sends == 1
        and t_catcher.count() == 1
    )
    checks.append(
        {
            "id": "unit.mock_whatsapp_transport.counters",
            "result": "PASS" if (denied_ok and allowed_ok) else "FAIL",
            "detail": (
                f"denied_ok={denied_ok} allowed_ok={allowed_ok} "
                f"counters={transport.counters.snapshot()}"
            ),
        }
    )

    # Memory secrets guard: reject + redact.
    secret_sample = "api_key=sk-abcdefghijklmnopqrstuvwxyz12345"
    reject_ok = False
    try:
        MemoryStore.seed(Path(tempfile.mkdtemp(prefix="unit-mem-"))).remember(
            "preferences", "note", secret_sample
        )
    except MemorySecretsError:
        reject_ok = True
    redacted = redact_secrets(secret_sample)
    redact_ok = "[REDACTED]" in redacted and "sk-" not in redacted
    checks.append(
        {
            "id": "unit.memory.secrets_guard",
            "result": "PASS" if (reject_ok and redact_ok) else "FAIL",
            "detail": f"reject_ok={reject_ok} redact_ok={redact_ok}",
        }
    )

    checks.extend(_run_transcription_unit_checks(ROOT))
    checks.extend(_run_models_unit_checks(ROOT))
    checks.extend(_run_reminder_unit_checks())
    checks.extend(_run_voice_unit_checks())
    checks.extend(_run_todo_unit_checks())
    checks.extend(_run_android_approval_unit_checks())
    checks.extend(_run_calendar_unit_checks(ROOT))
    checks.extend(_run_diet_unit_checks(ROOT))
    checks.extend(_run_booking_unit_checks(ROOT))
    checks.extend(_run_shopping_unit_checks(ROOT))

    result = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    write_report(out_dir / "unit", layer="unit", result=result, checks=checks)
    return {"layer": "unit", "result": result, "checks": checks}


def run_contract(out_dir: Path, *, broken_allow_all: bool) -> dict[str, Any]:
    ctx = {
        "allowlist": ["+15550001111"],
        "broken_allow_all": broken_allow_all,
        "artifacts_dir": str(out_dir / "contract"),
    }
    checks = run_all(ctx)
    result = "PASS" if all(c.get("result") == "PASS" for c in checks) else "FAIL"

    # Capture outbound from a positive allowlisted path for artifact convention.
    catcher = OutboundMessageCatcher()
    sim = IngressSimulator(
        allowlist=["+15550001111"],
        catcher=catcher,
        broken_allow_all=False,
    )
    sim.handle("+15550001111", "ping", is_group=False)
    outbound_path = out_dir / "contract" / "outbound-messages.json"
    catcher.write_json(outbound_path)

    write_report(
        out_dir / "contract",
        layer="contract",
        result=result,
        checks=checks,
        extra={
            "broken_allow_all": broken_allow_all,
            "outbound_messages": str(outbound_path.relative_to(ROOT)),
            "invariants_discovered": [c.get("id") for c in checks],
        },
    )
    return {"layer": "contract", "result": result, "checks": checks}


def run_e2e(out_dir: Path, *, write_flow_artifacts: bool = True) -> dict[str, Any]:
    """Gate-tagged E2E flows (ci-gates.md). E2E-01..06 Virtual User journeys (T5)."""
    checks: list[dict[str, Any]] = []
    e2e01_dir = ROOT / "artifacts" / "test" / "e2e-01"
    journey01 = run_e2e_01(
        root=ROOT,
        artifacts_dir=e2e01_dir,
        write_artifacts=write_flow_artifacts,
    )
    for check in journey01.checks:
        checks.append(
            {
                "id": check["id"],
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": True,
                "flow": "E2E-01",
            }
        )

    e2e02_dir = ROOT / "artifacts" / "test" / "e2e-02"
    journey02 = run_e2e_02(
        root=ROOT,
        artifacts_dir=e2e02_dir,
        write_artifacts=write_flow_artifacts,
    )
    for check in journey02.checks:
        checks.append(
            {
                "id": check["id"],
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": True,
                "flow": "E2E-02",
            }
        )

    e2e03_dir = ROOT / "artifacts" / "test" / "e2e-03"
    journey03 = run_e2e_03(
        root=ROOT,
        artifacts_dir=e2e03_dir,
        write_artifacts=write_flow_artifacts,
    )
    for check in journey03.checks:
        checks.append(
            {
                "id": check["id"],
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": True,
                "flow": "E2E-03",
            }
        )

    e2e04_dir = ROOT / "artifacts" / "test" / "e2e-04"
    journey04 = run_e2e_04(
        root=ROOT,
        artifacts_dir=e2e04_dir,
        write_artifacts=write_flow_artifacts,
    )
    for check in journey04.checks:
        checks.append(
            {
                "id": check["id"],
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": True,
                "flow": "E2E-04",
            }
        )

    e2e05_dir = ROOT / "artifacts" / "test" / "e2e-05"
    journey05 = run_e2e_05(
        root=ROOT,
        artifacts_dir=e2e05_dir,
        write_artifacts=write_flow_artifacts,
    )
    for check in journey05.checks:
        checks.append(
            {
                "id": check["id"],
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": check.get("gate", True),
                "flow": "E2E-05",
            }
        )

    e2e06_dir = ROOT / "artifacts" / "test" / "e2e-06"
    journey06 = run_e2e_06(
        root=ROOT,
        artifacts_dir=e2e06_dir,
        write_artifacts=write_flow_artifacts,
    )
    for check in journey06.checks:
        checks.append(
            {
                "id": check["id"],
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": True,
                "flow": "E2E-06",
            }
        )

    e2e07_dir = ROOT / "artifacts" / "test" / "e2e-07"
    journey07 = run_e2e_07(
        root=ROOT,
        artifacts_dir=e2e07_dir,
        write_artifacts=write_flow_artifacts,
    )
    for check in journey07.checks:
        checks.append(
            {
                "id": check["id"],
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": True,
                "flow": "E2E-07",
            }
        )

    e2e09_dir = ROOT / "artifacts" / "test" / "e2e-09"
    journey09 = run_e2e_09(
        root=ROOT,
        artifacts_dir=e2e09_dir,
        write_artifacts=write_flow_artifacts,
    )
    for check in journey09.checks:
        checks.append(
            {
                "id": check["id"],
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": check.get("gate", True),
                "flow": "E2E-09",
            }
        )

    # Mirror a compact layer report under ci/e2e for aggregate layout.
    layer_dir = out_dir / "e2e"
    result = (
        "PASS"
        if journey01.ok
        and journey02.ok
        and journey03.ok
        and journey04.ok
        and journey05.ok
        and journey06.ok
        and journey07.ok
        and journey09.ok
        else "FAIL"
    )
    write_report(
        layer_dir,
        layer="e2e",
        result=result,
        checks=checks,
        extra={
            "gate_flows": [
                "E2E-01",
                "E2E-02",
                "E2E-03",
                "E2E-04",
                "E2E-05",
                "E2E-06",
                "E2E-07",
                "E2E-09",
            ],
            "e2e_01_artifacts": "artifacts/test/e2e-01/",
            "e2e_02_artifacts": "artifacts/test/e2e-02/",
            "e2e_03_artifacts": "artifacts/test/e2e-03/",
            "e2e_04_artifacts": "artifacts/test/e2e-04/",
            "e2e_05_artifacts": "artifacts/test/e2e-05/",
            "e2e_06_artifacts": "artifacts/test/e2e-06/",
            "e2e_07_artifacts": "artifacts/test/e2e-07/",
            "e2e_09_artifacts": "artifacts/test/e2e-09/",
            "t4_exit": journey02.ok,
            "t5_exit": journey06.ok,
            "t6_exit": journey07.ok,
            "harness": "VirtualUser",
        },
    )
    return {
        "layer": "e2e",
        "result": result,
        "checks": checks,
        "flows": [
            "E2E-01",
            "E2E-02",
            "E2E-03",
            "E2E-04",
            "E2E-05",
            "E2E-06",
            "E2E-07",
            "E2E-09",
        ],
    }


def run_integration(out_dir: Path) -> dict[str, Any]:
    """Integration stubs + Virtual User wiring checks."""
    checks: list[dict[str, Any]] = []
    catcher = OutboundMessageCatcher()
    clock = FakeClock()
    sim = IngressSimulator(allowlist=["+15550001111"], catcher=catcher)

    # Reject then accept path with clock tick between.
    denied = sim.handle("+19999999999", "nope")
    clock.advance(60)
    allowed = sim.handle("+15550001111", "remind me")
    ok = (
        (not denied.allowed)
        and allowed.allowed
        and catcher.count() == 1
        and sim.counters.tool_calls == 1
        and sim.counters.outbound_sends == 1
    )
    checks.append(
        {
            "id": "integration.ingress_stub.roundtrip",
            "result": "PASS" if ok else "FAIL",
            "detail": (
                f"denied={denied.reason} allowed={allowed.reason} "
                f"outbound={catcher.count()} tools={sim.counters.tool_calls} "
                f"clock={clock.now().isoformat()}"
            ),
        }
    )

    # Mock transport: group_id without is_group still ignored; DM still works.
    t = MockWhatsAppTransport(
        allowlist=["+15550001111"], catcher=OutboundMessageCatcher()
    )
    sneaky = t.inject_text(
        "+15550001111", "sneaky", is_group=False, group_id="120363@g.us"
    )
    dm = t.inject_text("+15550001111", "ok dm")
    group_ok = (
        (not sneaky.allowed)
        and sneaky.reason == "groups_disabled"
        and dm.allowed
        and t.counters.tool_calls == 1
        and t.counters.outbound_sends == 1
    )
    checks.append(
        {
            "id": "integration.mock_whatsapp.group_id_isolation",
            "result": "PASS" if group_ok else "FAIL",
            "detail": (
                f"sneaky={sneaky.reason} dm={dm.reason} "
                f"counters={t.counters.snapshot()}"
            ),
        }
    )

    # Trust core: hard buy without accept cannot execute; accept then execute + audit.
    gw = ActionGateway(clock=FakeClock())
    prop = gw.propose("buy", "integration buy", {"sku": "int-1", "price": 9.99})
    trust_ok = False
    trust_detail = "propose failed"
    if prop.approval_id:
        blocked = gw.execute(prop.approval_id)
        gw.accept(prop.approval_id)
        done = gw.execute(prop.approval_id)
        audits = gw.audit.for_approval(prop.approval_id)
        trust_ok = (
            (not blocked.ok)
            and done.ok
            and gw.commerce.buy_count == 1
            and len(audits) == 1
            and audits[0].approval_id == prop.approval_id
        )
        trust_detail = (
            f"blocked={blocked.reason} executed={done.ok} "
            f"buy_count={gw.commerce.buy_count} audit={len(audits)}"
        )
    checks.append(
        {
            "id": "integration.trust_core.hard_buy_gate",
            "result": "PASS" if trust_ok else "FAIL",
            "detail": trust_detail,
        }
    )

    checks.extend(_run_memory_integration_checks(ROOT))
    checks.extend(_run_task05_hosting_checks(ROOT))
    checks.extend(_run_transcription_integration_checks(ROOT))
    checks.extend(_run_models_integration_checks(ROOT))
    checks.extend(_run_reminder_integration_checks(ROOT))
    checks.extend(_run_voice_integration_checks(ROOT))
    checks.extend(_run_todo_integration_checks(ROOT))
    checks.extend(_run_android_approval_integration_checks(ROOT))
    checks.extend(_run_calendar_integration_checks(ROOT))
    checks.extend(_run_diet_integration_checks(ROOT))
    checks.extend(_run_booking_integration_checks(ROOT))
    checks.extend(_run_shopping_integration_checks(ROOT))

    result = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    layer_dir = out_dir / "integration"
    catcher.write_json(layer_dir / "outbound-messages.json")
    write_report(layer_dir, layer="integration", result=result, checks=checks)
    return {"layer": "integration", "result": result, "checks": checks}


def _run_transcription_unit_checks(root: Path) -> list[dict[str, Any]]:
    """STT fixture map + TTS policy mode rules (assert modes only)."""
    checks: list[dict[str, Any]] = []
    manifest_path = root / "fixtures" / "audio" / "manifest.json"
    manifest = load_manifest(manifest_path)
    clip_ids = {c["id"] for c in manifest.get("clips", [])}
    manifest_ok = (
        manifest_path.is_file()
        and "fx-reminder" in clip_ids
        and "fx-empty" in clip_ids
        and "fx-unclear-buy" in clip_ids
        and (root / "fixtures" / "audio" / "fx-reminder.ogg").is_file()
    )
    checks.append(
        {
            "id": "unit.stt.fixture_manifest",
            "result": "PASS" if manifest_ok else "FAIL",
            "detail": f"clips={sorted(clip_ids)} path={manifest_path}",
        }
    )

    stt = SttStub(manifest_path=manifest_path)
    rem = stt.transcribe("fx-reminder")
    rem_ok = (
        rem.usable
        and rem.outcome is SttOutcome.OK
        and rem.transcript == "Remind me Sunday at 18:00 to call grandma."
        and (rem.turn_body or "").startswith("[Audio] ")
    )
    checks.append(
        {
            "id": "unit.stt.e2e01_fixture_map",
            "result": "PASS" if rem_ok else "FAIL",
            "detail": f"outcome={rem.outcome.value} transcript={rem.transcript!r}",
        }
    )

    empty = stt.transcribe("fx-empty")
    unknown = stt.transcribe("fx-does-not-exist")
    clarify_ok = empty.clarification_needed and unknown.clarification_needed
    checks.append(
        {
            "id": "unit.stt.error_and_unknown_clarify",
            "result": "PASS" if clarify_ok else "FAIL",
            "detail": (
                f"empty={empty.outcome.value} unknown={unknown.outcome.value} "
                f"clarify={clarify_ok}"
            ),
        }
    )

    # Duration bound from manifest (independent of byte size).
    long_ok_clip = SttStub(
        manifest={
            "clips": [
                {
                    "id": "fx-long-ok",
                    "path": "fx-long-ok.ogg",
                    "expected_transcript": "this would be a long note",
                    "outcome": "ok",
                    "confidence": 0.95,
                    "bytes": 64,
                    "duration_sec": 180,
                }
            ],
            "max_bytes": 1024,
            "max_duration_sec": 120,
        }
    )
    over_dur = long_ok_clip.transcribe("fx-long-ok")
    duration_bound_ok = (
        over_dur.clarification_needed
        and over_dur.outcome is SttOutcome.OVERSIZE
        and (over_dur.meta or {}).get("reason") == "duration"
    )
    checks.append(
        {
            "id": "unit.stt.duration_bound",
            "result": "PASS" if duration_bound_ok else "FAIL",
            "detail": (
                f"outcome={over_dur.outcome.value} "
                f"meta={over_dur.meta} clarify={over_dur.clarification_needed}"
            ),
        }
    )

    # TTS policy: inbound mode speaks only for audio; never mode never speaks.
    inbound = TtsPolicySpy(mode=TtsMode.INBOUND)
    never = TtsPolicySpy(mode=TtsMode.NEVER)
    always = TtsPolicySpy(mode=TtsMode.ALWAYS)
    tts_ok = (
        inbound.maybe_speak("hi", inbound_was_audio=True) is True
        and inbound.maybe_speak("hi", inbound_was_audio=False) is False
        and never.maybe_speak("hi", inbound_was_audio=True) is False
        and always.maybe_speak("hi", inbound_was_audio=False) is True
        and inbound.speak_count == 1
        and never.speak_count == 0
        and always.speak_count == 1
    )
    checks.append(
        {
            "id": "unit.tts.mode_policy",
            "result": "PASS" if tts_ok else "FAIL",
            "detail": (
                f"inbound={inbound.snapshot()} never={never.speak_count} "
                f"always={always.speak_count}"
            ),
        }
    )
    return checks


def _run_models_unit_checks(root: Path) -> list[dict[str, Any]]:
    """Models router: fixture table, Luna default, Terra/Sol escalation, stub registry."""
    checks: list[dict[str, Any]] = []
    fixture_path = root / "fixtures" / "models" / "routing-intents.json"
    fixture = load_routing_fixture(fixture_path)
    cases = fixture.get("cases", [])
    fixture_ok = fixture_path.is_file() and len(cases) >= 10
    checks.append(
        {
            "id": "unit.models.fixture_pack",
            "result": "PASS" if fixture_ok else "FAIL",
            "detail": f"path={fixture_path} cases={len(cases)}",
        }
    )

    table_failures: list[str] = []
    for case in cases:
        case_id = case.get("id", "?")
        expected = case.get("expected_model")
        signals = RoutingSignals.from_dict(case.get("signals") or {})
        decision = route(signals)
        if decision.model.value != expected:
            table_failures.append(
                f"{case_id}: expected {expected} got {decision.model.value}"
            )
    table_ok = not table_failures
    checks.append(
        {
            "id": "unit.models.fixture_table",
            "result": "PASS" if table_ok else "FAIL",
            "detail": (
                f"all {len(cases)} cases match"
                if table_ok
                else "; ".join(table_failures[:5])
            ),
        }
    )

    luna_dec = route(RoutingSignals(intent="reminder", utterance="Remind me at 5"))
    luna_ok = luna_dec.model is ModelRole.LUNA and not luna_dec.escalated
    checks.append(
        {
            "id": "unit.models.default_luna",
            "result": "PASS" if luna_ok else "FAIL",
            "detail": f"model={luna_dec.model.value} escalated={luna_dec.escalated}",
        }
    )

    terra_dec = route(
        RoutingSignals(
            intent="booking",
            utterance="retry booking",
            booking_retry=True,
        )
    )
    sol_dec = route(
        RoutingSignals(
            intent="self_mod",
            utterance="patch three files",
            self_mod_files=3,
        )
    )
    escalate_ok = (
        terra_dec.model is ModelRole.TERRA
        and terra_dec.escalated
        and sol_dec.model is ModelRole.SOL
        and sol_dec.escalated
    )
    checks.append(
        {
            "id": "unit.models.terra_sol_escalation",
            "result": "PASS" if escalate_ok else "FAIL",
            "detail": (
                f"terra={terra_dec.model.value} sol={sol_dec.model.value} "
                f"terra_reasons={terra_dec.reasons} sol_reasons={sol_dec.reasons}"
            ),
        }
    )

    registry = ModelStubRegistry()
    luna_stub = registry.complete_as(ModelRole.LUNA, "hello reminder")
    sol_stub = registry.complete_as(ModelRole.SOL, "deep plan week")
    stub_ok = (
        luna_stub.model is ModelRole.LUNA
        and sol_stub.model is ModelRole.SOL
        and luna_stub.stub
        and "[stub:luna]" in luna_stub.text
        and registry.for_role(ModelRole.LUNA).snapshot()["call_count"] == 1
    )
    checks.append(
        {
            "id": "unit.models.stub_registry",
            "result": "PASS" if stub_ok else "FAIL",
            "detail": (
                f"luna_text={luna_stub.text!r} sol_model={sol_stub.model.value} "
                f"snapshot={registry.snapshot()}"
            ),
        }
    )
    return checks


def _run_models_integration_checks(root: Path) -> list[dict[str, Any]]:
    """STT pipeline independent from chat model selection; router + stubs wired."""
    checks: list[dict[str, Any]] = []

    # Chat model stubs never touch STT; pipeline uses SttStub regardless of router.
    pipeline = TranscriptionPipeline.from_fixtures(
        manifest_path=root / "fixtures" / "audio" / "manifest.json"
    )
    registry = ModelStubRegistry()
    chat_dec = route(
        RoutingSignals(intent="reminder", utterance="Remind me Sunday to call grandma")
    )
    chat_completion = registry.complete_as(chat_dec.model, "route then respond")
    audio_turn = pipeline.process_voice_note(audio_fixture_id="fx-reminder")

    stt_indep_ok = (
        chat_dec.model is ModelRole.LUNA
        and chat_completion.model is ModelRole.LUNA
        and audio_turn.is_transcript_turn
        and isinstance(pipeline.stt, SttStub)
        and registry.snapshot()["luna"]["call_count"] == 1
        and pipeline.stt.snapshot().get("call_count", 0) >= 1
    )
    checks.append(
        {
            "id": "integration.models.stt_independent_from_chat",
            "result": "PASS" if stt_indep_ok else "FAIL",
            "detail": (
                f"chat={chat_dec.model.value} stt_type={type(pipeline.stt).__name__} "
                f"transcript_turn={audio_turn.is_transcript_turn} "
                f"stt_calls={pipeline.stt.snapshot().get('call_count')}"
            ),
        }
    )

    # Escalated planning path uses Sol stub without changing STT config.
    sol_signals = RoutingSignals(
        intent="planning",
        utterance="Give me a deep plan for travel and meals",
        multi_day_plan=True,
        has_calendar_constraints=True,
        has_diet_constraints=True,
        has_travel_constraints=True,
    )
    sol_dec = route(sol_signals)
    sol_completion = registry.complete_as(sol_dec.model, "weekly plan draft")
    pipeline2 = TranscriptionPipeline.from_fixtures(
        manifest_path=root / "fixtures" / "audio" / "manifest.json"
    )
    clarify = pipeline2.process_voice_note(audio_fixture_id="fx-empty")
    escalate_path_ok = (
        sol_dec.model is ModelRole.SOL
        and sol_completion.model is ModelRole.SOL
        and clarify.is_clarification
        and isinstance(pipeline2.stt, SttStub)
        and pipeline2.stt is not pipeline.stt
    )
    checks.append(
        {
            "id": "integration.models.sol_planning_with_stt_stub",
            "result": "PASS" if escalate_path_ok else "FAIL",
            "detail": (
                f"sol_dec={sol_dec.model.value} sol_stub={sol_completion.model.value} "
                f"clarify={clarify.is_clarification} stt={pipeline2.stt.snapshot()}"
            ),
        }
    )
    return checks


def _run_reminder_unit_checks() -> list[dict[str, Any]]:
    """One-shot NL due times, recurring weekly across DST, snooze/cancel."""
    checks: list[dict[str, Any]] = []
    tz_name = "Europe/Madrid"
    tz = ZoneInfo(tz_name)
    # E2E-01 setup: Monday 10:00 local.
    monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)
    utterance = "Remind me Sunday at 18:00 to call grandma."
    parsed = parse_reminder(utterance, now=monday, timezone=tz_name)
    expected_due = datetime(2026, 1, 11, 18, 0, 0, tzinfo=tz)
    oneshot_ok = (
        parsed.kind == "one_shot"
        and parsed.body.lower() == "call grandma"
        and parsed.due_at == expected_due
        and parsed.weekday == 6
        and parsed.hour == 18
        and parsed.minute == 0
    )
    checks.append(
        {
            "id": "unit.reminder.oneshot_nl_due",
            "result": "PASS" if oneshot_ok else "FAIL",
            "detail": (
                f"kind={parsed.kind} due={parsed.due_at.isoformat()} "
                f"expected={expected_due.isoformat()} body={parsed.body!r}"
            ),
        }
    )

    # Audio-prefixed transcript still parses (E2E-01 STT turn body).
    audio_utt = "[Audio] Remind me Sunday at 18:00 to call grandma."
    audio_parsed = parse_reminder(audio_utt, now=monday, timezone=tz_name)
    audio_ok = audio_parsed.due_at == expected_due and audio_parsed.body.lower() == "call grandma"
    checks.append(
        {
            "id": "unit.reminder.parse_audio_prefix",
            "result": "PASS" if audio_ok else "FAIL",
            "detail": f"due={audio_parsed.due_at.isoformat()} body={audio_parsed.body!r}",
        }
    )

    # Recurring weekly stable across Europe/Madrid DST spring-forward.
    pre_dst = datetime(2026, 3, 22, 18, 0, 0, tzinfo=tz)  # Sunday CET
    post = next_weekly_after(pre_dst, weekday=6, hour=18, minute=0)
    dst_ok = (
        post.weekday() == 6
        and post.hour == 18
        and post.minute == 0
        and post.tzinfo is not None
        and post.utcoffset() != pre_dst.utcoffset()
    )
    checks.append(
        {
            "id": "unit.reminder.recurring_weekly_dst",
            "result": "PASS" if dst_ok else "FAIL",
            "detail": (
                f"pre={pre_dst.isoformat()} post={post.isoformat()} "
                f"offsets={pre_dst.utcoffset()}→{post.utcoffset()}"
            ),
        }
    )

    # Recurring parse: every Sunday.
    every = parse_reminder(
        "every Sunday remind me to call grandma",
        now=monday,
        timezone=tz_name,
    )
    every_ok = every.kind == "recurring" and every.weekday == 6 and every.due_at == expected_due
    checks.append(
        {
            "id": "unit.reminder.recurring_every_sunday",
            "result": "PASS" if every_ok else "FAIL",
            "detail": f"kind={every.kind} due={every.due_at.isoformat()}",
        }
    )

    # Auto tier mapping for reminder/habit create.
    tier_ok = (
        tier_for("reminder_create") == ApprovalTier.AUTO
        and tier_for("habit_create") == ApprovalTier.AUTO
    )
    checks.append(
        {
            "id": "unit.reminder.auto_approval_tier",
            "result": "PASS" if tier_ok else "FAIL",
            "detail": (
                f"reminder_create={tier_for('reminder_create').value} "
                f"habit_create={tier_for('habit_create').value}"
            ),
        }
    )

    # Snooze / cancel state machine (unit on store).
    store = ReminderStore()
    clock = FakeClock(start=monday.astimezone(ZoneInfo("UTC")))
    rem = store.create(
        text="call grandma",
        timezone=tz_name,
        kind=ReminderKind.ONE_SHOT,
        due_at=expected_due,
        created_at=clock.now(),
        hour=18,
        minute=0,
        weekday=6,
        recipient="+15550001111",
    )
    snooze_until = expected_due + timedelta(hours=1)
    store.snooze(rem.id, snooze_until)
    snoozed = store.get(rem.id)
    snooze_status = snoozed.status if snoozed else None
    snooze_due = snoozed.due_at if snoozed else None
    store.cancel(rem.id)
    cancelled = store.get(rem.id)
    sc_ok = (
        snooze_status == ReminderStatus.SNOOZED
        and snooze_due == snooze_until
        and cancelled is not None
        and cancelled.status == ReminderStatus.CANCELLED
        and rem.id not in {r.id for r in store.due(snooze_until + timedelta(seconds=1))}
    )
    checks.append(
        {
            "id": "unit.reminder.snooze_cancel",
            "result": "PASS" if sc_ok else "FAIL",
            "detail": (
                f"snooze={snooze_status.value if snooze_status else None} "
                f"cancel={cancelled.status.value if cancelled else None}"
            ),
        }
    )
    return checks


def _run_reminder_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Create + confirm outbound; fire via FakeClock.advance; habit WhatsApp first step."""
    checks: list[dict[str, Any]] = []
    tz_name = "Europe/Madrid"
    tz = ZoneInfo(tz_name)
    owner = "+15550001111"
    seed_path = root / "fixtures" / "memory" / "seed-profile.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    seed_tz = seed.get("identity", {}).get("timezone") or tz_name

    # E2E-01-shaped: Monday 10:00 → create from transcript → confirm; no hard approval.
    monday_local = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)
    clock = FakeClock(start=monday_local)
    catcher = OutboundMessageCatcher()
    store = ReminderStore()
    gw = ActionGateway(clock=clock, reminders=store)
    svc = ReminderService(
        store=store,
        clock=clock,
        catcher=catcher,
        gateway=gw,
        timezone=seed_tz,
        recipient=owner,
    )
    created = svc.create_from_utterance(
        "Remind me Sunday at 18:00 to call grandma.",
        timezone=seed_tz,
    )
    expected_due = datetime(2026, 1, 11, 18, 0, 0, tzinfo=tz)
    pending_approvals = gw.approvals.list(status=ApprovalStatus.PENDING)
    hard_items = [
        i
        for i in gw.approvals.list()
        if i.action_type in {"reminder_create", "habit_create"}
    ]
    create_ok = (
        created.ok
        and created.reminder is not None
        and created.reminder.due_at == expected_due
        and created.tier == "auto"
        and created.approval_id is None
        and catcher.count() == 1
        and catcher.messages[0].meta.get("kind") == "reminder_confirm"
        and "call grandma" in catcher.messages[0].body.lower()
        and len(hard_items) == 0
        and len(pending_approvals) == 0
        and seed_tz == "Europe/Madrid"
    )
    checks.append(
        {
            "id": "integration.reminder.e2e01_create_confirm",
            "result": "PASS" if create_ok else "FAIL",
            "detail": (
                f"ok={created.ok} due={created.reminder.due_at.isoformat() if created.reminder else None} "
                f"tier={created.tier} approval_id={created.approval_id} "
                f"outbound={catcher.count()} hard_items={len(hard_items)} "
                f"seed_tz={seed_tz}"
            ),
        }
    )

    # Advance fake clock to due → fire reminder outbound (no wall sleep).
    assert created.reminder is not None
    delta = expected_due - clock.now()
    scheduler = ReminderScheduler(
        store, clock, catcher, kill=gw.kill, default_recipient=owner
    )
    fires = scheduler.advance(delta)
    rem_after = store.get(created.reminder.id)
    fire_ok = (
        len(fires) == 1
        and fires[0].emitted
        and fires[0].reason == "ok"
        and rem_after is not None
        and rem_after.status == ReminderStatus.FIRED
        and rem_after.fire_count == 1
        and any(m.meta.get("kind") == "reminder_fire" for m in catcher.messages)
        and any("Reminder: call grandma" == m.body for m in catcher.messages)
    )
    checks.append(
        {
            "id": "integration.reminder.clock_advance_fire",
            "result": "PASS" if fire_ok else "FAIL",
            "detail": (
                f"fires={len(fires)} status={rem_after.status.value if rem_after else None} "
                f"fire_count={rem_after.fire_count if rem_after else None} "
                f"outbound={catcher.count()}"
            ),
        }
    )

    # Habit scaffolding: high-priority recurring → WhatsApp first escalation step.
    clock2 = FakeClock(start=monday_local)
    catcher2 = OutboundMessageCatcher()
    store2 = ReminderStore()
    gw2 = ActionGateway(clock=clock2, reminders=store2)
    svc2 = ReminderService(
        store=store2,
        clock=clock2,
        catcher=catcher2,
        gateway=gw2,
        timezone=tz_name,
        recipient=owner,
    )
    habit_created = svc2.create_from_utterance(
        "every Sunday at 18:00 remind me to stretch",
        as_habit=True,
        habit_priority="high",
        escalation_enabled=True,
    )
    habit = habit_created.habit
    channel_before = habit.current_channel() if habit else None
    step_before = habit.escalation_step if habit else None
    sched2 = ReminderScheduler(
        store2, clock2, catcher2, kill=gw2.kill, default_recipient=owner
    )
    due2 = habit_created.reminder.due_at if habit_created.reminder else expected_due
    fires2 = sched2.advance(due2 - clock2.now())
    habit_after = store2.get_habit(habit.id) if habit else None
    habit_ok = (
        habit_created.ok
        and habit is not None
        and habit.priority == "high"
        and channel_before is EscalationChannel.WHATSAPP
        and step_before == 0
        and len(fires2) == 1
        and fires2[0].emitted
        and fires2[0].channel == "whatsapp"
        and any(m.body.startswith("Habit reminder:") for m in catcher2.messages)
        and habit_after is not None
        # After WhatsApp fire without completion, ladder advances toward Android.
        and habit_after.escalation_step == 1
        and habit_after.current_channel() is EscalationChannel.ANDROID
    )
    checks.append(
        {
            "id": "integration.habit.whatsapp_first_step",
            "result": "PASS" if habit_ok else "FAIL",
            "detail": (
                f"ok={habit_created.ok} step_before=0 "
                f"step_after={habit_after.escalation_step if habit_after else None} "
                f"channel={fires2[0].channel if fires2 else None} "
                f"fires={len(fires2)}"
            ),
        }
    )

    # Pause agent blocks proactive reminder fires (capabilities contract case).
    clock3 = FakeClock(start=monday_local)
    catcher3 = OutboundMessageCatcher()
    store3 = ReminderStore()
    gw3 = ActionGateway(clock=clock3, reminders=store3)
    svc3 = ReminderService(
        store=store3, clock=clock3, catcher=catcher3, gateway=gw3, timezone=tz_name, recipient=owner
    )
    created3 = svc3.create_from_utterance(
        "Remind me Sunday at 18:00 to call grandma.",
        timezone=tz_name,
    )
    gw3.pause_agent()
    sched3 = ReminderScheduler(
        store3, clock3, catcher3, kill=gw3.kill, default_recipient=owner
    )
    assert created3.reminder is not None
    blocked = sched3.advance(created3.reminder.due_at - clock3.now())
    pause_ok = (
        len(blocked) == 1
        and (not blocked[0].emitted)
        and blocked[0].reason == "pause_agent"
        and not any(m.meta.get("kind") == "reminder_fire" for m in catcher3.messages)
        and store3.get(created3.reminder.id) is not None
        and store3.get(created3.reminder.id).status == ReminderStatus.ACTIVE
    )
    checks.append(
        {
            "id": "integration.reminder.pause_stops_fire",
            "result": "PASS" if pause_ok else "FAIL",
            "detail": (
                f"emitted={blocked[0].emitted if blocked else None} "
                f"reason={blocked[0].reason if blocked else None} "
                f"fire_msgs={sum(1 for m in catcher3.messages if m.meta.get('kind')=='reminder_fire')}"
            ),
        }
    )

    # Snooze then fire after snooze_until via clock.advance.
    clock4 = FakeClock(start=monday_local)
    catcher4 = OutboundMessageCatcher()
    store4 = ReminderStore()
    rem4 = store4.create(
        text="water plants",
        timezone=tz_name,
        kind=ReminderKind.ONE_SHOT,
        due_at=expected_due,
        created_at=clock4.now(),
        hour=18,
        minute=0,
        weekday=6,
        recipient=owner,
    )
    snooze_until = expected_due + timedelta(hours=2)
    store4.snooze(rem4.id, snooze_until)
    sched4 = ReminderScheduler(store4, clock4, catcher4, default_recipient=owner)
    early = sched4.advance(expected_due - clock4.now())
    later = sched4.advance(timedelta(hours=2))
    snooze_fire_ok = (
        len(early) == 0
        and len(later) == 1
        and later[0].emitted
        and store4.get(rem4.id).status == ReminderStatus.FIRED
    )
    checks.append(
        {
            "id": "integration.reminder.snooze_then_fire",
            "result": "PASS" if snooze_fire_ok else "FAIL",
            "detail": f"early={len(early)} later={len(later)}",
        }
    )
    return checks


def _run_voice_unit_checks() -> list[dict[str, Any]]:
    """Mock voice provider: place call, tool allowlist, after-call summary."""
    checks: list[dict[str, Any]] = []
    owner = "+15550001111"

    allow_ok = (
        is_call_mode_allowed("calendar_read")
        and is_call_mode_allowed("todo_read")
        and not is_call_mode_allowed("buy")
        and not is_call_mode_allowed("book")
        and not is_call_mode_allowed("self_mod_apply")
        and call_mode_block_reason("buy") == "call_mode_forbidden_hard_action"
        and call_mode_block_reason("calendar_create") == "call_mode_tool_not_allowlisted"
        and call_mode_block_reason("calendar_read") is None
        and CALL_MODE_FORBIDDEN_TOOLS == frozenset({"buy", "book", "self_mod_apply"})
        and "calendar_read" in CALL_MODE_ALLOWED_TOOLS
    )
    checks.append(
        {
            "id": "unit.voice.call_mode_allowlist",
            "result": "PASS" if allow_ok else "FAIL",
            "detail": (
                f"allowed={sorted(CALL_MODE_ALLOWED_TOOLS)} "
                f"forbidden={sorted(CALL_MODE_FORBIDDEN_TOOLS)}"
            ),
        }
    )

    clock = FakeClock()
    catcher = OutboundMessageCatcher()
    voice = MockVoiceProvider(catcher, clock, default_to=owner)
    session = voice.place_call(script="Calling about: stretch", reminder_id="r1")
    read = voice.invoke_tool(session.id, "memory_read", {"key": "prefs"})
    buy = voice.invoke_tool(session.id, "buy", {"sku": "x"})
    book = voice.invoke_tool(session.id, "book", {"shop": "y"})
    apply = voice.invoke_tool(session.id, "self_mod_apply", {"path": "z"})
    ended = voice.end_call(session.id, outcome="done")
    summaries = [
        m for m in catcher.messages if m.meta.get("kind") == "after_call_summary"
    ]
    call_msgs = [m for m in catcher.messages if m.meta.get("kind") == "outbound_call"]
    provider_ok = (
        session.status == "ended"
        and voice.call_count == 1
        and read.ok
        and (not buy.ok)
        and (not book.ok)
        and (not apply.ok)
        and buy.reason == "call_mode_forbidden_hard_action"
        and ended.summary_queued
        and len(summaries) == 1
        and summaries[0].channel == "whatsapp"
        and len(call_msgs) == 1
        and call_msgs[0].channel == "call"
        and len(voice.forbidden_attempts()) == 3
    )
    checks.append(
        {
            "id": "unit.voice.mock_provider_place_and_tools",
            "result": "PASS" if provider_ok else "FAIL",
            "detail": (
                f"call_count={voice.call_count} read_ok={read.ok} "
                f"buy={buy.reason} summaries={len(summaries)} "
                f"forbidden={len(voice.forbidden_attempts())}"
            ),
        }
    )
    return checks


def _run_voice_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Escalation ladder WhatsApp → Android → call + after-call summary (E2E-02 prep)."""
    _ = root
    checks: list[dict[str, Any]] = []
    tz_name = "Europe/Madrid"
    tz = ZoneInfo(tz_name)
    monday_local = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)
    owner = "+15550001111"

    clock = FakeClock(start=monday_local)
    catcher = OutboundMessageCatcher()
    store = ReminderStore()
    gw = ActionGateway(clock=clock, reminders=store)
    voice = MockVoiceProvider(catcher, clock, default_to=owner)
    android = AndroidNotificationCatcher(clock, catcher, default_to=owner)
    svc = ReminderService(
        store=store,
        clock=clock,
        catcher=catcher,
        gateway=gw,
        timezone=tz_name,
        recipient=owner,
    )
    created = svc.create_from_utterance(
        "every Sunday at 18:00 remind me to stretch",
        as_habit=True,
        habit_priority="high",
        escalation_enabled=True,
    )
    habit = created.habit
    assert habit is not None and created.reminder is not None

    sched = ReminderScheduler(
        store,
        clock,
        catcher,
        kill=gw.kill,
        default_recipient=owner,
        voice=voice,
        android=android,
    )

    # Step 1 — WhatsApp
    fires1 = sched.advance(created.reminder.due_at - clock.now())
    habit1 = store.get_habit(habit.id)
    step1_ok = (
        created.ok
        and len(fires1) == 1
        and fires1[0].emitted
        and fires1[0].channel == "whatsapp"
        and any(m.body.startswith("Habit reminder:") for m in catcher.messages)
        and habit1 is not None
        and habit1.escalation_step == 1
        and habit1.current_channel() is EscalationChannel.ANDROID
        and voice.call_count == 0
        and android.count() == 0
    )
    checks.append(
        {
            "id": "integration.voice.escalation_whatsapp_step",
            "result": "PASS" if step1_ok else "FAIL",
            "detail": (
                f"channel={fires1[0].channel if fires1 else None} "
                f"step={habit1.escalation_step if habit1 else None} "
                f"calls={voice.call_count}"
            ),
        }
    )

    # Step 2 — Android (next weekly due)
    rem_after_1 = store.get(created.reminder.id)
    assert rem_after_1 is not None
    fires2 = sched.advance(rem_after_1.due_at - clock.now())
    habit2 = store.get_habit(habit.id)
    step2_ok = (
        len(fires2) == 1
        and fires2[0].emitted
        and fires2[0].channel == "android"
        and fires2[0].notification_id is not None
        and android.count() == 1
        and any(m.channel == "android" for m in catcher.messages)
        and habit2 is not None
        and habit2.escalation_step == 2
        and habit2.current_channel() is EscalationChannel.CALL
        and voice.call_count == 0
    )
    checks.append(
        {
            "id": "integration.voice.escalation_android_step",
            "result": "PASS" if step2_ok else "FAIL",
            "detail": (
                f"channel={fires2[0].channel if fires2 else None} "
                f"android_nudge={android.count()} "
                f"step={habit2.escalation_step if habit2 else None}"
            ),
        }
    )

    # Step 3 — Call + after-call WhatsApp summary
    rem_after_2 = store.get(created.reminder.id)
    assert rem_after_2 is not None
    fires3 = sched.advance(rem_after_2.due_at - clock.now())
    habit3 = store.get_habit(habit.id)
    summaries = [
        m
        for m in catcher.messages
        if m.meta.get("kind") == "after_call_summary" and m.channel == "whatsapp"
    ]
    call_msgs = [m for m in catcher.messages if m.channel == "call"]
    step3_ok = (
        len(fires3) == 1
        and fires3[0].emitted
        and fires3[0].channel == "call"
        and fires3[0].call_id is not None
        and fires3[0].summary_queued
        and voice.call_count == 1
        and voice.calls[0].status == "ended"
        and voice.calls[0].summary_queued
        and len(summaries) == 1
        and len(call_msgs) == 1
        and habit3 is not None
        and habit3.current_channel() is EscalationChannel.CALL
    )
    checks.append(
        {
            "id": "integration.voice.escalation_call_and_summary",
            "result": "PASS" if step3_ok else "FAIL",
            "detail": (
                f"channel={fires3[0].channel if fires3 else None} "
                f"call_id={fires3[0].call_id if fires3 else None} "
                f"summary_queued={fires3[0].summary_queued if fires3 else None} "
                f"summaries={len(summaries)}"
            ),
        }
    )

    # Ordered channel touches for E2E-02 readiness.
    touch_order = [f.channel for f in (fires1 + fires2 + fires3) if f.emitted]
    order_ok = touch_order == ["whatsapp", "android", "call"]
    checks.append(
        {
            "id": "integration.voice.escalation_ordered_touches",
            "result": "PASS" if order_ok else "FAIL",
            "detail": f"order={touch_order}",
        }
    )

    # Mid-call hard tools blocked (INV-APPR-005 path via live session before end).
    # Use a fresh active call to probe tools (prior call already ended).
    live = voice.place_call(script="Calling about: probe", reminder_id="probe")
    blocked = []
    for tool in ("buy", "book", "self_mod_apply"):
        res = voice.invoke_tool(live.id, tool, {"item": tool})
        blocked.append(not res.ok and res.reason == "call_mode_forbidden_hard_action")
    read_ok = voice.invoke_tool(live.id, "todo_read", {}).ok
    voice.end_call(live.id, outcome="probe_done")
    appr005_ok = all(blocked) and read_ok
    checks.append(
        {
            "id": "integration.voice.call_mode_blocks_hard_tools",
            "result": "PASS" if appr005_ok else "FAIL",
            "detail": f"blocked={blocked} read_ok={read_ok}",
        }
    )

    # EscalationLadder helper still exposes channel_touch_order for E2E-02.
    ladder = EscalationLadder(
        ReminderStore(),
        FakeClock(start=monday_local),
        OutboundMessageCatcher(),
        default_recipient=owner,
    )
    ladder_ok = ladder.voice is not None and ladder.android is not None
    checks.append(
        {
            "id": "integration.voice.escalation_ladder_scaffold",
            "result": "PASS" if ladder_ok else "FAIL",
            "detail": f"voice={type(ladder.voice).__name__} android={type(ladder.android).__name__}",
        }
    )
    return checks


def _run_todo_unit_checks() -> list[dict[str, Any]]:
    """Parse todo utterances, store CRUD, dedup near-identical open todos."""
    checks: list[dict[str, Any]] = []

    parsed = parse_todo("Add todo: buy oat milk.")
    parse_ok = parsed.title.lower() == "buy oat milk"
    checks.append(
        {
            "id": "unit.todo.parse_add_utterance",
            "result": "PASS" if parse_ok else "FAIL",
            "detail": f"title={parsed.title!r}",
        }
    )

    audio_parsed = parse_todo("[Audio] Add todo: buy oat milk.")
    audio_ok = audio_parsed.title.lower() == "buy oat milk"
    checks.append(
        {
            "id": "unit.todo.parse_audio_prefix",
            "result": "PASS" if audio_ok else "FAIL",
            "detail": f"title={audio_parsed.title!r}",
        }
    )

    intent_ok = looks_like_todo_add("Add a todo: pack for trip") and not looks_like_todo_add(
        "Remind me Sunday"
    )
    checks.append(
        {
            "id": "unit.todo.intent_detection",
            "result": "PASS" if intent_ok else "FAIL",
            "detail": f"todo={looks_like_todo_add('Add a todo: pack')} rem={looks_like_todo_add('Remind me')}",
        }
    )

    tier_ok = (
        tier_for("todo_add") == ApprovalTier.AUTO
        and tier_for("todo_complete") == ApprovalTier.AUTO
    )
    checks.append(
        {
            "id": "unit.todo.auto_approval_tier",
            "result": "PASS" if tier_ok else "FAIL",
            "detail": (
                f"todo_add={tier_for('todo_add').value} "
                f"todo_complete={tier_for('todo_complete').value}"
            ),
        }
    )

    clock = FakeClock()
    store = TodoStore()
    t1 = store.create(title="Buy oat milk", created_at=clock.now(), created_from=TodoSource.WHATSAPP)
    open_status = t1.status
    dup = store.find_open_duplicate("buy oat milk")
    t2 = store.complete(t1.id, completed_at=clock.now(), completed_from=TodoSource.ANDROID)
    crud_ok = (
        t1.id.startswith("todo-")
        and open_status == TodoStatus.OPEN
        and dup is not None
        and dup.id == t1.id
        and t2.status == TodoStatus.DONE
        and len(store.list_open()) == 0
    )
    checks.append(
        {
            "id": "unit.todo.create_list_complete",
            "result": "PASS" if crud_ok else "FAIL",
            "detail": (
                f"id={t1.id} dup={dup.id if dup else None} "
                f"done={t2.status.value} open={len(store.list_open())}"
            ),
        }
    )

    store2 = TodoStore()
    store2.create(title="Buy protein powder", created_at=clock.now())
    near_dup = store2.find_open_duplicate("buy protein powder!")
    dedup_ok = near_dup is not None and normalize_title(near_dup.title) == normalize_title(
        "buy protein powder!"
    )
    checks.append(
        {
            "id": "unit.todo.dedup_near_identical",
            "result": "PASS" if dedup_ok else "FAIL",
            "detail": f"found={near_dup.title if near_dup else None}",
        }
    )

    return checks


def _run_calendar_unit_checks(root: Path) -> list[dict[str, Any]]:
    """Calendar parse, conflicts, free slots, soft-confirm tier."""
    checks: list[dict[str, Any]] = []
    tz = ZoneInfo("Europe/Madrid")
    monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)

    parsed = parse_schedule(
        EXPECTED_E2E04_UTTERANCE,
        now=monday,
        timezone="Europe/Madrid",
    )
    parse_ok = (
        parsed.title.lower() == "focus block"
        and parsed.start.isoformat() == "2026-01-09T09:00:00+01:00"
        and parsed.end.isoformat() == "2026-01-09T11:00:00+01:00"
        and parsed.weekday == 4
    )
    checks.append(
        {
            "id": "unit.calendar.parse_e2e04_utterance",
            "result": "PASS" if parse_ok else "FAIL",
            "detail": (
                f"title={parsed.title!r} start={parsed.start.isoformat()} "
                f"end={parsed.end.isoformat()}"
            ),
        }
    )

    hyphen = parse_schedule(
        "Schedule focus block Friday 09:00-11:00.",
        now=monday,
        timezone="Europe/Madrid",
    )
    hyphen_ok = hyphen.start == parsed.start and hyphen.end == parsed.end
    checks.append(
        {
            "id": "unit.calendar.parse_hyphen_range",
            "result": "PASS" if hyphen_ok else "FAIL",
            "detail": f"start={hyphen.start.isoformat()} end={hyphen.end.isoformat()}",
        }
    )

    intent_ok = looks_like_schedule(EXPECTED_E2E04_UTTERANCE) and not looks_like_schedule(
        "Remind me Sunday"
    )
    checks.append(
        {
            "id": "unit.calendar.intent_detection",
            "result": "PASS" if intent_ok else "FAIL",
            "detail": f"schedule={looks_like_schedule(EXPECTED_E2E04_UTTERANCE)}",
        }
    )

    tier_ok = (
        tier_for("calendar_create") == ApprovalTier.SOFT_CONFIRM
        and tier_for("calendar_read") == ApprovalTier.AUTO
        and tier_for("calendar_modify") == ApprovalTier.SOFT_CONFIRM
    )
    checks.append(
        {
            "id": "unit.calendar.soft_confirm_tier",
            "result": "PASS" if tier_ok else "FAIL",
            "detail": (
                f"create={tier_for('calendar_create').value} "
                f"read={tier_for('calendar_read').value}"
            ),
        }
    )

    store = CalendarStore()
    fixture = root / "fixtures" / "calendar" / "busy-friday.json"
    seeded = store.load_fixture(fixture)
    focus_start = datetime(2026, 1, 9, 9, 0, 0, tzinfo=tz)
    focus_end = datetime(2026, 1, 9, 11, 0, 0, tzinfo=tz)
    conflicts = store.find_conflicts(focus_start, focus_end, title="Focus block")
    conflict_ok = len(seeded) == 3 and len(conflicts) >= 1 and any(
        c.existing_id == "evt-standup" for c in conflicts
    )
    checks.append(
        {
            "id": "unit.calendar.conflict_detection",
            "result": "PASS" if conflict_ok else "FAIL",
            "detail": (
                f"seeded={len(seeded)} conflicts={len(conflicts)} "
                f"ids={[c.existing_id for c in conflicts]}"
            ),
        }
    )

    slots = store.suggest_free_slots(
        day_start=datetime(2026, 1, 9, 9, 0, 0, tzinfo=tz),
        day_end=datetime(2026, 1, 9, 18, 0, 0, tzinfo=tz),
        duration=timedelta(hours=2),
        limit=3,
    )
    # 09:00–11:00 overlaps standup; free 2h should start at/after 10:00 or later windows.
    free_ok = len(slots) >= 1 and all(
        store.find_conflicts(s.start, s.end) == [] for s in slots
    )
    checks.append(
        {
            "id": "unit.calendar.suggest_free_slots",
            "result": "PASS" if free_ok else "FAIL",
            "detail": f"slots={[s.to_dict() for s in slots]}",
        }
    )

    # Touching endpoints do not conflict.
    touch = store.find_conflicts(
        datetime(2026, 1, 9, 10, 0, 0, tzinfo=tz),
        datetime(2026, 1, 9, 12, 0, 0, tzinfo=tz),
    )
    # standup ends 10:00 — touching ok; lunch starts 12:00 — touching ok; none overlap half-open.
    # Wait: 10:00-12:00 vs lunch 12:00-13:00 — no overlap. vs standup 09:30-10:00 — no overlap.
    touch_ok = len(touch) == 0
    checks.append(
        {
            "id": "unit.calendar.touching_endpoints_ok",
            "result": "PASS" if touch_ok else "FAIL",
            "detail": f"conflicts={len(touch)}",
        }
    )

    return checks


def _run_calendar_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Soft-confirm propose → Accept creates once; Deny creates nothing; NL path."""
    checks: list[dict[str, Any]] = []
    owner = "+15550001111"
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    store = CalendarStore()
    gw = ActionGateway(clock=clock)
    gw.calendar.attach_store(store)
    svc = CalendarService(
        store=store,
        clock=clock,
        catcher=catcher,
        gateway=gw,
        timezone="Europe/Madrid",
        recipient=owner,
    )

    proposed = svc.propose_from_utterance(EXPECTED_E2E04_UTTERANCE)
    pending = gw.approvals.list(status=ApprovalStatus.PENDING)
    propose_ok = (
        proposed.ok
        and proposed.approval_id is not None
        and proposed.tier == ApprovalTier.SOFT_CONFIRM.value
        and not proposed.executed
        and gw.calendar.create_count == 0
        and len(store.list_all()) == 0
        and len(pending) == 1
        and catcher.count() == 1
        and catcher.messages[0].meta.get("kind") == "calendar_propose"
        and proposed.parsed is not None
        and proposed.parsed.start.isoformat() == "2026-01-09T09:00:00+01:00"
    )
    checks.append(
        {
            "id": "integration.calendar.nl_propose_soft_confirm",
            "result": "PASS" if propose_ok else "FAIL",
            "detail": (
                f"ok={proposed.ok} approval={proposed.approval_id} "
                f"create={gw.calendar.create_count} pending={len(pending)} "
                f"reason={proposed.reason}"
            ),
        }
    )

    inbox = AndroidApprovalInboxApi(gw)
    accepted = inbox.accept(proposed.approval_id) if proposed.approval_id else None
    accept_ok = (
        accepted is not None
        and accepted.ok
        and gw.calendar.create_count == 1
        and len(store.list_all()) == 1
        and store.list_all()[0].title.lower() == "focus block"
    )
    checks.append(
        {
            "id": "integration.calendar.accept_creates_once",
            "result": "PASS" if accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(accepted, 'ok', None)} create={gw.calendar.create_count} "
                f"events={len(store.list_all())}"
            ),
        }
    )

    # Deny path: seed conflict store separately.
    clock2 = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher2 = OutboundMessageCatcher()
    store2 = CalendarStore()
    gw2 = ActionGateway(clock=clock2)
    gw2.calendar.attach_store(store2)
    svc2 = CalendarService(
        store=store2,
        clock=clock2,
        catcher=catcher2,
        gateway=gw2,
        timezone="Europe/Madrid",
        recipient=owner,
    )
    denied_prop = svc2.propose_from_utterance("Schedule dentist Saturday 15:00–16:00.")
    inbox2 = AndroidApprovalInboxApi(gw2)
    denied = inbox2.deny(denied_prop.approval_id) if denied_prop.approval_id else None
    late = gw2.execute(denied_prop.approval_id) if denied_prop.approval_id else None
    deny_ok = (
        denied_prop.ok
        and denied is not None
        and denied.status == ApprovalStatus.DENIED.value
        and gw2.calendar.create_count == 0
        and len(store2.list_all()) == 0
        and late is not None
        and (not late.ok)
    )
    checks.append(
        {
            "id": "integration.calendar.deny_creates_nothing",
            "result": "PASS" if deny_ok else "FAIL",
            "detail": (
                f"deny={denied.status if denied else None} create={gw2.calendar.create_count} "
                f"late={getattr(late, 'reason', None)}"
            ),
        }
    )

    # Conflict-aware proposal still soft-confirms (calls out conflict; no write).
    store3 = CalendarStore()
    store3.load_fixture(root / "fixtures" / "calendar" / "busy-friday.json")
    clock3 = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher3 = OutboundMessageCatcher()
    gw3 = ActionGateway(clock=clock3)
    gw3.calendar.attach_store(store3)
    svc3 = CalendarService(
        store=store3,
        clock=clock3,
        catcher=catcher3,
        gateway=gw3,
        timezone="Europe/Madrid",
        recipient=owner,
    )
    conflicted = svc3.propose_from_utterance(EXPECTED_E2E04_UTTERANCE)
    conflict_ok = (
        conflicted.ok
        and len(conflicted.conflicts) >= 1
        and len(conflicted.suggestions) >= 1
        and gw3.calendar.create_count == 0
        and "Conflict" in conflicted.confirm_body
        and len(store3.list_all()) == 3  # seeded only; no write
    )
    checks.append(
        {
            "id": "integration.calendar.conflict_aware_propose",
            "result": "PASS" if conflict_ok else "FAIL",
            "detail": (
                f"conflicts={len(conflicted.conflicts)} "
                f"suggestions={len(conflicted.suggestions)} "
                f"create={gw3.calendar.create_count} body={conflicted.confirm_body!r}"
            ),
        }
    )

    # Virtual User WhatsApp NL → pending soft confirm (E2E-04 readiness).
    vu = VirtualUser.bootstrap(root=root)
    turn = vu.inject_text(EXPECTED_E2E04_UTTERANCE)
    vu_ok = (
        turn.allowed
        and "calendar_propose" in turn.tool_calls
        and vu.calendar_create_count() == 0
        and len(vu.pending_approvals()) == 1
        and vu.last_calendar_propose is not None
        and vu.last_calendar_propose.ok
        and vu.last_calendar_propose.parsed is not None
        and vu.last_calendar_propose.parsed.start.isoformat()
        == "2026-01-09T09:00:00+01:00"
    )
    checks.append(
        {
            "id": "integration.calendar.virtual_user_nl_path",
            "result": "PASS" if vu_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} create={vu.calendar_create_count()} "
                f"pending={len(vu.pending_approvals())}"
            ),
        }
    )

    # Accept via Android after NL propose.
    appr_id = vu.last_calendar_propose.approval_id if vu.last_calendar_propose else None
    vu_accept = vu.accept_approval(appr_id) if appr_id else None
    vu_accept_ok = (
        vu_accept is not None
        and vu_accept.ok
        and vu.calendar_create_count() == 1
        and len(vu.calendar_store.list_all()) == 1
    )
    checks.append(
        {
            "id": "integration.calendar.virtual_user_accept",
            "result": "PASS" if vu_accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(vu_accept, 'ok', None)} "
                f"create={vu.calendar_create_count()}"
            ),
        }
    )

    return checks


def _run_diet_unit_checks(root: Path) -> list[dict[str, Any]]:
    """Diet parse, constraint checks, planner selection."""
    checks: list[dict[str, Any]] = []
    tz = ZoneInfo("Europe/Madrid")
    monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)

    parsed = parse_meal_plan_request(EXPECTED_E2E05_UTTERANCE, now=monday)
    parse_ok = (
        parsed.target_phrase == "tomorrow"
        and parsed.plan_date.isoformat() == "2026-01-06"
    )
    checks.append(
        {
            "id": "unit.diet.parse_tomorrow",
            "result": "PASS" if parse_ok else "FAIL",
            "detail": (
                f"phrase={parsed.target_phrase!r} date={parsed.plan_date.isoformat()}"
            ),
        }
    )

    intent_ok = looks_like_meal_plan(EXPECTED_E2E05_UTTERANCE) and not looks_like_meal_plan(
        "Add todo: buy oat milk"
    )
    checks.append(
        {
            "id": "unit.diet.intent_detection",
            "result": "PASS" if intent_ok else "FAIL",
            "detail": f"meal_plan={looks_like_meal_plan(EXPECTED_E2E05_UTTERANCE)}",
        }
    )

    tier_ok = tier_for("diet_draft") == ApprovalTier.AUTO
    checks.append(
        {
            "id": "unit.diet.auto_tier",
            "result": "PASS" if tier_ok else "FAIL",
            "detail": f"tier={tier_for('diet_draft').value}",
        }
    )

    fixture = root / "fixtures" / "memory" / "seed-profile.json"
    store = MemoryStore.seed_from_fixture(root / "artifacts" / "test" / ".unit-diet-mem", fixture)
    constraints = store.planning_constraints()
    banned = banned_terms(constraints)
    banned_ok = "peanuts" in banned and "shellfish" in banned and "rice" in banned
    checks.append(
        {
            "id": "unit.diet.banned_terms_from_memory",
            "result": "PASS" if banned_ok else "FAIL",
            "detail": f"banned={sorted(banned)}",
        }
    )

    calendar = CalendarStore()
    plan = build_meal_plan(
        plan_date=parsed.plan_date,
        timezone="Europe/Madrid",
        constraints=constraints,
        calendar=calendar,
    )
    check = check_meal_plan(
        meals=[m.to_dict() for m in plan.meals],
        grocery_items=plan.grocery_items,
        constraints=constraints,
    )
    plan_ok = (
        len(plan.meals) == 3
        and check.ok
        and all(len(text_violations(m.name, banned)) == 0 for m in plan.meals)
    )
    checks.append(
        {
            "id": "unit.diet.planner_respects_constraints",
            "result": "PASS" if plan_ok else "FAIL",
            "detail": (
                f"meals={[m.name for m in plan.meals]} violations={check.violations}"
            ),
        }
    )

    # Late-night calendar event → quick dinner preference.
    late_start = datetime(2026, 1, 6, 19, 0, 0, tzinfo=tz)
    calendar.create(
        title="Evening meeting",
        start=late_start,
        end=late_start + timedelta(hours=2, minutes=30),
        timezone="Europe/Madrid",
    )
    late_night, busy_day, notes = schedule_hints(
        calendar, parsed.plan_date, "Europe/Madrid"
    )
    late_plan = build_meal_plan(
        plan_date=parsed.plan_date,
        timezone="Europe/Madrid",
        constraints=constraints,
        calendar=calendar,
    )
    dinner = next(m for m in late_plan.meals if m.slot == "dinner")
    schedule_ok = late_night and dinner.quick and len(notes) >= 1
    checks.append(
        {
            "id": "unit.diet.schedule_late_night_quick_dinner",
            "result": "PASS" if schedule_ok else "FAIL",
            "detail": (
                f"late_night={late_night} dinner={dinner.name!r} quick={dinner.quick} "
                f"notes={notes}"
            ),
        }
    )

    return checks


def _run_diet_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Diet service plans + grocery todos; Virtual User NL path; E2E-05 structure."""
    checks: list[dict[str, Any]] = []
    owner = "+15550001111"
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    calendar = CalendarStore()
    todo_store = TodoStore()
    mem_root = root / "artifacts" / "test" / ".integration-diet-mem"
    memory = MemoryStore.seed_from_fixture(
        mem_root, root / "fixtures" / "memory" / "seed-profile.json"
    )
    gw = ActionGateway(clock=clock, todos=todo_store)
    gw.calendar.attach_store(calendar)
    svc = DietService(
        calendar=calendar,
        todo_store=todo_store,
        clock=clock,
        catcher=catcher,
        memory=memory,
        gateway=gw,
        timezone="Europe/Madrid",
        recipient=owner,
    )

    planned = svc.plan_from_utterance(EXPECTED_E2E05_UTTERANCE)
    constraints = memory.planning_constraints()
    banned = banned_terms(constraints)
    violations: list[str] = []
    if planned.plan:
        for meal in planned.plan.meals:
            blob = " ".join([meal.name, *meal.ingredients])
            violations.extend(text_violations(blob, banned))
    service_ok = (
        planned.ok
        and planned.constraint_ok
        and planned.plan is not None
        and len(planned.plan.meals) == 3
        and len(violations) == 0
        and len(planned.grocery_todos) >= 1
        and catcher.count() == 1
        and catcher.messages[0].meta.get("kind") == "diet_plan"
        and tier_for("diet_draft") == ApprovalTier.AUTO
    )
    checks.append(
        {
            "id": "integration.diet.plan_and_grocery_todos",
            "result": "PASS" if service_ok else "FAIL",
            "detail": (
                f"ok={planned.ok} meals={len(planned.plan.meals) if planned.plan else 0} "
                f"grocery_todos={len(planned.grocery_todos)} violations={violations} "
                f"reason={planned.reason}"
            ),
        }
    )

    grocery_open = [
        t for t in todo_store.list_open() if "grocery" in t.tags or t.title.startswith("Buy ")
    ]
    grocery_ok = len(grocery_open) >= len(planned.plan.grocery_items) if planned.plan else False
    checks.append(
        {
            "id": "integration.diet.grocery_todos_tagged",
            "result": "PASS" if grocery_ok else "FAIL",
            "detail": f"open_grocery={len(grocery_open)}",
        }
    )

    vu = VirtualUser.bootstrap(root=root)
    turn = vu.inject_text(EXPECTED_E2E05_UTTERANCE)
    vu_plan = vu.last_plan_meals
    vu_ok = (
        turn.allowed
        and "diet_draft" in turn.tool_calls
        and vu_plan is not None
        and vu_plan.ok
        and vu_plan.plan is not None
        and len(vu.grocery_todos()) >= 1
    )
    checks.append(
        {
            "id": "integration.diet.virtual_user_nl_path",
            "result": "PASS" if vu_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} grocery={len(vu.grocery_todos())} "
                f"reason={getattr(vu_plan, 'reason', None)}"
            ),
        }
    )

    structure = run_e2e_05_structure(
        root=root,
        artifacts_dir=root / "artifacts" / "test" / "e2e-05-structure",
        write_artifacts=True,
    )
    checks.append(
        {
            "id": "integration.diet.e2e05_structure",
            "result": "PASS" if structure.ok else "FAIL",
            "detail": (
                f"result={structure.result} grocery={structure.grocery_todo_count} "
                f"eval={structure.eval_score}"
            ),
        }
    )

    return checks


def _run_booking_unit_checks(root: Path) -> list[dict[str, Any]]:
    """Stub portal slots, NL parse, hard-approve tier."""
    checks: list[dict[str, Any]] = []
    tz = ZoneInfo("Europe/Madrid")
    monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)

    parse_ok = looks_like_booking(EXPECTED_E2E06_UTTERANCE)
    parsed = parse_booking(EXPECTED_E2E06_UTTERANCE, now=monday, timezone="Europe/Madrid")
    parse_detail_ok = (
        parse_ok
        and parsed.service == "haircut"
        and parsed.period == "afternoon"
        and parsed.window_start.isoformat().startswith("2026-01-12")
    )
    checks.append(
        {
            "id": "unit.booking.parse_e2e06_utterance",
            "result": "PASS" if parse_detail_ok else "FAIL",
            "detail": (
                f"service={parsed.service} period={parsed.period} "
                f"window_start={parsed.window_start.isoformat()}"
            ),
        }
    )

    portal = StubBooksyPortal.from_fixture(
        root / "fixtures" / "browser" / "booksy-stub-slots.json"
    )
    slots = portal.list_slots(
        window_start=parsed.window_start,
        window_end=parsed.window_end,
        period=parsed.period,
        limit=3,
    )
    portal_ok = (
        portal.shop == "Main St Barber"
        and 2 <= len(slots) <= 3
        and all(s.period == "afternoon" for s in slots)
        and portal.list_count == 1
    )
    checks.append(
        {
            "id": "unit.booking.stub_portal_slots",
            "result": "PASS" if portal_ok else "FAIL",
            "detail": f"shop={portal.shop} slots={len(slots)} list_count={portal.list_count}",
        }
    )

    tier_ok = tier_for("book") == ApprovalTier.HARD_APPROVE
    checks.append(
        {
            "id": "unit.booking.hard_approve_tier",
            "result": "PASS" if tier_ok else "FAIL",
            "detail": f"tier={tier_for('book').value}",
        }
    )

    intent_ok = looks_like_booking("Book a haircut next week afternoon.") and not looks_like_booking(
        "Schedule focus block Friday 09:00–11:00."
    )
    checks.append(
        {
            "id": "unit.booking.intent_detection",
            "result": "PASS" if intent_ok else "FAIL",
            "detail": f"book={looks_like_booking(EXPECTED_E2E06_UTTERANCE)}",
        }
    )

    return checks


def _run_booking_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Propose → book_count=0; Accept → book+calendar+WhatsApp; Deny stays 0."""
    checks: list[dict[str, Any]] = []
    owner = "+15550001111"
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    cal = CalendarStore()
    gw = ActionGateway(clock=clock)
    svc = BookingService(
        clock=clock,
        catcher=catcher,
        gateway=gw,
        calendar_store=cal,
        timezone="Europe/Madrid",
        recipient=owner,
        portal_fixture=root / "fixtures" / "browser" / "booksy-stub-slots.json",
    )

    proposed = svc.propose_from_utterance(EXPECTED_E2E06_UTTERANCE)
    pending = gw.approvals.list(status=ApprovalStatus.PENDING)
    propose_ok = (
        proposed.ok
        and proposed.approval_id is not None
        and proposed.tier == ApprovalTier.HARD_APPROVE.value
        and not proposed.executed
        and gw.commerce.book_count == 0
        and 2 <= len(proposed.options) <= 3
        and len(pending) == 1
        and catcher.count() >= 1
        and catcher.messages[0].meta.get("kind") == "booking_propose"
        and proposed.task_id is not None
    )
    checks.append(
        {
            "id": "integration.booking.nl_propose_hard_approve",
            "result": "PASS" if propose_ok else "FAIL",
            "detail": (
                f"ok={proposed.ok} approval={proposed.approval_id} "
                f"book={gw.commerce.book_count} options={len(proposed.options)} "
                f"reason={proposed.reason}"
            ),
        }
    )

    inbox = AndroidApprovalInboxApi(gw)
    create_before = gw.calendar.create_count
    accepted = inbox.accept(proposed.approval_id) if proposed.approval_id else None
    confirms = [m for m in catcher.messages if m.meta.get("kind") == "booking_confirm"]
    task = svc.store.get(proposed.task_id) if proposed.task_id else None
    accept_ok = (
        accepted is not None
        and accepted.ok
        and gw.commerce.book_count == 1
        and gw.calendar.create_count == create_before + 1
        and len(confirms) == 1
        and task is not None
        and task.is_success
        and task.status == BookingStatus.BOOKED
        and len(cal.list_all()) == 1
    )
    checks.append(
        {
            "id": "integration.booking.accept_books_once_writeback",
            "result": "PASS" if accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(accepted, 'ok', None)} book={gw.commerce.book_count} "
                f"calendar={gw.calendar.create_count} confirms={len(confirms)} "
                f"task={task.status.value if task else None}"
            ),
        }
    )

    # Deny path.
    clock2 = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher2 = OutboundMessageCatcher()
    cal2 = CalendarStore()
    gw2 = ActionGateway(clock=clock2)
    svc2 = BookingService(
        clock=clock2,
        catcher=catcher2,
        gateway=gw2,
        calendar_store=cal2,
        timezone="Europe/Madrid",
        recipient=owner,
        portal_fixture=root / "fixtures" / "browser" / "booksy-stub-slots.json",
    )
    denied_prop = svc2.propose_from_utterance(EXPECTED_E2E06_UTTERANCE)
    inbox2 = AndroidApprovalInboxApi(gw2)
    # Android Deny alone must sync booking task → denied (no manual store glue).
    denied = inbox2.deny(denied_prop.approval_id) if denied_prop.approval_id else None
    late = gw2.execute(denied_prop.approval_id) if denied_prop.approval_id else None
    deny_task = svc2.store.get(denied_prop.task_id) if denied_prop.task_id else None
    deny_ok = (
        denied_prop.ok
        and denied is not None
        and denied.status == ApprovalStatus.DENIED.value
        and gw2.commerce.book_count == 0
        and gw2.calendar.create_count == 0
        and late is not None
        and (not late.ok)
        and deny_task is not None
        and deny_task.status == BookingStatus.DENIED
        and not deny_task.is_success
    )
    checks.append(
        {
            "id": "integration.booking.deny_books_nothing",
            "result": "PASS" if deny_ok else "FAIL",
            "detail": (
                f"deny={denied.status if denied else None} book={gw2.commerce.book_count} "
                f"late={getattr(late, 'reason', None)} "
                f"task={deny_task.status.value if deny_task else None}"
            ),
        }
    )

    # Failed booking cannot mark success (INV-BOOK-002 integration mirror).
    clock3 = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher3 = OutboundMessageCatcher()
    gw3 = ActionGateway(clock=clock3)
    gw3.commerce.fail_next_book = True
    svc3 = BookingService(
        clock=clock3,
        catcher=catcher3,
        gateway=gw3,
        timezone="Europe/Madrid",
        recipient=owner,
        portal_fixture=root / "fixtures" / "browser" / "booksy-stub-slots.json",
    )
    fail_prop = svc3.propose_from_utterance(EXPECTED_E2E06_UTTERANCE)
    fail_accept = (
        AndroidApprovalInboxApi(gw3).accept(fail_prop.approval_id)
        if fail_prop.approval_id
        else None
    )
    fail_task = svc3.store.get(fail_prop.task_id) if fail_prop.task_id else None
    fail_confirms = [
        m for m in catcher3.messages if m.meta.get("kind") == "booking_confirm"
    ]
    fail_ok = (
        fail_prop.ok
        and fail_accept is not None
        and (not fail_accept.ok)
        and gw3.commerce.book_count == 0
        and gw3.calendar.create_count == 0
        and len(fail_confirms) == 0
        and fail_task is not None
        and fail_task.status == BookingStatus.FAILED
        and not fail_task.is_success
    )
    checks.append(
        {
            "id": "integration.booking.failed_not_success",
            "result": "PASS" if fail_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(fail_accept, 'ok', None)} "
                f"book={gw3.commerce.book_count} calendar={gw3.calendar.create_count} "
                f"task={fail_task.status.value if fail_task else None}"
            ),
        }
    )

    # Virtual User WhatsApp NL → pending hard approve (E2E-06 readiness).
    vu = VirtualUser.bootstrap(root=root)
    turn = vu.inject_text(EXPECTED_E2E06_UTTERANCE)
    vu_ok = (
        turn.allowed
        and "book_propose" in turn.tool_calls
        and vu.book_count() == 0
        and len(vu.pending_approvals()) == 1
        and vu.last_booking_propose is not None
        and vu.last_booking_propose.ok
        and 2 <= len(vu.last_booking_propose.options) <= 3
    )
    checks.append(
        {
            "id": "integration.booking.virtual_user_nl_path",
            "result": "PASS" if vu_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} book={vu.book_count()} "
                f"pending={len(vu.pending_approvals())} "
                f"options={len(vu.last_booking_propose.options) if vu.last_booking_propose else 0}"
            ),
        }
    )

    appr_id = vu.last_booking_propose.approval_id if vu.last_booking_propose else None
    vu_accept = vu.accept_approval(appr_id) if appr_id else None
    vu_confirms = [
        m for m in vu.catcher.messages if m.meta.get("kind") == "booking_confirm"
    ]
    vu_accept_ok = (
        vu_accept is not None
        and vu_accept.ok
        and vu.book_count() == 1
        and vu.calendar_create_count() == 1
        and len(vu_confirms) == 1
    )
    checks.append(
        {
            "id": "integration.booking.virtual_user_accept",
            "result": "PASS" if vu_accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(vu_accept, 'ok', None)} book={vu.book_count()} "
                f"calendar={vu.calendar_create_count()} confirms={len(vu_confirms)}"
            ),
        }
    )

    # E2E-09 readiness: ignored hard approval expires → execute still 0.
    vu_exp = VirtualUser.bootstrap(root=root)
    exp_prop = vu_exp.book_from_utterance(EXPECTED_E2E06_UTTERANCE)
    book_before_exp = vu_exp.book_count()
    late_accept_ok = None
    late_exec = None
    expired_item = None
    item = None
    if exp_prop.approval_id:
        item = vu_exp.gateway.approvals.get(exp_prop.approval_id)
        # Advance past hard default expiry (4h).
        vu_exp.advance(timedelta(hours=5))
        vu_exp.gateway.approvals.expire_due()
        expired_item = vu_exp.gateway.approvals.get(exp_prop.approval_id)
        try:
            late_accept = vu_exp.accept_approval(exp_prop.approval_id)
            late_accept_ok = late_accept.ok
        except ApprovalError:
            late_accept_ok = False
        late_exec = vu_exp.gateway.execute(exp_prop.approval_id)
    exp_ok = (
        exp_prop.ok
        and book_before_exp == 0
        and vu_exp.book_count() == 0
        and expired_item is not None
        and expired_item.status == ApprovalStatus.EXPIRED
        and late_accept_ok is False
        and late_exec is not None
        and (not late_exec.ok)
    )
    checks.append(
        {
            "id": "integration.booking.expiry_e2e09_ready",
            "result": "PASS" if exp_ok else "FAIL",
            "detail": (
                f"status={expired_item.status.value if expired_item else None} "
                f"book={vu_exp.book_count()} "
                f"late_accept_ok={late_accept_ok} "
                f"late_exec={getattr(late_exec, 'reason', None)} "
                f"was_pending={item.status.value if item else None}"
            ),
        }
    )

    return checks


def _run_shopping_unit_checks(root: Path) -> list[dict[str, Any]]:
    """Spend-cap math, NL parse, dry-run merchant catalog, hard-approve tier."""
    checks: list[dict[str, Any]] = []

    parse_ok = looks_like_shopping(EXPECTED_E2E07_UTTERANCE)
    parsed = parse_shopping(EXPECTED_E2E07_UTTERANCE)
    parse_detail_ok = (
        parse_ok
        and parsed.item_key == "protein_powder"
        and parsed.prefer_usual
        and not looks_like_shopping("Add todo: buy oat milk")
        and not looks_like_shopping("Remind me to buy milk")
    )
    checks.append(
        {
            "id": "unit.shopping.parse_e2e07_utterance",
            "result": "PASS" if parse_detail_ok else "FAIL",
            "detail": (
                f"item_key={parsed.item_key} prefer_usual={parsed.prefer_usual} "
                f"looks={parse_ok}"
            ),
        }
    )

    merchant = DryRunMerchant.from_fixture(
        root / "fixtures" / "shopping" / "merchant-catalog.json"
    )
    hits = merchant.search(
        query="protein powder", item_key="protein_powder", prefer_usual=True, limit=3
    )
    usual = merchant.find_usual("protein_powder")
    merchant_ok = (
        merchant.merchant == "StubMart"
        and usual is not None
        and usual.sku == "prot-whey-2kg"
        and usual.price == 29.99
        and len(hits) >= 1
        and hits[0].sku == "prot-whey-2kg"
        and merchant.search_count == 1
    )
    checks.append(
        {
            "id": "unit.shopping.dry_run_merchant_catalog",
            "result": "PASS" if merchant_ok else "FAIL",
            "detail": (
                f"merchant={merchant.merchant} usual_sku={usual.sku if usual else None} "
                f"price={usual.price if usual else None} hits={len(hits)}"
            ),
        }
    )

    caps = SpendCapConfig.from_file(root / "config" / "shopping.harness.json")
    ledger = SpendLedger(config=caps)
    tz = ZoneInfo("Europe/Madrid")
    now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=tz)
    under = ledger.check(29.99, now=now)
    over = ledger.check(60.0, now=now)
    ledger.record(40.0, now=now)
    second = ledger.check(20.0, now=now)
    cap_math_ok = (
        caps.daily_limit == 50.0
        and caps.weekly_limit == 150.0
        and under.ok
        and (not over.ok)
        and over.reason == "spend_cap_daily"
        and (not second.ok)
        and second.reason == "spend_cap_daily"
    )
    checks.append(
        {
            "id": "unit.shopping.spend_cap_math",
            "result": "PASS" if cap_math_ok else "FAIL",
            "detail": (
                f"daily={caps.daily_limit} under={under.ok} over={over.reason} "
                f"second={second.reason}"
            ),
        }
    )

    tier_ok = tier_for("buy") == ApprovalTier.HARD_APPROVE
    checks.append(
        {
            "id": "unit.shopping.hard_approve_tier",
            "result": "PASS" if tier_ok else "FAIL",
            "detail": f"tier={tier_for('buy').value}",
        }
    )

    intent_ok = looks_like_shopping("Buy my usual protein powder.") and not looks_like_booking(
        "Buy my usual protein powder."
    )
    checks.append(
        {
            "id": "unit.shopping.intent_detection",
            "result": "PASS" if intent_ok else "FAIL",
            "detail": f"shop={looks_like_shopping(EXPECTED_E2E07_UTTERANCE)}",
        }
    )

    return checks


def _run_shopping_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Propose buy_count=0; Accept under cap → dry-run; freeze/cap block."""
    checks: list[dict[str, Any]] = []
    owner = "+15550001111"
    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    gw = ActionGateway(clock=clock)
    svc = ShoppingService(
        clock=clock,
        catcher=catcher,
        gateway=gw,
        recipient=owner,
        merchant_fixture=root / "fixtures" / "shopping" / "merchant-catalog.json",
        caps_config=root / "config" / "shopping.harness.json",
    )

    proposed = svc.propose_from_utterance(EXPECTED_E2E07_UTTERANCE)
    pending = gw.approvals.list(status=ApprovalStatus.PENDING)
    propose_ok = (
        proposed.ok
        and proposed.approval_id is not None
        and proposed.tier == ApprovalTier.HARD_APPROVE.value
        and not proposed.executed
        and gw.commerce.buy_count == 0
        and proposed.price == 29.99
        and len(pending) == 1
        and catcher.count() >= 1
        and catcher.messages[0].meta.get("kind") == "shopping_propose"
        and proposed.task_id is not None
    )
    checks.append(
        {
            "id": "integration.shopping.nl_propose_hard_approve",
            "result": "PASS" if propose_ok else "FAIL",
            "detail": (
                f"ok={proposed.ok} approval={proposed.approval_id} "
                f"buy={gw.commerce.buy_count} price={proposed.price} "
                f"reason={proposed.reason}"
            ),
        }
    )

    inbox = AndroidApprovalInboxApi(gw)
    accepted = inbox.accept(proposed.approval_id) if proposed.approval_id else None
    receipts = [m for m in catcher.messages if m.meta.get("kind") == "shopping_receipt"]
    task = svc.store.get(proposed.task_id) if proposed.task_id else None
    audits = (
        gw.audit.for_approval(proposed.approval_id) if proposed.approval_id else []
    )
    accept_ok = (
        accepted is not None
        and accepted.ok
        and gw.commerce.buy_count == 1
        and len(receipts) == 1
        and task is not None
        and task.is_success
        and task.status == PurchaseStatus.PURCHASED
        and isinstance(accepted.execute.result if accepted.execute else None, dict)
        and (accepted.execute.result or {}).get("dry_run") is True
        and any(a.success and a.approval_id == proposed.approval_id for a in audits)
        and len(gw.spend.entries) == 1
    )
    checks.append(
        {
            "id": "integration.shopping.accept_dry_run_receipt",
            "result": "PASS" if accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(accepted, 'ok', None)} buy={gw.commerce.buy_count} "
                f"receipts={len(receipts)} task={task.status.value if task else None} "
                f"audits={len(audits)}"
            ),
        }
    )

    # Freeze blocks even with stale accepted approval (INV-PAY-001 mirror).
    clock_f = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher_f = OutboundMessageCatcher()
    gw_f = ActionGateway(clock=clock_f)
    svc_f = ShoppingService(
        clock=clock_f,
        catcher=catcher_f,
        gateway=gw_f,
        recipient=owner,
        merchant_fixture=root / "fixtures" / "shopping" / "merchant-catalog.json",
        caps_config=root / "config" / "shopping.harness.json",
    )
    prop_f = svc_f.propose_from_utterance(EXPECTED_E2E07_UTTERANCE)
    assert prop_f.approval_id
    gw_f.accept(prop_f.approval_id)
    gw_f.freeze_spending()
    blocked_f = gw_f.execute(prop_f.approval_id)
    freeze_ok = (
        (not blocked_f.ok)
        and blocked_f.reason == "freeze_spending"
        and gw_f.commerce.buy_count == 0
        and any(r.get("reason") == "freeze_spending" for r in gw_f.execute_rejections)
        and gw_f.approvals.get(prop_f.approval_id) is not None
        and gw_f.approvals.get(prop_f.approval_id).status == ApprovalStatus.ACCEPTED  # type: ignore[union-attr]
    )
    checks.append(
        {
            "id": "integration.shopping.freeze_blocks_stale_approval",
            "result": "PASS" if freeze_ok else "FAIL",
            "detail": (
                f"reason={blocked_f.reason} buy={gw_f.commerce.buy_count} "
                f"rejections={len(gw_f.execute_rejections)}"
            ),
        }
    )

    # Over cap → blocked with cap reason (INV-PAY-002 mirror).
    clock_c = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher_c = OutboundMessageCatcher()
    gw_c = ActionGateway(clock=clock_c)
    svc_c = ShoppingService(
        clock=clock_c,
        catcher=catcher_c,
        gateway=gw_c,
        recipient=owner,
        merchant_fixture=root / "fixtures" / "shopping" / "merchant-catalog.json",
        spend_caps=SpendCapConfig(daily_limit=10.0, weekly_limit=150.0),
    )
    prop_c = svc_c.propose_from_utterance(EXPECTED_E2E07_UTTERANCE)
    accept_c = (
        AndroidApprovalInboxApi(gw_c).accept(prop_c.approval_id)
        if prop_c.approval_id
        else None
    )
    cap_ok = (
        prop_c.ok
        and accept_c is not None
        and (not accept_c.ok)
        and accept_c.execute is not None
        and accept_c.execute.reason == "spend_cap_daily"
        and gw_c.commerce.buy_count == 0
        and any(r.get("reason") == "spend_cap_daily" for r in gw_c.execute_rejections)
    )
    checks.append(
        {
            "id": "integration.shopping.cap_breach_blocks",
            "result": "PASS" if cap_ok else "FAIL",
            "detail": (
                f"reason={getattr(getattr(accept_c, 'execute', None), 'reason', None)} "
                f"buy={gw_c.commerce.buy_count}"
            ),
        }
    )

    # Deny path.
    clock_d = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher_d = OutboundMessageCatcher()
    gw_d = ActionGateway(clock=clock_d)
    svc_d = ShoppingService(
        clock=clock_d,
        catcher=catcher_d,
        gateway=gw_d,
        recipient=owner,
        merchant_fixture=root / "fixtures" / "shopping" / "merchant-catalog.json",
        caps_config=root / "config" / "shopping.harness.json",
    )
    prop_d = svc_d.propose_from_utterance(EXPECTED_E2E07_UTTERANCE)
    deny = (
        AndroidApprovalInboxApi(gw_d).deny(prop_d.approval_id)
        if prop_d.approval_id
        else None
    )
    late = gw_d.execute(prop_d.approval_id) if prop_d.approval_id else None
    deny_task = svc_d.store.get(prop_d.task_id) if prop_d.task_id else None
    deny_ok = (
        prop_d.ok
        and deny is not None
        and deny.status == ApprovalStatus.DENIED.value
        and gw_d.commerce.buy_count == 0
        and late is not None
        and (not late.ok)
        and deny_task is not None
        and deny_task.status == PurchaseStatus.DENIED
    )
    checks.append(
        {
            "id": "integration.shopping.deny_buys_nothing",
            "result": "PASS" if deny_ok else "FAIL",
            "detail": (
                f"deny={deny.status if deny else None} buy={gw_d.commerce.buy_count} "
                f"task={deny_task.status.value if deny_task else None}"
            ),
        }
    )

    # Virtual User NL path.
    vu = VirtualUser.bootstrap(root=root)
    turn = vu.inject_text(EXPECTED_E2E07_UTTERANCE)
    vu_ok = (
        turn.allowed
        and "buy_propose" in turn.tool_calls
        and vu.last_shopping_propose is not None
        and vu.last_shopping_propose.ok
        and vu.buy_count() == 0
        and vu.last_shopping_propose.price == 29.99
    )
    checks.append(
        {
            "id": "integration.shopping.virtual_user_nl_path",
            "result": "PASS" if vu_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} buy={vu.buy_count()} "
                f"price={getattr(vu.last_shopping_propose, 'price', None)}"
            ),
        }
    )

    # Virtual User Accept under cap → dry-run.
    vu2 = VirtualUser.bootstrap(root=root)
    prop_vu = vu2.buy_from_utterance(EXPECTED_E2E07_UTTERANCE)
    accept_vu = (
        vu2.android_inbox.accept(prop_vu.approval_id) if prop_vu.approval_id else None
    )
    vu_accept_ok = (
        prop_vu.ok
        and accept_vu is not None
        and accept_vu.ok
        and vu2.buy_count() == 1
        and any(m.meta.get("kind") == "shopping_receipt" for m in vu2.catcher.messages)
    )
    checks.append(
        {
            "id": "integration.shopping.virtual_user_accept_e2e07_ready",
            "result": "PASS" if vu_accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(accept_vu, 'ok', None)} buy={vu2.buy_count()} "
                f"e2e07_ready=true"
            ),
        }
    )

    return checks


def _run_android_approval_unit_checks() -> list[dict[str, Any]]:
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


def _run_android_approval_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Virtual User alone Accept/Deny via Android API; soft-confirm calendar hooks."""
    checks: list[dict[str, Any]] = []

    t2 = run_t2_approval_inbox(
        root=root,
        artifacts_dir=root / "artifacts" / "test" / "task-11",
        write_artifacts=False,
    )
    for check in t2.checks:
        checks.append(
            {
                "id": f"integration.android_approval.{check['id'].removeprefix('t2.')}",
                "result": check["result"],
                "detail": check.get("detail", ""),
                "gate": check.get("gate", True),
            }
        )

    # Explicit E2E-04 hook: pending soft confirm leaves adapter create at 0.
    vu = VirtualUser.bootstrap(root=root)
    prop = vu.propose_soft_calendar(
        title="Focus block",
        start="2026-01-09T09:00:00+01:00",
        end="2026-01-09T11:00:00+01:00",
        source_utterance="Schedule focus block Friday 09:00–11:00.",
    )
    hook_ok = (
        prop.ok
        and prop.approval_id is not None
        and vu.calendar_create_count() == 0
        and len(vu.list_android_approvals()) == 1
        and vu.android_inbox.get(prop.approval_id) is not None
    )
    checks.append(
        {
            "id": "integration.android_approval.e2e04_soft_confirm_hook",
            "result": "PASS" if hook_ok else "FAIL",
            "detail": (
                f"approval_id={prop.approval_id} create={vu.calendar_create_count()} "
                f"pending={len(vu.list_android_approvals())}"
            ),
        }
    )

    return checks


def _run_todo_integration_checks(root: Path) -> list[dict[str, Any]]:
    """WhatsApp todo create → Android projection equality; complete sync; dedup."""
    checks: list[dict[str, Any]] = []
    owner = "+15550001111"
    clock = FakeClock()
    catcher = OutboundMessageCatcher()
    store = TodoStore()
    gw = ActionGateway(clock=clock, todos=store)
    svc = TodoService(store=store, clock=clock, catcher=catcher, gateway=gw, recipient=owner)
    android = AndroidProjectionApi(store=store, clock=clock, gateway=gw)

    created = svc.create_from_utterance("Add todo: buy oat milk.", recipient=owner)
    pending = gw.approvals.list(status=ApprovalStatus.PENDING)
    create_ok = (
        created.ok
        and created.todo is not None
        and created.todo.title.lower() == "buy oat milk"
        and created.todo.status == TodoStatus.OPEN
        and created.tier == "auto"
        and created.approval_id is None
        and len(pending) == 0
        and catcher.count() == 1
        and catcher.messages[0].meta.get("kind") == "todo_confirm"
    )
    checks.append(
        {
            "id": "integration.todo.whatsapp_create_auto",
            "result": "PASS" if create_ok else "FAIL",
            "detail": (
                f"ok={created.ok} title={created.todo.title if created.todo else None!r} "
                f"tier={created.tier} outbound={catcher.count()}"
            ),
        }
    )

    assert created.todo is not None
    projected = android.list_todos()
    proj = projected[0] if projected else None
    sync_ok = (
        proj is not None
        and proj.id == created.todo.id
        and proj.title == created.todo.title
        and proj.status == "open"
        and android.get_todo(created.todo.id) == proj
    )
    checks.append(
        {
            "id": "integration.todo.android_projection_equality",
            "result": "PASS" if sync_ok else "FAIL",
            "detail": (
                f"agent_id={created.todo.id} android_id={proj.id if proj else None} "
                f"title={proj.title if proj else None!r} status={proj.status if proj else None}"
            ),
        }
    )

    completed = android.complete_todo(created.todo.id)
    store_after = store.get(created.todo.id)
    complete_ok = (
        completed.status == "done"
        and store_after is not None
        and store_after.status == TodoStatus.DONE
        and len(android.list_todos(status="open")) == 0
    )
    checks.append(
        {
            "id": "integration.todo.android_complete_reflects_store",
            "result": "PASS" if complete_ok else "FAIL",
            "detail": (
                f"proj={completed.status} store={store_after.status.value if store_after else None}"
            ),
        }
    )

    # Dedup: second add with same title returns existing open todo (no duplicate row).
    catcher2 = OutboundMessageCatcher()
    store3 = TodoStore()
    gw3 = ActionGateway(clock=clock, todos=store3)
    svc3 = TodoService(store=store3, clock=clock, catcher=catcher2, gateway=gw3, recipient=owner)
    first = svc3.create_from_utterance("Add todo: buy oat milk.", recipient=owner)
    second = svc3.create_from_utterance("Add todo: Buy oat milk.", recipient=owner)
    dedup_ok = (
        first.ok
        and second.ok
        and second.deduplicated
        and first.todo is not None
        and second.todo is not None
        and first.todo.id == second.todo.id
        and len(store3.list_open()) == 1
        and any(m.meta.get("kind") == "todo_dedup" for m in catcher2.messages)
    )
    checks.append(
        {
            "id": "integration.todo.dedup_whatsapp_readd",
            "result": "PASS" if dedup_ok else "FAIL",
            "detail": (
                f"first={first.todo.id if first.todo else None} "
                f"second_dedup={second.deduplicated} open={len(store3.list_open())}"
            ),
        }
    )

    # E2E-03 prep via Virtual User harness (full journey).
    e2e03 = run_e2e_03(
        root=root,
        artifacts_dir=root / "artifacts" / "test" / "e2e-03",
        write_artifacts=True,
    )
    checks.append(
        {
            "id": "integration.todo.e2e03_virtual_user_journey",
            "result": e2e03.result,
            "detail": (
                f"todo_id={e2e03.todo_id} title={e2e03.title!r} status={e2e03.status} "
                f"checks={len(e2e03.checks)}"
            ),
        }
    )

    return checks


def _run_transcription_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Voice note → STT stub → transcript turn OR clarification via mock WhatsApp."""
    checks: list[dict[str, Any]] = []
    owner = "+15550001111"
    pipeline = TranscriptionPipeline.from_fixtures(
        manifest_path=root / "fixtures" / "audio" / "manifest.json"
    )
    catcher = OutboundMessageCatcher()
    transport = MockWhatsAppTransport(
        allowlist=[owner],
        catcher=catcher,
        pipeline=pipeline,
        tts_mode=TtsMode.INBOUND,
    )

    # Happy path: E2E-01 audio fixture → transcript turn + TTS spy speak.
    voice = transport.inject_audio(owner, audio_fixture_id="fx-reminder")
    voice_ok = (
        voice.allowed
        and voice.transcript == "Remind me Sunday at 18:00 to call grandma."
        and (voice.turn_body or "").startswith("[Audio] Remind me Sunday")
        and voice.clarification is None
        and "agent.respond" in voice.tool_calls
        and voice.tts_spoken is True
        and transport.counters.stt_calls == 1
        and transport.counters.transcript_turns == 1
        and transport.counters.clarification_asks == 0
        and catcher.count() == 1
    )
    checks.append(
        {
            "id": "integration.transcription.voice_to_transcript_turn",
            "result": "PASS" if voice_ok else "FAIL",
            "detail": (
                f"transcript={voice.transcript!r} turn={voice.turn_body!r} "
                f"tts={voice.tts_spoken} tools={voice.tool_calls} "
                f"counters={transport.counters.snapshot()}"
            ),
        }
    )

    # Text inbound must not trigger TTS under inbound mode.
    transport.reset_effects()
    text = transport.inject_text(owner, "hello text")
    # default handler does not call TTS for text; policy spy stays at 0
    text_tts_ok = (
        text.allowed
        and transport.pipeline.tts.speak_count == 0
        and transport.counters.tts_speaks == 0
        and transport.counters.stt_calls == 0
    )
    checks.append(
        {
            "id": "integration.transcription.tts_inbound_mode_text_skip",
            "result": "PASS" if text_tts_ok else "FAIL",
            "detail": f"tts_calls={transport.pipeline.tts.snapshot()}",
        }
    )

    # Empty / garbage / unknown → clarification; zero hard tools.
    transport.reset_effects()
    for fid in ("fx-empty", "fx-garbage", "fx-unknown-xyz"):
        res = transport.inject_audio(owner, audio_fixture_id=fid)
        if not res.clarification or "agent.clarify" not in res.tool_calls:
            checks.append(
                {
                    "id": "integration.transcription.clarify_on_bad_audio",
                    "result": "FAIL",
                    "detail": f"fixture={fid} result={res}",
                }
            )
            break
    else:
        hard = [t for t in transport.tool_call_log if t in (
            "buy", "book", "self_mod_apply", "policy_change", "transfer_money"
        )]
        clarify_ok = (
            transport.counters.clarification_asks >= 3
            and transport.counters.transcript_turns == 0
            and not hard
        )
        checks.append(
            {
                "id": "integration.transcription.clarify_on_bad_audio",
                "result": "PASS" if clarify_ok else "FAIL",
                "detail": (
                    f"clarifies={transport.counters.clarification_asks} "
                    f"hard={hard} outbound={catcher.count()}"
                ),
            }
        )

    # Low-confidence buy → echo clarify; never silent buy.
    transport.reset_effects()
    risky = transport.inject_audio(owner, audio_fixture_id="fx-unclear-buy")
    risky_ok = (
        risky.clarification is not None
        and "buy" in (risky.clarification or "").lower()
        and "agent.clarify" in risky.tool_calls
        and "buy" not in transport.tool_call_log
        and risky.tts_spoken is False
    )
    checks.append(
        {
            "id": "integration.transcription.low_confidence_hard_action_clarify",
            "result": "PASS" if risky_ok else "FAIL",
            "detail": f"clarification={risky.clarification!r} tools={risky.tool_calls}",
        }
    )

    # IngressSimulator wiring: audio fixture id path.
    sim = IngressSimulator(
        allowlist=[owner],
        catcher=OutboundMessageCatcher(),
        pipeline=TranscriptionPipeline.from_fixtures(
            manifest_path=root / "fixtures" / "audio" / "manifest.json"
        ),
    )
    sim_res = sim.handle_audio(owner, audio_fixture_id="fx-todo")
    sim_ok = (
        sim_res.allowed
        and sim_res.transcript == "Add todo: buy oat milk"
        and (sim_res.turn_body or "").startswith("[Audio]")
        and sim.counters.stt_calls == 1
    )
    checks.append(
        {
            "id": "integration.transcription.ingress_sim_audio",
            "result": "PASS" if sim_ok else "FAIL",
            "detail": (
                f"transcript={sim_res.transcript!r} turn={sim_res.turn_body!r} "
                f"stt_calls={sim.counters.stt_calls}"
            ),
        }
    )

    return checks


def _run_memory_integration_checks(root: Path) -> list[dict[str, Any]]:
    """Memory profile R/W — explicit remember, hot load, episodic, restart durability."""
    checks: list[dict[str, Any]] = []
    fixture = root / "fixtures" / "memory" / "seed-profile.json"

    with tempfile.TemporaryDirectory(prefix="task04-mem-") as tmp:
        mem_root = Path(tmp) / "memory"
        store = MemoryStore.seed_from_fixture(mem_root, fixture)

        # Hot profile on turn includes identity facts.
        hot = store.load_hot_profile()
        ctx_lines = store.hot_context_lines()
        hot_ok = (
            hot.get("identity", {}).get("name") == "Alex"
            and "grandma" in hot.get("identity", {}).get("household", "").lower()
            and any("Allergies" in line for line in ctx_lines)
        )
        checks.append(
            {
                "id": "integration.memory.hot_profile_turn",
                "result": "PASS" if hot_ok else "FAIL",
                "detail": f"name={hot.get('identity', {}).get('name')} lines={ctx_lines}",
            }
        )

        # Diet constraints for planner input assembly.
        constraints = store.planning_constraints()
        diet_ok = (
            "peanuts" in constraints.get("allergies", [])
            and "shellfish" in constraints.get("food_dislikes", [])
            and constraints.get("diet_phase") == "low carb"
        )
        checks.append(
            {
                "id": "integration.memory.diet_constraints",
                "result": "PASS" if diet_ok else "FAIL",
                "detail": str(constraints),
            }
        )

        # Explicit remember persists across harness reboot (new store handle).
        store.remember("goals", "diet_phase", "low carb — no rice", explicit=True)
        store.append_episode("User asked to remember Sunday grandma call", tags=["ritual"])
        reopened = MemoryStore.open(mem_root)
        reboot_hot = reopened.load_hot_profile()
        episodes = reopened.read_episodes(limit=5)
        reboot_ok = (
            reboot_hot.get("goals", {}).get("diet_phase") == "low carb — no rice"
            and len(episodes) == 1
            and "grandma" in episodes[0].get("summary", "").lower()
        )
        checks.append(
            {
                "id": "integration.memory.remember_persists_restart",
                "result": "PASS" if reboot_ok else "FAIL",
                "detail": (
                    f"diet={reboot_hot.get('goals', {}).get('diet_phase')} "
                    f"episodes={len(episodes)}"
                ),
            }
        )

        # Secrets must not land in memory files.
        secret_blocked = False
        try:
            reopened.remember("preferences", "leak", "token: supersecret123")
        except MemorySecretsError:
            secret_blocked = True
        disk = (
            reopened.profile_path.read_text(encoding="utf-8")
            + reopened.episodes_path.read_text(encoding="utf-8")
        )
        secrets_ok = secret_blocked and "supersecret123" not in disk
        checks.append(
            {
                "id": "integration.memory.secrets_not_on_disk",
                "result": "PASS" if secrets_ok else "FAIL",
                "detail": f"secret_blocked={secret_blocked}",
            }
        )

    return checks


def _run_task05_hosting_checks(root: Path) -> list[dict[str, Any]]:
    """E2E-10 prep: durable approvals survive harness Gateway restart."""
    checks: list[dict[str, Any]] = []

    # Config templates loadable (harness JSON profile + backup manifest).
    profile = load_gateway_profile(root / "config" / "gateway.harness.json")
    paths = gateway_data_paths(profile)
    backup_manifest = root / "config" / "backup.example.json"
    config_ok = (
        profile.get("gateway", {}).get("mode") == "harness"
        and paths["approvals"].name == "items.json"
        and backup_manifest.exists()
    )
    checks.append(
        {
            "id": "integration.hosting.config_profile",
            "result": "PASS" if config_ok else "FAIL",
            "detail": (
                f"mode={profile.get('gateway', {}).get('mode')} "
                f"approvals={paths['approvals']} backup_manifest={backup_manifest.exists()}"
            ),
        }
    )

    with tempfile.TemporaryDirectory(prefix="task05-hosting-") as tmp:
        mem_root = Path(tmp)
        approvals_path = mem_root / "approvals" / "items.json"
        clock = FakeClock()

        # Phase 1: create pending purchase approval (E2E-10 step 1).
        gw1 = ActionGateway(clock=clock, approvals_path=approvals_path)
        prop = gw1.propose(
            "buy",
            "protein powder purchase",
            {"sku": "protein-powder", "price": 42.0},
            estimated_cost=42.0,
        )
        approval_id = prop.approval_id
        pending_before = gw1.approvals.list(status=ApprovalStatus.PENDING)
        disk_ok = approvals_path.exists()

        # Phase 2: simulate Gateway restart — new process, reopen store (E2E-10 step 2).
        gw2 = ActionGateway(clock=clock, approvals_path=approvals_path)
        reopened = gw2.approvals.get(approval_id or "")
        pending_after = gw2.approvals.list(status=ApprovalStatus.PENDING)

        restart_ok = (
            prop.ok
            and approval_id is not None
            and disk_ok
            and len(pending_before) == 1
            and reopened is not None
            and reopened.status == ApprovalStatus.PENDING
            and len(pending_after) == 1
            and pending_after[0].id == approval_id
        )
        checks.append(
            {
                "id": "integration.hosting.approval_survives_restart",
                "result": "PASS" if restart_ok else "FAIL",
                "detail": (
                    f"approval_id={approval_id} disk={disk_ok} "
                    f"pending_before={len(pending_before)} "
                    f"pending_after={len(pending_after)} "
                    f"status={reopened.status.value if reopened else None}"
                ),
            }
        )

        # Phase 3: Accept still works once; no duplicate execute (E2E-10 step 3).
        gw2.accept(approval_id or "")
        first = gw2.execute(approval_id or "")
        second = gw2.execute(approval_id or "")
        gw3 = ActionGateway(clock=clock, approvals_path=approvals_path)
        final_item = gw3.approvals.get(approval_id or "")

        accept_once_ok = (
            first.ok
            and gw2.commerce.buy_count == 1
            and (not second.ok)
            and final_item is not None
            and final_item.status == ApprovalStatus.EXECUTED
        )
        checks.append(
            {
                "id": "integration.hosting.accept_once_after_restart",
                "result": "PASS" if accept_once_ok else "FAIL",
                "detail": (
                    f"first={first.ok} second={second.ok} "
                    f"buy_count={gw2.commerce.buy_count} "
                    f"status={final_item.status.value if final_item else None}"
                ),
            }
        )

        # GatewayHarness wrapper restart path (same checks via harness API).
        harness_profile = {
            "gateway": {"name": "task05", "mode": "harness"},
            "data_root": str(mem_root),
            "paths": {"approvals": str(approvals_path)},
        }
        h1 = GatewayHarness(clock=clock, profile=harness_profile)
        h2 = h1.restart()
        harness_ok = h2.gateway.approvals.get(approval_id or "") is not None
        checks.append(
            {
                "id": "integration.hosting.gateway_harness_restart",
                "result": "PASS" if harness_ok else "FAIL",
                "detail": f"reopened_via_harness={harness_ok}",
            }
        )

    return checks


def aggregate(layers: list[dict[str, Any]], out_dir: Path, *, broken: bool) -> int:
    overall = "PASS" if all(L["result"] == "PASS" for L in layers) else "FAIL"
    flat_checks: list[dict[str, Any]] = []
    for layer in layers:
        for check in layer.get("checks", []):
            flat_checks.append(
                {
                    "id": f"{layer['layer']}:{check.get('id')}",
                    "result": check.get("result"),
                    "detail": check.get("detail", ""),
                }
            )

    write_report(
        out_dir,
        layer="test:ci",
        result=overall,
        checks=flat_checks,
        extra={
            "broken_allow_all": broken,
            "layers": [{"layer": L["layer"], "result": L["result"]} for L in layers],
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
                "artifacts": [
                    "artifacts/test/ci/",
                    "artifacts/test/e2e-01/",
                    "artifacts/test/e2e-02/",
                    "artifacts/test/e2e-03/",
                    "artifacts/test/e2e-04/",
                    "artifacts/test/e2e-05/",
                    "artifacts/test/e2e-06/",
                    "artifacts/test/e2e-07/",
                    "artifacts/test/e2e-09/",
                    "artifacts/test/task-03/",
                    "artifacts/test/task-04/",
                    "artifacts/test/task-05/",
                    "artifacts/test/task-06/",
                    "artifacts/test/task-07/",
                    "artifacts/test/task-09/",
                    "artifacts/test/task-10/",
                    "artifacts/test/task-11/",
                    "artifacts/test/task-13/",
                    "artifacts/test/task-15/",
                    "artifacts/test/task-16/",
                    "artifacts/test/task-17/",
                    "artifacts/test/task-19/",
                    "artifacts/test/task-20/",
                    "artifacts/test/task-21/",
                    "artifacts/test/task-22/",
                ],
            },
        },
    )

    # Compact stamp for autonomous verification loops.
    stamp = {
        "claim": (
            "WhatsApp ingress + memory R/W + transcription + reminders/habits + "
            "E2E-01 voice reminder + E2E-02 habit escalation ladder (T4) + "
            "E2E-03 todo sync + E2E-04 calendar soft confirm + E2E-05 diet → "
            "groceries gates + TASK-17 outbound voice calls (INV-APPR-005) + "
            "TASK-19 Booksy stub bookings (INV-BOOK-001/002) + "
            "E2E-06 propose→approve→book (+ deny) + E2E-09 expiry (T5) + "
            "TASK-21 shopping dry-run + spend caps/freeze (INV-PAY-001/002) + "
            "E2E-07 shopping cap/freeze (+ deny gate; T6): "
            "allowlisted DM; voice→transcript/clarify; Auto reminder/todo create; "
            "Android projection equality; calendar soft-confirm (INV-APPR-003); "
            "diet plan with banned-ingredient absence + grocery todos; "
            "WhatsApp→Android→call ordered touches; after-call WhatsApp summary; "
            "call-mode blocks buy/book/self_mod_apply; hard-approve book "
            "book_count=0 until Accept + calendar writeback + WhatsApp confirm; "
            "deny leaves execute 0; ignored hard approval expires → execute 0; "
            "failed booking never marks success; shopping propose buy_count=0; "
            "Accept under cap → dry-run receipt/audit; freeze blocks stale accepted "
            "approval execute; cap breach → spend_cap_* rejection artifact; "
            "E2E-07 deny path leaves buy_count=0; "
            "fail-closed on broken INV"
        ),
        "result": overall,
        "broken_allow_all": broken,
        "commands": [
            "./scripts/test-ci.sh --break-invariant"
            if broken
            else "./scripts/test-ci.sh"
        ],
        "artifacts": [
            "artifacts/test/ci/report.json",
            "artifacts/test/e2e-01/verification.json",
            "artifacts/test/e2e-02/verification.json",
            "artifacts/test/e2e-03/verification.json",
            "artifacts/test/e2e-04/verification.json",
            "artifacts/test/e2e-05/verification.json",
            "artifacts/test/e2e-06/verification.json",
            "artifacts/test/e2e-07/verification.json",
            "artifacts/test/e2e-09/verification.json",
            "artifacts/test/task-03/verification.json",
            "artifacts/test/task-04/verification.json",
            "artifacts/test/task-05/verification.json",
            "artifacts/test/task-06/verification.json",
            "artifacts/test/task-07/verification.json",
            "artifacts/test/task-09/verification.json",
            "artifacts/test/task-10/verification.json",
            "artifacts/test/task-11/verification.json",
            "artifacts/test/task-13/verification.json",
            "artifacts/test/task-15/verification.json",
            "artifacts/test/task-16/verification.json",
            "artifacts/test/task-17/verification.json",
            "artifacts/test/task-19/verification.json",
            "artifacts/test/task-20/verification.json",
            "artifacts/test/task-21/verification.json",
            "artifacts/test/task-22/verification.json",
        ],
        "invariants": [
            c.get("id")
            for L in layers
            if L["layer"] == "contract"
            for c in L.get("checks", [])
        ],
        "gate_e2e": [
            "E2E-01",
            "E2E-02",
            "E2E-03",
            "E2E-04",
            "E2E-05",
            "E2E-06",
            "E2E-07",
            "E2E-09",
        ],
        "t5_exit": overall == "PASS" and not broken,
        "t6_exit": overall == "PASS" and not broken,
        "e2e07_ready": overall == "PASS" and not broken,
    }
    (out_dir / "verification.json").write_text(
        json.dumps(stamp, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # TASK-02 dedicated artifact mirror (same CI results + trust focus).
    task02 = ROOT / "artifacts" / "test" / "task-02"
    task02.mkdir(parents=True, exist_ok=True)
    trust_ids = [
        c.get("id")
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith(("INV-APPR-", "INV-KILL-", "INV-AUDIT-"))
    ]
    trust_checks = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith(("INV-APPR-", "INV-KILL-", "INV-AUDIT-"))
    ]
    trust_pass = all(c.get("result") == "PASS" for c in trust_checks) if trust_checks else False
    write_report(
        task02,
        layer="task-02",
        result="PASS" if (overall == "PASS" and trust_pass) else ("FAIL" if not broken else overall),
        checks=trust_checks or flat_checks,
        extra={
            "broken_allow_all": broken,
            "trust_invariant_ids": trust_ids,
            "ci_overall": overall,
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
            },
        },
    )
    (task02 / "verification.json").write_text(
        json.dumps(
            {
                "claim": "No hard action path without accept; INV-APPR/KILL/AUDIT proven",
                "result": "PASS"
                if (overall == "PASS" and trust_pass)
                else ("FAIL" if not broken else overall),
                "ci_overall": overall,
                "trust_invariants": trust_ids,
                "commands": ["./scripts/test-ci.sh", "make test-ci"],
                "artifacts": [
                    "artifacts/test/task-02/report.json",
                    "artifacts/test/ci/report.json",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # TASK-03 WhatsApp ingress artifacts.
    task03 = ROOT / "artifacts" / "test" / "task-03"
    task03.mkdir(parents=True, exist_ok=True)
    ingress_ids = [
        c.get("id")
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-INGRESS-")
    ]
    ingress_checks = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-INGRESS-")
    ]
    ingress_pass = (
        all(c.get("result") == "PASS" for c in ingress_checks) if ingress_checks else False
    )
    # Mirror outbound from contract layer if present.
    contract_outbound = out_dir / "contract" / "outbound-messages.json"
    if contract_outbound.exists():
        (task03 / "outbound-messages.json").write_text(
            contract_outbound.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    write_report(
        task03,
        layer="task-03",
        result="PASS"
        if (overall == "PASS" and ingress_pass)
        else ("FAIL" if not broken else overall),
        checks=ingress_checks or flat_checks,
        extra={
            "broken_allow_all": broken,
            "ingress_invariant_ids": ingress_ids,
            "ci_overall": overall,
            "adversarial_coverage": [
                "non-allowlisted DM",
                "spoofed sender forms",
                "empty allowlist",
                "flood",
                "group is_group flag",
                "group_id without flag",
                "group JID / broadcast sender",
                "mixed DM then group",
                "audio transcript-or-clarify scaffold (003)",
            ],
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
                "artifacts": "artifacts/test/task-03/",
            },
        },
    )
    (task03 / "verification.json").write_text(
        json.dumps(
            {
                "claim": (
                    "Allowlisted DM only; groups disabled ignored; "
                    "non-allowlisted → no tools / no outbound side effects"
                ),
                "result": "PASS"
                if (overall == "PASS" and ingress_pass)
                else ("FAIL" if not broken else overall),
                "ci_overall": overall,
                "ingress_invariants": ingress_ids,
                "commands": [
                    "./scripts/test-ci.sh",
                    "make test-ci",
                    "make test-ci-fail-closed",
                ],
                "artifacts": [
                    "artifacts/test/task-03/report.json",
                    "artifacts/test/task-03/verification.json",
                    "artifacts/test/ci/report.json",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # TASK-04 personal memory artifacts.
    task04 = ROOT / "artifacts" / "test" / "task-04"
    task04.mkdir(parents=True, exist_ok=True)
    mem_ids = [
        c.get("id")
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-MEM-")
    ]
    mem_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.memory.")
    ]
    mem_pass = (
        all(c.get("result") == "PASS" for c in mem_integration) if mem_integration else False
    ) and (all(c.get("result") == "PASS" for c in [
        c for L in layers if L["layer"] == "contract" for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-MEM-")
    ]) if mem_ids else True)
    write_report(
        task04,
        layer="task-04",
        result="PASS"
        if (overall == "PASS" and mem_pass)
        else ("FAIL" if not broken else overall),
        checks=mem_integration,
        extra={
            "broken_allow_all": broken,
            "memory_invariant_ids": mem_ids,
            "ci_overall": overall,
            "fixture": "fixtures/memory/seed-profile.json",
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
                "artifacts": "artifacts/test/task-04/",
            },
        },
    )
    (task04 / "verification.json").write_text(
        json.dumps(
            {
                "claim": (
                    "Hot profile loadable; explicit remember + episodic persist across restart; "
                    "INV-MEM-001 rejects secrets in memory files"
                ),
                "result": "PASS"
                if (overall == "PASS" and mem_pass)
                else ("FAIL" if not broken else overall),
                "ci_overall": overall,
                "memory_invariants": mem_ids,
                "integration_checks": [c.get("id") for c in mem_integration],
                "commands": ["./scripts/test-ci.sh", "make test-ci"],
                "artifacts": [
                    "artifacts/test/task-04/report.json",
                    "artifacts/test/task-04/verification.json",
                    "fixtures/memory/seed-profile.json",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # TASK-05 hosting / reboot durability artifacts.
    task05 = ROOT / "artifacts" / "test" / "task-05"
    task05.mkdir(parents=True, exist_ok=True)
    hosting_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.hosting.")
    ]
    hosting_pass = (
        all(c.get("result") == "PASS" for c in hosting_integration)
        if hosting_integration
        else False
    )
    write_report(
        task05,
        layer="task-05",
        result="PASS"
        if (overall == "PASS" and hosting_pass)
        else ("FAIL" if not broken else overall),
        checks=hosting_integration,
        extra={
            "broken_allow_all": broken,
            "ci_overall": overall,
            "e2e_flow": "E2E-10 (restart mid-flight) — prep",
            "config": [
                "config/gateway.harness.json",
                "config/gateway.example.yaml",
                "config/backup.example.json",
            ],
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
                "artifacts": "artifacts/test/task-05/",
            },
        },
    )
    (task05 / "verification.json").write_text(
        json.dumps(
            {
                "claim": (
                    "Gateway config skeleton + durable approval store survives harness "
                    "restart; Accept works once (E2E-10 prep)"
                ),
                "result": "PASS"
                if (overall == "PASS" and hosting_pass)
                else ("FAIL" if not broken else overall),
                "ci_overall": overall,
                "e2e_flow": "E2E-10",
                "integration_checks": [c.get("id") for c in hosting_integration],
                "commands": ["./scripts/test-ci.sh", "make test-ci"],
                "artifacts": [
                    "artifacts/test/task-05/report.json",
                    "artifacts/test/task-05/verification.json",
                    "config/gateway.harness.json",
                    "config/backup.example.json",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # TASK-06 transcription pipeline artifacts.
    task06 = ROOT / "artifacts" / "test" / "task-06"
    task06.mkdir(parents=True, exist_ok=True)
    transcription_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith(("unit.stt.", "unit.tts."))
    ]
    transcription_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.transcription.")
    ]
    ingress_003 = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if c.get("id") == "INV-INGRESS-003"
    ]
    task06_checks = transcription_unit + transcription_integration + ingress_003
    task06_pass = (
        all(c.get("result") == "PASS" for c in task06_checks) if task06_checks else False
    )
    # Capture outbound sample from a voice turn for artifact convention.
    voice_catcher = OutboundMessageCatcher()
    voice_transport = MockWhatsAppTransport(
        allowlist=["+15550001111"],
        catcher=voice_catcher,
        pipeline=TranscriptionPipeline.from_fixtures(),
    )
    voice_transport.inject_audio("+15550001111", audio_fixture_id="fx-reminder")
    voice_catcher.write_json(task06 / "outbound-messages.json")
    write_report(
        task06,
        layer="task-06",
        result="PASS"
        if (overall == "PASS" and task06_pass)
        else ("FAIL" if not broken else overall),
        checks=task06_checks or flat_checks,
        extra={
            "broken_allow_all": broken,
            "ci_overall": overall,
            "e2e_flow": "E2E-01 (voice reminder) — STT dependency ready",
            "fixture_manifest": "fixtures/audio/manifest.json",
            "inv_ingress_003": [c.get("result") for c in ingress_003],
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
                "artifacts": "artifacts/test/task-06/",
            },
        },
    )
    (task06 / "verification.json").write_text(
        json.dumps(
            {
                "claim": (
                    "WhatsApp voice notes pass through STT stub; transcript turn or "
                    "clarification (INV-INGRESS-003); TTS inbound-mode policy; "
                    "E2E-01 audio fixture mapped"
                ),
                "result": "PASS"
                if (overall == "PASS" and task06_pass)
                else ("FAIL" if not broken else overall),
                "ci_overall": overall,
                "e2e_flow": "E2E-01",
                "fixture": "fixtures/audio/manifest.json",
                "unit_checks": [c.get("id") for c in transcription_unit],
                "integration_checks": [c.get("id") for c in transcription_integration],
                "invariants": ["INV-INGRESS-003"],
                "commands": [
                    "./scripts/test-ci.sh",
                    "make test-ci",
                    "make test-ci-fail-closed",
                ],
                "artifacts": [
                    "artifacts/test/task-06/report.json",
                    "artifacts/test/task-06/verification.json",
                    "artifacts/test/task-06/outbound-messages.json",
                    "fixtures/audio/manifest.json",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # TASK-07 reminders + habits artifacts.
    # Fail-closed (--break-invariant) must not stomp happy-path task-07 evidence:
    # INV break is expected overall FAIL; reminder checks are independent.
    reminder_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.reminder.")
    ]
    reminder_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith(("integration.reminder.", "integration.habit."))
    ]
    task07_checks = reminder_unit + reminder_integration
    task07_pass = (
        all(c.get("result") == "PASS" for c in task07_checks) if task07_checks else False
    )
    if not broken:
        task07 = ROOT / "artifacts" / "test" / "task-07"
        task07.mkdir(parents=True, exist_ok=True)
        # Capture confirm + fire outbound sample for artifact convention (E2E-01 prep).
        tz = ZoneInfo("Europe/Madrid")
        monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)
        demo_clock = FakeClock(start=monday)
        demo_catcher = OutboundMessageCatcher()
        demo_store = ReminderStore()
        demo_gw = ActionGateway(clock=demo_clock, reminders=demo_store)
        demo_svc = ReminderService(
            store=demo_store,
            clock=demo_clock,
            catcher=demo_catcher,
            gateway=demo_gw,
            timezone="Europe/Madrid",
            recipient="+15550001111",
        )
        demo = demo_svc.create_from_utterance(
            "Remind me Sunday at 18:00 to call grandma.",
            timezone="Europe/Madrid",
        )
        if demo.reminder is not None:
            demo_sched = ReminderScheduler(
                demo_store,
                demo_clock,
                demo_catcher,
                kill=demo_gw.kill,
                default_recipient="+15550001111",
            )
            demo_sched.advance(demo.reminder.due_at - demo_clock.now())
        demo_catcher.write_json(task07 / "outbound-messages.json")
        (task07 / "reminders.json").write_text(
            json.dumps(demo_store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_report(
            task07,
            layer="task-07",
            result="PASS" if task07_pass else "FAIL",
            checks=task07_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": (
                    "E2E-01 (voice reminder) — create/fire ready; "
                    "E2E-02 habit ladder scaffold"
                ),
                "seed_timezone": "Europe/Madrid",
                "agent_b_rerun": {
                    "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-07/",
                },
            },
        )
        (task07 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "One-shot + recurring reminders via FakeClock.advance; "
                        "outbound confirm/fire captured; habit WhatsApp-first "
                        "escalation scaffold; reminder_create is Auto "
                        "(no hard approval); E2E-01 ready"
                    ),
                    "result": "PASS" if task07_pass else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-01",
                    "e2e_prep": "E2E-02",
                    "seed_timezone": "Europe/Madrid",
                    "unit_checks": [c.get("id") for c in reminder_unit],
                    "integration_checks": [c.get("id") for c in reminder_integration],
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": [
                        "artifacts/test/task-07/report.json",
                        "artifacts/test/task-07/verification.json",
                        "artifacts/test/task-07/outbound-messages.json",
                        "artifacts/test/task-07/reminders.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-09 models router artifacts.
    models_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.models.")
    ]
    models_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.models.")
    ]
    model_invariants = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-MODEL-")
    ]
    task09_checks = models_unit + models_integration + model_invariants
    task09_pass = (
        all(c.get("result") == "PASS" for c in task09_checks) if task09_checks else False
    )
    if not broken:
        task09 = ROOT / "artifacts" / "test" / "task-09"
        task09.mkdir(parents=True, exist_ok=True)
        # Sample routing decisions for artifact convention (no live Luna).
        routing_sample = []
        fixture_path = ROOT / "fixtures" / "models" / "routing-intents.json"
        fixture = load_routing_fixture(fixture_path)
        for case in fixture.get("cases", []):
            signals = RoutingSignals.from_dict(case.get("signals") or {})
            decision = route(signals)
            routing_sample.append(
                {
                    "id": case.get("id"),
                    "expected_model": case.get("expected_model"),
                    "decision": decision.to_dict(),
                }
            )
        (task09 / "routing-decisions.json").write_text(
            json.dumps({"cases": routing_sample}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        registry = ModelStubRegistry()
        for role in ModelRole:
            registry.complete_as(role, f"sample prompt for {role.value}")
        (task09 / "stub-snapshot.json").write_text(
            json.dumps(registry.snapshot(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_report(
            task09,
            layer="task-09",
            result="PASS" if task09_pass else "FAIL",
            checks=task09_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "fixture": "fixtures/models/routing-intents.json",
                "model_invariants": [c.get("id") for c in model_invariants],
                "no_live_luna_in_ci": True,
                "agent_b_rerun": {
                    "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-09/",
                },
            },
        )
        (task09 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "Luna default routing; Terra/Sol escalation for hard planning "
                        "and self-mod; STT stub independent from chat model; "
                        "no live Luna in CI"
                    ),
                    "result": "PASS" if task09_pass else "FAIL",
                    "ci_overall": overall,
                    "fixture": "fixtures/models/routing-intents.json",
                    "unit_checks": [c.get("id") for c in models_unit],
                    "integration_checks": [c.get("id") for c in models_integration],
                    "invariants": [c.get("id") for c in model_invariants],
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": [
                        "artifacts/test/task-09/report.json",
                        "artifacts/test/task-09/verification.json",
                        "artifacts/test/task-09/routing-decisions.json",
                        "artifacts/test/task-09/stub-snapshot.json",
                        "fixtures/models/routing-intents.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-10 todos + Android projection artifacts.
    todo_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.todo.")
    ]
    todo_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.todo.")
    ]
    task10_checks = todo_unit + todo_integration
    task10_pass = (
        all(c.get("result") == "PASS" for c in task10_checks) if task10_checks else False
    )
    if not broken:
        task10 = ROOT / "artifacts" / "test" / "task-10"
        task10.mkdir(parents=True, exist_ok=True)
        e2e03_demo = run_e2e_03(
            root=ROOT,
            artifacts_dir=ROOT / "artifacts" / "test" / "e2e-03",
            write_artifacts=True,
        )
        demo_clock = FakeClock()
        demo_store = TodoStore()
        demo_gw = ActionGateway(clock=demo_clock, todos=demo_store)
        demo_catcher = OutboundMessageCatcher()
        demo_svc = TodoService(
            store=demo_store,
            clock=demo_clock,
            catcher=demo_catcher,
            gateway=demo_gw,
            recipient="+15550001111",
        )
        demo_android = AndroidProjectionApi(
            store=demo_store, clock=demo_clock, gateway=demo_gw
        )
        demo_created = demo_svc.create_from_utterance("Add todo: buy oat milk.")
        demo_proj = demo_android.list_todos()
        (task10 / "todos.json").write_text(
            json.dumps(demo_store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (task10 / "android-projection.json").write_text(
            json.dumps(
                {
                    "before_complete": [p.to_dict() for p in demo_proj],
                    "e2e03": {
                        "result": e2e03_demo.result,
                        "todo_id": e2e03_demo.todo_id,
                        "title": e2e03_demo.title,
                        "status": e2e03_demo.status,
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        demo_catcher.write_json(task10 / "outbound-messages.json")
        write_report(
            task10,
            layer="task-10",
            result="PASS" if task10_pass else "FAIL",
            checks=task10_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-03 (gate)",
                "demo_todo_id": demo_created.todo.id if demo_created.todo else None,
                "agent_b_rerun": {
                    "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-10/",
                },
            },
        )
        (task10 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "Todo store + Android projection API doubles: WhatsApp "
                        "'Add todo' Auto-creates; list/get/complete reflect same ids; "
                        "dedup near-identical open todos; E2E-03 gate green"
                    ),
                    "result": "PASS" if task10_pass else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-03",
                    "e2e03_result": e2e03_demo.result,
                    "unit_checks": [c.get("id") for c in todo_unit],
                    "integration_checks": [c.get("id") for c in todo_integration],
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-03",
                    ],
                    "artifacts": [
                        "artifacts/test/task-10/report.json",
                        "artifacts/test/task-10/verification.json",
                        "artifacts/test/task-10/todos.json",
                        "artifacts/test/task-10/android-projection.json",
                        "artifacts/test/task-10/outbound-messages.json",
                        "artifacts/test/e2e-03/verification.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-11 Android approval inbox + soft-confirm calendar hooks.
    # Fail-closed must not stomp happy-path task-11 verification.
    android_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.android_approval.")
    ]
    android_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.android_approval.")
    ]
    task11_checks = android_unit + android_integration
    task11_pass = (
        all(c.get("result") == "PASS" for c in task11_checks) if task11_checks else False
    )
    if not broken:
        t2_demo = run_t2_approval_inbox(
            root=ROOT,
            artifacts_dir=ROOT / "artifacts" / "test" / "task-11",
            write_artifacts=True,
        )
        task11 = ROOT / "artifacts" / "test" / "task-11"
        # run_t2 writes report/verification; enrich stamp with CI cross-check.
        stamp_path = task11 / "verification.json"
        if stamp_path.is_file():
            stamp_data = json.loads(stamp_path.read_text(encoding="utf-8"))
        else:
            stamp_data = {}
        stamp_data["ci_overall"] = overall
        stamp_data["unit_checks"] = [c.get("id") for c in android_unit]
        stamp_data["integration_checks"] = [c.get("id") for c in android_integration]
        stamp_data["task11_pass"] = task11_pass and t2_demo.ok
        stamp_data["result"] = "PASS" if (task11_pass and t2_demo.ok) else "FAIL"
        stamp_path.write_text(
            json.dumps(stamp_data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # TASK-13 calendar read/write + soft confirm.
    # Fail-closed must not stomp happy-path task-13 verification.
    calendar_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.calendar.")
    ]
    calendar_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.calendar.")
    ]
    task13_checks = calendar_unit + calendar_integration
    task13_pass = (
        all(c.get("result") == "PASS" for c in task13_checks) if task13_checks else False
    )
    if not broken:
        task13 = ROOT / "artifacts" / "test" / "task-13"
        task13.mkdir(parents=True, exist_ok=True)
        demo_vu = VirtualUser.bootstrap(root=ROOT)
        demo_turn = demo_vu.inject_text(EXPECTED_E2E04_UTTERANCE)
        demo_prop = demo_vu.last_calendar_propose
        create_before = demo_vu.calendar_create_count()
        demo_accept = (
            demo_vu.accept_approval(demo_prop.approval_id)
            if demo_prop and demo_prop.approval_id
            else None
        )
        create_after_accept = demo_vu.calendar_create_count()

        # Deny path on a fresh VU.
        deny_vu = VirtualUser.bootstrap(root=ROOT)
        deny_prop = deny_vu.schedule_from_utterance("Schedule dentist Saturday 15:00–16:00.")
        deny_create_before = deny_vu.calendar_create_count()
        deny_result = (
            deny_vu.deny_approval(deny_prop.approval_id) if deny_prop.approval_id else None
        )
        deny_create_after = deny_vu.calendar_create_count()

        (task13 / "calendar.json").write_text(
            json.dumps(
                {
                    "accept_path": {
                        "utterance": EXPECTED_E2E04_UTTERANCE,
                        "create_before_accept": create_before,
                        "create_after_accept": create_after_accept,
                        "events": demo_vu.gateway.calendar.events,
                        "approval_id": demo_prop.approval_id if demo_prop else None,
                        "parsed_start": (
                            demo_prop.parsed.start.isoformat()
                            if demo_prop and demo_prop.parsed
                            else None
                        ),
                    },
                    "deny_path": {
                        "create_before": deny_create_before,
                        "create_after": deny_create_after,
                        "events": deny_vu.gateway.calendar.events,
                        "deny_status": deny_result.status if deny_result else None,
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        demo_vu.catcher.write_json(task13 / "outbound-messages.json")
        (task13 / "approvals.json").write_text(
            json.dumps(
                {
                    "accept": demo_vu.android_inbox.snapshot(),
                    "deny": deny_vu.android_inbox.snapshot(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            task13,
            layer="task-13",
            result="PASS" if task13_pass else "FAIL",
            checks=task13_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-04 (prep)",
                "nl_tools": getattr(demo_turn, "tool_calls", None),
                "agent_b_rerun": {
                    "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-13/",
                },
            },
        )
        (task13 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "In-memory calendar + conflict-aware soft confirm (INV-APPR-003): "
                        "NL 'Schedule focus block Friday 09:00–11:00.' proposes pending "
                        "soft confirm with create_count=0; Accept creates once; Deny "
                        "creates nothing; E2E-04 ready"
                    ),
                    "result": "PASS" if task13_pass else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-04",
                    "e2e04_ready": task13_pass,
                    "invariants": ["INV-APPR-003"],
                    "unit_checks": [c.get("id") for c in calendar_unit],
                    "integration_checks": [c.get("id") for c in calendar_integration],
                    "create_before_accept": create_before,
                    "create_after_accept": create_after_accept,
                    "deny_create_after": deny_create_after,
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-03",
                    ],
                    "artifacts": [
                        "artifacts/test/task-13/report.json",
                        "artifacts/test/task-13/verification.json",
                        "artifacts/test/task-13/calendar.json",
                        "artifacts/test/task-13/approvals.json",
                        "artifacts/test/task-13/outbound-messages.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-15 diet planning v1.
    # Fail-closed must not stomp happy-path task-15 verification.
    diet_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.diet.")
    ]
    diet_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.diet.")
    ]
    task15_checks = diet_unit + diet_integration
    task15_pass = (
        all(c.get("result") == "PASS" for c in task15_checks) if task15_checks else False
    )
    if not broken:
        task15 = ROOT / "artifacts" / "test" / "task-15"
        task15.mkdir(parents=True, exist_ok=True)
        structure = run_e2e_05_structure(
            root=ROOT,
            artifacts_dir=ROOT / "artifacts" / "test" / "e2e-05-structure",
            write_artifacts=True,
        )
        demo_vu = VirtualUser.bootstrap(root=ROOT)
        demo_turn = demo_vu.inject_text(EXPECTED_E2E05_UTTERANCE)
        demo_plan = demo_vu.last_plan_meals
        (task15 / "meal-plan.json").write_text(
            json.dumps(
                demo_plan.plan.to_dict() if demo_plan and demo_plan.plan else {},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (task15 / "grocery-todos.json").write_text(
            json.dumps(demo_vu.todo_store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        demo_vu.catcher.write_json(task15 / "outbound-messages.json")
        write_report(
            task15,
            layer="task-15",
            result="PASS" if task15_pass else "FAIL",
            checks=task15_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-05 (structure)",
                "eval_lane_blocking": False,
                "nl_tools": getattr(demo_turn, "tool_calls", None),
                "agent_b_rerun": {
                    "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-15/",
                },
            },
        )
        (task15 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "Diet planning v1: memory constraints + schedule → structured "
                        "meal plan; banned ingredients absent; grocery todos created; "
                        "E2E-05 structure ready"
                    ),
                    "result": "PASS" if task15_pass else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-05",
                    "e2e05_ready": task15_pass and structure.ok,
                    "eval_lane_blocking": False,
                    "eval_score": structure.eval_score,
                    "unit_checks": [c.get("id") for c in diet_unit],
                    "integration_checks": [c.get("id") for c in diet_integration],
                    "grocery_todo_count": len(demo_vu.grocery_todos()),
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-03",
                        "make e2e-04",
                    ],
                    "artifacts": [
                        "artifacts/test/task-15/report.json",
                        "artifacts/test/task-15/verification.json",
                        "artifacts/test/task-15/meal-plan.json",
                        "artifacts/test/task-15/grocery-todos.json",
                        "artifacts/test/task-15/outbound-messages.json",
                        "artifacts/test/e2e-05-structure/verification.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-16 E2E-05 diet → groceries gate.
    # Fail-closed must not stomp happy-path task-16 verification.
    e2e05_checks = [
        c
        for L in layers
        if L["layer"] == "e2e"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("e2e-05.")
    ]
    task16_pass = (
        all(c.get("result") == "PASS" for c in e2e05_checks if c.get("gate", True))
        if e2e05_checks
        else False
    )
    if not broken:
        task16 = ROOT / "artifacts" / "test" / "task-16"
        task16.mkdir(parents=True, exist_ok=True)
        journey05 = run_e2e_05(
            root=ROOT,
            artifacts_dir=ROOT / "artifacts" / "test" / "e2e-05",
            write_artifacts=True,
        )
        demo_vu = VirtualUser.bootstrap(root=ROOT)
        demo_turn = demo_vu.inject_text(EXPECTED_E2E05_UTTERANCE)
        demo_plan = demo_vu.last_plan_meals
        (task16 / "meal-plan.json").write_text(
            json.dumps(
                demo_plan.plan.to_dict() if demo_plan and demo_plan.plan else {},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (task16 / "grocery-todos.json").write_text(
            json.dumps(demo_vu.todo_store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        demo_vu.catcher.write_json(task16 / "outbound-messages.json")
        write_report(
            task16,
            layer="task-16",
            result="PASS" if task16_pass else "FAIL",
            checks=e2e05_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-05",
                "gate": True,
                "eval_lane_blocking": False,
                "nl_tools": getattr(demo_turn, "tool_calls", None),
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-05",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-16/",
                },
            },
        )
        (task16 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "E2E-05 diet → groceries: seed memory with dislikes/allergies → "
                        "'Plan meals for tomorrow.' → structured plan + grocery todos; "
                        "banned ingredients absent; T3 exit for diet path"
                    ),
                    "result": "PASS" if task16_pass and journey05.ok else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-05",
                    "gate": True,
                    "t3_exit": task16_pass and journey05.ok,
                    "eval_lane_blocking": False,
                    "eval_score": journey05.eval_score,
                    "grocery_todo_count": journey05.grocery_todo_count,
                    "e2e_checks": [c.get("id") for c in e2e05_checks],
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-03",
                        "make e2e-04",
                        "make e2e-05",
                    ],
                    "artifacts": [
                        "artifacts/test/task-16/report.json",
                        "artifacts/test/task-16/verification.json",
                        "artifacts/test/task-16/meal-plan.json",
                        "artifacts/test/task-16/grocery-todos.json",
                        "artifacts/test/task-16/outbound-messages.json",
                        "artifacts/test/e2e-05/verification.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-17 outbound voice calls + escalation ladder.
    # Fail-closed must not stomp happy-path task-17 verification.
    voice_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.voice.")
    ]
    voice_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.voice.")
    ]
    appr005 = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if c.get("id") == "INV-APPR-005"
    ]
    task17_checks = voice_unit + voice_integration + appr005
    task17_pass = (
        all(c.get("result") == "PASS" for c in task17_checks) if task17_checks else False
    )
    if not broken:
        task17 = ROOT / "artifacts" / "test" / "task-17"
        task17.mkdir(parents=True, exist_ok=True)
        tz = ZoneInfo("Europe/Madrid")
        monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)
        demo_clock = FakeClock(start=monday)
        demo_catcher = OutboundMessageCatcher()
        demo_store = ReminderStore()
        demo_gw = ActionGateway(clock=demo_clock, reminders=demo_store)
        demo_voice = MockVoiceProvider(demo_catcher, demo_clock, default_to="+15550001111")
        demo_android = AndroidNotificationCatcher(
            demo_clock, demo_catcher, default_to="+15550001111"
        )
        demo_svc = ReminderService(
            store=demo_store,
            clock=demo_clock,
            catcher=demo_catcher,
            gateway=demo_gw,
            timezone="Europe/Madrid",
            recipient="+15550001111",
        )
        demo = demo_svc.create_from_utterance(
            "every Sunday at 18:00 remind me to stretch",
            as_habit=True,
            habit_priority="high",
            escalation_enabled=True,
        )
        demo_sched = ReminderScheduler(
            demo_store,
            demo_clock,
            demo_catcher,
            kill=demo_gw.kill,
            default_recipient="+15550001111",
            voice=demo_voice,
            android=demo_android,
        )
        channel_touches: list[str] = []
        if demo.reminder is not None and demo.habit is not None:
            for _ in range(3):
                rem = demo_store.get(demo.reminder.id)
                if rem is None:
                    break
                fires = demo_sched.advance(rem.due_at - demo_clock.now())
                for f in fires:
                    if f.emitted:
                        channel_touches.append(f.channel)
        # Probe INV-APPR-005 on a fresh active call for artifact evidence.
        probe = demo_voice.place_call(script="Calling about: allowlist probe")
        probe_invocations = []
        for tool in ("calendar_read", "buy", "book", "self_mod_apply"):
            res = demo_voice.invoke_tool(probe.id, tool, {"item": tool})
            probe_invocations.append(res.invocation.to_dict())
        demo_voice.end_call(probe.id, outcome="task17_artifact")

        (task17 / "calls.json").write_text(
            json.dumps(demo_voice.snapshot(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (task17 / "android-notifications.json").write_text(
            json.dumps({"notifications": demo_android.to_list()}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        demo_catcher.write_json(task17 / "outbound-messages.json")
        (task17 / "escalation-touches.json").write_text(
            json.dumps(
                {
                    "channel_touches": channel_touches,
                    "expected": ["whatsapp", "android", "call"],
                    "habit": demo.habit.to_dict() if demo.habit else None,
                    "probe_invocations": probe_invocations,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            task17,
            layer="task-17",
            result="PASS" if task17_pass else "FAIL",
            checks=task17_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-02",
                "e2e02_ready": task17_pass and channel_touches == ["whatsapp", "android", "call"],
                "channel_touches": channel_touches,
                "call_count": demo_voice.call_count,
                "agent_b_rerun": {
                    "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-17/",
                },
            },
        )
        (task17 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "TASK-17 outbound voice calls: mock provider places call + "
                        "records tool invocations; INV-APPR-005 blocks "
                        "buy/book/self_mod_apply mid-call; after-call WhatsApp "
                        "summary queued; habit escalation ladder "
                        "WhatsApp→Android→call ready for E2E-02"
                    ),
                    "result": "PASS" if task17_pass else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-02",
                    "e2e02_ready": task17_pass
                    and channel_touches == ["whatsapp", "android", "call"],
                    "invariants": ["INV-APPR-005"],
                    "unit_checks": [c.get("id") for c in voice_unit],
                    "integration_checks": [c.get("id") for c in voice_integration],
                    "channel_touches": channel_touches,
                    "call_count": demo_voice.call_count,
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-03",
                        "make e2e-04",
                        "make e2e-05",
                    ],
                    "artifacts": [
                        "artifacts/test/task-17/report.json",
                        "artifacts/test/task-17/verification.json",
                        "artifacts/test/task-17/calls.json",
                        "artifacts/test/task-17/outbound-messages.json",
                        "artifacts/test/task-17/android-notifications.json",
                        "artifacts/test/task-17/escalation-touches.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-19 Booksy stub portal bookings + hard approve + INV-BOOK-*.
    # Fail-closed must not stomp happy-path task-19 verification.
    booking_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.booking.")
    ]
    booking_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.booking.")
    ]
    book_invs = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-BOOK-")
    ]
    task19_checks = booking_unit + booking_integration + book_invs
    task19_pass = (
        all(c.get("result") == "PASS" for c in task19_checks) if task19_checks else False
    )
    if not broken:
        task19 = ROOT / "artifacts" / "test" / "task-19"
        task19.mkdir(parents=True, exist_ok=True)
        tz = ZoneInfo("Europe/Madrid")
        monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)
        demo_clock = FakeClock(start=monday)
        demo_catcher = OutboundMessageCatcher()
        demo_cal = CalendarStore()
        demo_gw = ActionGateway(clock=demo_clock)
        demo_svc = BookingService(
            clock=demo_clock,
            catcher=demo_catcher,
            gateway=demo_gw,
            calendar_store=demo_cal,
            timezone="Europe/Madrid",
            recipient="+15550001111",
            portal_fixture=ROOT / "fixtures" / "browser" / "booksy-stub-slots.json",
        )
        demo_prop = demo_svc.propose_from_utterance(EXPECTED_E2E06_UTTERANCE)
        book_before = demo_gw.commerce.book_count
        demo_inbox = AndroidApprovalInboxApi(demo_gw)
        demo_accept = (
            demo_inbox.accept(demo_prop.approval_id) if demo_prop.approval_id else None
        )
        demo_confirms = [
            m for m in demo_catcher.messages if m.meta.get("kind") == "booking_confirm"
        ]
        demo_task = (
            demo_svc.store.get(demo_prop.task_id) if demo_prop.task_id else None
        )

        # Deny variant artifact evidence.
        deny_clock = FakeClock(start=monday)
        deny_catcher = OutboundMessageCatcher()
        deny_gw = ActionGateway(clock=deny_clock)
        deny_svc = BookingService(
            clock=deny_clock,
            catcher=deny_catcher,
            gateway=deny_gw,
            timezone="Europe/Madrid",
            recipient="+15550001111",
            portal_fixture=ROOT / "fixtures" / "browser" / "booksy-stub-slots.json",
        )
        deny_prop = deny_svc.propose_from_utterance(EXPECTED_E2E06_UTTERANCE)
        if deny_prop.approval_id:
            AndroidApprovalInboxApi(deny_gw).deny(deny_prop.approval_id)
            deny_svc.mark_denied_for_approval(deny_prop.approval_id)

        (task19 / "bookings.json").write_text(
            json.dumps(
                {
                    "accept_path": {
                        "propose": {
                            "ok": demo_prop.ok,
                            "approval_id": demo_prop.approval_id,
                            "task_id": demo_prop.task_id,
                            "options": demo_prop.options,
                            "book_count_at_propose": book_before,
                        },
                        "accept_ok": getattr(demo_accept, "ok", None),
                        "book_count": demo_gw.commerce.book_count,
                        "calendar_create_count": demo_gw.calendar.create_count,
                        "task": demo_task.to_dict() if demo_task else None,
                        "calendar_events": [e.to_dict() for e in demo_cal.list_all()],
                    },
                    "deny_path": {
                        "approval_id": deny_prop.approval_id,
                        "book_count": deny_gw.commerce.book_count,
                        "task": (
                            deny_svc.store.get(deny_prop.task_id).to_dict()
                            if deny_prop.task_id and deny_svc.store.get(deny_prop.task_id)
                            else None
                        ),
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        demo_catcher.write_json(task19 / "outbound-messages.json")
        (task19 / "approvals.json").write_text(
            json.dumps(
                {
                    "accept": [a.to_dict() for a in demo_gw.approvals.list()],
                    "deny": [a.to_dict() for a in deny_gw.approvals.list()],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (task19 / "portal-slots.json").write_text(
            json.dumps(
                {
                    "shop": demo_svc.portal.shop_card(),
                    "proposed_options": demo_prop.options,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        e2e06_ready = (
            task19_pass
            and demo_prop.ok
            and book_before == 0
            and demo_gw.commerce.book_count == 1
            and demo_gw.calendar.create_count == 1
            and len(demo_confirms) == 1
            and deny_gw.commerce.book_count == 0
        )
        e2e09_ready = any(
            c.get("id") == "integration.booking.expiry_e2e09_ready"
            and c.get("result") == "PASS"
            for c in booking_integration
        )
        write_report(
            task19,
            layer="task-19",
            result="PASS" if task19_pass else "FAIL",
            checks=task19_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-06",
                "e2e06_ready": e2e06_ready,
                "e2e09_ready": e2e09_ready,
                "book_count_after_accept": demo_gw.commerce.book_count,
                "book_count_after_deny": deny_gw.commerce.book_count,
                "agent_b_rerun": {
                    "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-19/",
                },
            },
        )
        (task19 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "TASK-19 Booksy stub portal: propose 2–3 slots behind hard "
                        "approve (book_count=0); Accept → one book execute + calendar "
                        "writeback + WhatsApp confirm; Deny leaves execute at 0; "
                        "INV-BOOK-001/002 green; E2E-06/E2E-09 readiness"
                    ),
                    "result": "PASS" if task19_pass else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-06",
                    "e2e06_ready": e2e06_ready,
                    "e2e09_ready": e2e09_ready,
                    "invariants": ["INV-BOOK-001", "INV-BOOK-002"],
                    "unit_checks": [c.get("id") for c in booking_unit],
                    "integration_checks": [c.get("id") for c in booking_integration],
                    "book_count_after_accept": demo_gw.commerce.book_count,
                    "book_count_after_deny": deny_gw.commerce.book_count,
                    "calendar_writeback": demo_gw.calendar.create_count == 1,
                    "whatsapp_confirm": len(demo_confirms) == 1,
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-02",
                        "make e2e-03",
                        "make e2e-04",
                        "make e2e-05",
                    ],
                    "artifacts": [
                        "artifacts/test/task-19/report.json",
                        "artifacts/test/task-19/verification.json",
                        "artifacts/test/task-19/bookings.json",
                        "artifacts/test/task-19/approvals.json",
                        "artifacts/test/task-19/outbound-messages.json",
                        "artifacts/test/task-19/portal-slots.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-20 E2E-06 Booksy gate + E2E-09 expiry (T5 exit).
    # Fail-closed must not stomp happy-path task-20 / e2e-06 / e2e-09 verification.
    e2e06_checks = [
        c
        for L in layers
        if L["layer"] == "e2e"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("e2e-06.")
    ]
    e2e09_checks = [
        c
        for L in layers
        if L["layer"] == "e2e"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("e2e-09.")
    ]
    task20_pass = (
        bool(e2e06_checks)
        and all(c.get("result") == "PASS" for c in e2e06_checks if c.get("gate", True))
        and bool(e2e09_checks)
        and all(c.get("result") == "PASS" for c in e2e09_checks if c.get("gate", True))
    )
    if not broken:
        task20 = ROOT / "artifacts" / "test" / "task-20"
        task20.mkdir(parents=True, exist_ok=True)
        journey06 = run_e2e_06(
            root=ROOT,
            artifacts_dir=ROOT / "artifacts" / "test" / "e2e-06",
            write_artifacts=True,
        )
        journey09 = run_e2e_09(
            root=ROOT,
            artifacts_dir=ROOT / "artifacts" / "test" / "e2e-09",
            write_artifacts=True,
        )
        t5_exit = journey06.ok and journey09.ok and task20_pass
        write_report(
            task20,
            layer="task-20",
            result="PASS" if t5_exit else "FAIL",
            checks=e2e06_checks + e2e09_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-06",
                "gate": True,
                "t5_exit": t5_exit,
                "book_count_after_accept": journey06.book_count_after_accept,
                "book_count_after_deny": journey06.book_count_after_deny,
                "e2e09_status": journey09.status,
                "e2e09_book_count": journey09.book_count,
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-06",
                        "make e2e-09",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-20/",
                },
            },
        )
        (task20 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "TASK-20 / T5 exit: E2E-06 Booksy propose→approve→book "
                        "(+ deny leaves execute 0) gated green; E2E-09 ignored hard "
                        "approval expires → late Accept/execute blocked, book_count=0; "
                        "INV-BOOK-* intact"
                    ),
                    "result": "PASS" if t5_exit else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-06",
                    "gate": True,
                    "t5_exit": t5_exit,
                    "e2e06_result": journey06.result,
                    "e2e09_result": journey09.result,
                    "book_count_after_accept": journey06.book_count_after_accept,
                    "book_count_after_deny": journey06.book_count_after_deny,
                    "calendar_create_after_accept": journey06.calendar_create_after_accept,
                    "e2e09_status": journey09.status,
                    "e2e09_book_count": journey09.book_count,
                    "checks": [c.get("id") for c in e2e06_checks + e2e09_checks],
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-02",
                        "make e2e-03",
                        "make e2e-04",
                        "make e2e-05",
                        "make e2e-06",
                        "make e2e-09",
                    ],
                    "artifacts": [
                        "artifacts/test/task-20/report.json",
                        "artifacts/test/task-20/verification.json",
                        "artifacts/test/e2e-06/verification.json",
                        "artifacts/test/e2e-09/verification.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-21 Shopping skill (caps, freeze, dry-run) + INV-PAY-*.
    # Fail-closed must not stomp happy-path task-21 verification.
    shopping_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("unit.shopping.")
    ]
    shopping_integration = [
        c
        for L in layers
        if L["layer"] == "integration"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("integration.shopping.")
    ]
    pay_invs = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-PAY-")
    ]
    task21_checks = shopping_unit + shopping_integration + pay_invs
    task21_pass = (
        all(c.get("result") == "PASS" for c in task21_checks) if task21_checks else False
    )
    if not broken:
        task21 = ROOT / "artifacts" / "test" / "task-21"
        task21.mkdir(parents=True, exist_ok=True)
        tz = ZoneInfo("Europe/Madrid")
        monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)
        demo_clock = FakeClock(start=monday)
        demo_catcher = OutboundMessageCatcher()
        demo_gw = ActionGateway(clock=demo_clock)
        demo_svc = ShoppingService(
            clock=demo_clock,
            catcher=demo_catcher,
            gateway=demo_gw,
            recipient="+15550001111",
            merchant_fixture=ROOT / "fixtures" / "shopping" / "merchant-catalog.json",
            caps_config=ROOT / "config" / "shopping.harness.json",
        )
        demo_prop = demo_svc.propose_from_utterance(EXPECTED_E2E07_UTTERANCE)
        buy_before = demo_gw.commerce.buy_count
        demo_inbox = AndroidApprovalInboxApi(demo_gw)
        demo_accept = (
            demo_inbox.accept(demo_prop.approval_id) if demo_prop.approval_id else None
        )
        demo_receipts = [
            m for m in demo_catcher.messages if m.meta.get("kind") == "shopping_receipt"
        ]
        demo_task = (
            demo_svc.store.get(demo_prop.task_id) if demo_prop.task_id else None
        )

        # Freeze path: stale accepted approval blocked.
        freeze_clock = FakeClock(start=monday)
        freeze_catcher = OutboundMessageCatcher()
        freeze_gw = ActionGateway(clock=freeze_clock)
        freeze_svc = ShoppingService(
            clock=freeze_clock,
            catcher=freeze_catcher,
            gateway=freeze_gw,
            recipient="+15550001111",
            merchant_fixture=ROOT / "fixtures" / "shopping" / "merchant-catalog.json",
            caps_config=ROOT / "config" / "shopping.harness.json",
        )
        freeze_prop = freeze_svc.propose_from_utterance(EXPECTED_E2E07_UTTERANCE)
        freeze_exec_reason = None
        if freeze_prop.approval_id:
            freeze_gw.accept(freeze_prop.approval_id)
            freeze_gw.freeze_spending()
            freeze_exec = freeze_gw.execute(freeze_prop.approval_id)
            freeze_exec_reason = freeze_exec.reason

        # Cap path.
        cap_clock = FakeClock(start=monday)
        cap_catcher = OutboundMessageCatcher()
        cap_gw = ActionGateway(clock=cap_clock)
        cap_svc = ShoppingService(
            clock=cap_clock,
            catcher=cap_catcher,
            gateway=cap_gw,
            recipient="+15550001111",
            merchant_fixture=ROOT / "fixtures" / "shopping" / "merchant-catalog.json",
            spend_caps=SpendCapConfig(daily_limit=10.0, weekly_limit=150.0),
        )
        cap_prop = cap_svc.propose_from_utterance(EXPECTED_E2E07_UTTERANCE)
        cap_reason = None
        if cap_prop.approval_id:
            cap_accept = AndroidApprovalInboxApi(cap_gw).accept(cap_prop.approval_id)
            cap_reason = cap_accept.execute.reason if cap_accept.execute else None

        # Deny path.
        deny_clock = FakeClock(start=monday)
        deny_catcher = OutboundMessageCatcher()
        deny_gw = ActionGateway(clock=deny_clock)
        deny_svc = ShoppingService(
            clock=deny_clock,
            catcher=deny_catcher,
            gateway=deny_gw,
            recipient="+15550001111",
            merchant_fixture=ROOT / "fixtures" / "shopping" / "merchant-catalog.json",
            caps_config=ROOT / "config" / "shopping.harness.json",
        )
        deny_prop = deny_svc.propose_from_utterance(EXPECTED_E2E07_UTTERANCE)
        if deny_prop.approval_id:
            AndroidApprovalInboxApi(deny_gw).deny(deny_prop.approval_id)

        (task21 / "purchases.json").write_text(
            json.dumps(
                {
                    "accept_path": {
                        "propose": {
                            "ok": demo_prop.ok,
                            "approval_id": demo_prop.approval_id,
                            "task_id": demo_prop.task_id,
                            "price": demo_prop.price,
                            "sku": demo_prop.sku,
                            "merchant": demo_prop.merchant,
                            "buy_count_at_propose": buy_before,
                        },
                        "accept_ok": getattr(demo_accept, "ok", None),
                        "buy_count": demo_gw.commerce.buy_count,
                        "task": demo_task.to_dict() if demo_task else None,
                        "receipt": (
                            demo_accept.execute.result
                            if demo_accept and demo_accept.execute
                            else None
                        ),
                        "spend_ledger": demo_gw.spend.snapshot(),
                    },
                    "freeze_path": {
                        "approval_id": freeze_prop.approval_id,
                        "buy_count": freeze_gw.commerce.buy_count,
                        "execute_reason": freeze_exec_reason,
                        "policy": "block_stale_accepted_do_not_cancel",
                        "rejections": list(freeze_gw.execute_rejections),
                    },
                    "cap_path": {
                        "approval_id": cap_prop.approval_id,
                        "price": cap_prop.price,
                        "buy_count": cap_gw.commerce.buy_count,
                        "execute_reason": cap_reason,
                        "rejections": list(cap_gw.execute_rejections),
                    },
                    "deny_path": {
                        "approval_id": deny_prop.approval_id,
                        "buy_count": deny_gw.commerce.buy_count,
                        "task": (
                            deny_svc.store.get(deny_prop.task_id).to_dict()
                            if deny_prop.task_id and deny_svc.store.get(deny_prop.task_id)
                            else None
                        ),
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        demo_catcher.write_json(task21 / "outbound-messages.json")
        (task21 / "approvals.json").write_text(
            json.dumps(
                {
                    "accept": [a.to_dict() for a in demo_gw.approvals.list()],
                    "freeze": [a.to_dict() for a in freeze_gw.approvals.list()],
                    "cap": [a.to_dict() for a in cap_gw.approvals.list()],
                    "deny": [a.to_dict() for a in deny_gw.approvals.list()],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (task21 / "audit.json").write_text(
            json.dumps(
                {
                    "accept": demo_gw.audit.snapshot(),
                    "freeze": freeze_gw.audit.snapshot(),
                    "cap": cap_gw.audit.snapshot(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (task21 / "merchant-catalog.json").write_text(
            json.dumps(
                {
                    "merchant": demo_svc.merchant.merchant_card(),
                    "proposed_options": demo_prop.options,
                    "chosen_price": demo_prop.price,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        e2e07_ready = (
            task21_pass
            and demo_prop.ok
            and buy_before == 0
            and demo_gw.commerce.buy_count == 1
            and len(demo_receipts) == 1
            and freeze_gw.commerce.buy_count == 0
            and freeze_exec_reason == "freeze_spending"
            and cap_gw.commerce.buy_count == 0
            and cap_reason == "spend_cap_daily"
            and deny_gw.commerce.buy_count == 0
        )
        write_report(
            task21,
            layer="task-21",
            result="PASS" if task21_pass else "FAIL",
            checks=task21_checks or flat_checks,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-07",
                "e2e07_ready": e2e07_ready,
                "buy_count_after_accept": demo_gw.commerce.buy_count,
                "buy_count_after_freeze": freeze_gw.commerce.buy_count,
                "buy_count_after_cap": cap_gw.commerce.buy_count,
                "buy_count_after_deny": deny_gw.commerce.buy_count,
                "freeze_policy": "block_stale_accepted_do_not_cancel",
                "agent_b_rerun": {
                    "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-21/",
                },
            },
        )
        (task21 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "TASK-21 shopping dry-run merchant: propose usual protein "
                        "powder behind hard approve (buy_count=0 + price shown); "
                        "Accept under cap → one dry-run purchase + receipt/audit; "
                        "freeze blocks execute even with stale accepted approval "
                        "(policy: do not cancel); over-cap → spend_cap_daily "
                        "rejection artifact; Deny leaves buy_count=0; "
                        "INV-PAY-001/002 green; E2E-07 readiness"
                    ),
                    "result": "PASS" if task21_pass else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-07",
                    "e2e07_ready": e2e07_ready,
                    "invariants": ["INV-PAY-001", "INV-PAY-002"],
                    "unit_checks": [c.get("id") for c in shopping_unit],
                    "integration_checks": [c.get("id") for c in shopping_integration],
                    "buy_count_after_accept": demo_gw.commerce.buy_count,
                    "buy_count_after_freeze": freeze_gw.commerce.buy_count,
                    "buy_count_after_cap": cap_gw.commerce.buy_count,
                    "buy_count_after_deny": deny_gw.commerce.buy_count,
                    "freeze_policy": "block_stale_accepted_do_not_cancel",
                    "dry_run_receipt": len(demo_receipts) == 1,
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-02",
                        "make e2e-03",
                        "make e2e-04",
                        "make e2e-05",
                        "make e2e-06",
                        "make e2e-07",
                        "make e2e-09",
                    ],
                    "artifacts": [
                        "artifacts/test/task-21/report.json",
                        "artifacts/test/task-21/verification.json",
                        "artifacts/test/task-21/purchases.json",
                        "artifacts/test/task-21/approvals.json",
                        "artifacts/test/task-21/audit.json",
                        "artifacts/test/task-21/outbound-messages.json",
                        "artifacts/test/task-21/merchant-catalog.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    # TASK-22 E2E-07 Shopping with cap / freeze (+ deny) — T6 exit.
    # Fail-closed must not stomp happy-path task-22 / e2e-07 verification.
    e2e07_checks = [
        c
        for L in layers
        if L["layer"] == "e2e"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("e2e-07.")
    ]
    pay_invs_t22 = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-PAY-")
    ]
    task22_pass = (
        bool(e2e07_checks)
        and all(c.get("result") == "PASS" for c in e2e07_checks if c.get("gate", True))
        and bool(pay_invs_t22)
        and all(c.get("result") == "PASS" for c in pay_invs_t22)
    )
    if not broken:
        task22 = ROOT / "artifacts" / "test" / "task-22"
        task22.mkdir(parents=True, exist_ok=True)
        journey07 = run_e2e_07(
            root=ROOT,
            artifacts_dir=ROOT / "artifacts" / "test" / "e2e-07",
            write_artifacts=True,
        )
        t6_exit = journey07.ok and task22_pass
        write_report(
            task22,
            layer="task-22",
            result="PASS" if t6_exit else "FAIL",
            checks=e2e07_checks + pay_invs_t22,
            extra={
                "broken_allow_all": broken,
                "ci_overall": overall,
                "e2e_flow": "E2E-07",
                "gate": True,
                "t6_exit": t6_exit,
                "buy_count_after_accept": journey07.buy_count_after_accept,
                "buy_count_after_deny": journey07.buy_count_after_deny,
                "buy_count_after_freeze": journey07.buy_count_after_freeze,
                "buy_count_after_cap": journey07.buy_count_after_cap,
                "proposed_price": journey07.proposed_price,
                "freeze_reason": journey07.freeze_reason,
                "cap_reason": journey07.cap_reason,
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-07",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-22/",
                },
            },
        )
        (task22 / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "TASK-22 / T6 exit: E2E-07 Shopping with cap/freeze gated "
                        "green (propose price + buy=0; Accept under cap → dry-run "
                        "receipt/audit; freeze blocks execute; over cap → "
                        "spend_cap_daily; Deny leaves buy_count=0); INV-PAY-001/002 "
                        "intact"
                    ),
                    "result": "PASS" if t6_exit else "FAIL",
                    "ci_overall": overall,
                    "e2e_flow": "E2E-07",
                    "gate": True,
                    "t6_exit": t6_exit,
                    "e2e07_result": journey07.result,
                    "buy_count_after_accept": journey07.buy_count_after_accept,
                    "buy_count_after_deny": journey07.buy_count_after_deny,
                    "buy_count_after_freeze": journey07.buy_count_after_freeze,
                    "buy_count_after_cap": journey07.buy_count_after_cap,
                    "proposed_price": journey07.proposed_price,
                    "freeze_reason": journey07.freeze_reason,
                    "cap_reason": journey07.cap_reason,
                    "checks": [c.get("id") for c in e2e07_checks + pay_invs_t22],
                    "invariants": ["INV-PAY-001", "INV-PAY-002"],
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                        "make e2e-02",
                        "make e2e-03",
                        "make e2e-04",
                        "make e2e-05",
                        "make e2e-06",
                        "make e2e-07",
                        "make e2e-09",
                    ],
                    "artifacts": [
                        "artifacts/test/task-22/report.json",
                        "artifacts/test/task-22/verification.json",
                        "artifacts/test/e2e-07/verification.json",
                        "artifacts/test/e2e-07/purchases.json",
                        "artifacts/test/e2e-07/approvals.json",
                        "artifacts/test/e2e-07/audit.json",
                        "artifacts/test/e2e-07/outbound-messages.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return 0 if overall == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run personal-agent CI test layers")
    parser.add_argument(
        "--break-invariant",
        action="store_true",
        help="Enable broken_allow_all so INV-INGRESS-* must fail (fail-closed proof)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=str(ROOT / "artifacts" / "test" / "ci"),
        help="Output directory for report.json / report.md",
    )
    parser.add_argument(
        "--layer",
        choices=("all", "unit", "contract", "integration", "e2e"),
        default="all",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        layers: list[dict[str, Any]] = []
        if args.layer in ("all", "unit"):
            layers.append(run_unit(out_dir))
        if args.layer in ("all", "contract"):
            layers.append(run_contract(out_dir, broken_allow_all=args.break_invariant))
        if args.layer in ("all", "integration"):
            layers.append(run_integration(out_dir))
        if args.layer in ("all", "e2e"):
            # Fail-closed must not stomp happy-path E2E verification stamps.
            layers.append(
                run_e2e(out_dir, write_flow_artifacts=not args.break_invariant)
            )
        return aggregate(layers, out_dir, broken=args.break_invariant)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        write_report(
            out_dir,
            layer="test:ci",
            result="FAIL",
            checks=[{"id": "runner", "result": "FAIL", "detail": str(exc)}],
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
