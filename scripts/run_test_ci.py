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
from datetime import timedelta
from pathlib import Path
from typing import Any

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
from harness.whatsapp_transport import MockWhatsAppTransport  # noqa: E402
from policy.action_gateway import ActionGateway  # noqa: E402
from policy.approvals import (  # noqa: E402
    ApprovalStatus,
    ApprovalTier,
    tier_for,
)
from policy.ingress import evaluate_ingress, normalize_sender  # noqa: E402
from intelligence.memory.secrets import MemorySecretsError, redact_secrets  # noqa: E402
from intelligence.memory.store import MemoryStore  # noqa: E402
from intelligence.transcription.pipeline import TranscriptionPipeline  # noqa: E402
from intelligence.transcription.stt import SttOutcome, SttStub, load_manifest  # noqa: E402
from intelligence.transcription.tts import TtsMode, TtsPolicySpy  # noqa: E402


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


def run_integration(out_dir: Path) -> dict[str, Any]:
    """Integration stubs — full Virtual User lands later; prove harness wiring."""
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
                    "artifacts/test/task-03/",
                    "artifacts/test/task-04/",
                    "artifacts/test/task-05/",
                    "artifacts/test/task-06/",
                ],
            },
        },
    )

    # Compact stamp for autonomous verification loops.
    stamp = {
        "claim": (
            "WhatsApp ingress + memory R/W + transcription: allowlisted DM only; "
            "voice notes → transcript or clarification (INV-INGRESS-003); "
            "hot profile + episodic persist; fail-closed on broken INV"
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
            "artifacts/test/task-03/verification.json",
            "artifacts/test/task-04/verification.json",
            "artifacts/test/task-05/verification.json",
            "artifacts/test/task-06/verification.json",
        ],
        "invariants": [
            c.get("id")
            for L in layers
            if L["layer"] == "contract"
            for c in L.get("checks", [])
        ],
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
        choices=("all", "unit", "contract", "integration"),
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
