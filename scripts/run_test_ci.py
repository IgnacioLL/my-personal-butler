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
    VirtualUser,
    run_e2e_01,
    run_e2e_03,
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
from capabilities.todos.parse import looks_like_todo_add, parse_todo  # noqa: E402
from capabilities.todos.service import TodoService  # noqa: E402
from capabilities.todos.store import TodoSource, TodoStatus, TodoStore, normalize_title  # noqa: E402
from channels.android.approvals import AndroidApprovalInboxApi  # noqa: E402
from channels.android.projection import AndroidProjectionApi  # noqa: E402


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
    checks.extend(_run_todo_unit_checks())
    checks.extend(_run_android_approval_unit_checks())
    checks.extend(_run_calendar_unit_checks(ROOT))

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
    """Gate-tagged E2E flows (ci-gates.md). E2E-01 + E2E-03 Virtual User journeys."""
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

    # Mirror a compact layer report under ci/e2e for aggregate layout.
    layer_dir = out_dir / "e2e"
    result = "PASS" if journey01.ok and journey03.ok else "FAIL"
    write_report(
        layer_dir,
        layer="e2e",
        result=result,
        checks=checks,
        extra={
            "gate_flows": ["E2E-01", "E2E-03"],
            "e2e_01_artifacts": "artifacts/test/e2e-01/",
            "e2e_03_artifacts": "artifacts/test/e2e-03/",
            "harness": "VirtualUser",
        },
    )
    return {
        "layer": "e2e",
        "result": result,
        "checks": checks,
        "flows": ["E2E-01", "E2E-03"],
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
    checks.extend(_run_todo_integration_checks(ROOT))
    checks.extend(_run_android_approval_integration_checks(ROOT))
    checks.extend(_run_calendar_integration_checks(ROOT))

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
                    "artifacts/test/e2e-03/",
                    "artifacts/test/task-03/",
                    "artifacts/test/task-04/",
                    "artifacts/test/task-05/",
                    "artifacts/test/task-06/",
                    "artifacts/test/task-07/",
                    "artifacts/test/task-09/",
                    "artifacts/test/task-10/",
                    "artifacts/test/task-11/",
                    "artifacts/test/task-13/",
                ],
            },
        },
    )

    # Compact stamp for autonomous verification loops.
    stamp = {
        "claim": (
            "WhatsApp ingress + memory R/W + transcription + reminders/habits + "
            "E2E-01 voice reminder + E2E-03 todo sync gates: allowlisted DM; "
            "voice→transcript/clarify; Auto reminder/todo create; Android projection "
            "equality; calendar soft-confirm (INV-APPR-003); fail-closed on broken INV"
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
            "artifacts/test/e2e-03/verification.json",
            "artifacts/test/task-03/verification.json",
            "artifacts/test/task-04/verification.json",
            "artifacts/test/task-05/verification.json",
            "artifacts/test/task-06/verification.json",
            "artifacts/test/task-07/verification.json",
            "artifacts/test/task-09/verification.json",
            "artifacts/test/task-10/verification.json",
            "artifacts/test/task-11/verification.json",
            "artifacts/test/task-13/verification.json",
        ],
        "invariants": [
            c.get("id")
            for L in layers
            if L["layer"] == "contract"
            for c in L.get("checks", [])
        ],
        "gate_e2e": ["E2E-01", "E2E-03"],
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
