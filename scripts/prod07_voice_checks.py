"""PROD-07 Twilio/Telnyx voice-call production unit checks.

Imported by scripts/run_test_ci.py so parallel PROD agents editing that file
do not clobber voice production gates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from channels.voice.config import load_plugin_fragment, load_voice_call_config
from channels.voice.production import ProductionVoiceProvider, build_voice_provider
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.call_mode import (
    PRODUCTION_POLICY_PATH,
    SKILL_POLICY_PATH,
    gate_tool,
    load_call_mode_policy,
    policy_matches_allowlist,
)


def run_prod07_voice_unit_checks(root: Path | None = None) -> list[dict[str, Any]]:
    """Production templates, INV-APPR-005 policy sync, outbound allowlist, after-call WA."""
    checks: list[dict[str, Any]] = []
    base = root if root is not None else Path(__file__).resolve().parents[1]
    owner = "+15550005678"
    other = "+15559999999"

    plugin_path = base / "config" / "production" / "openclaw.voice-call.json"
    env_path = base / "config" / "production" / "voice-call.env.example"
    skill_policy = base / "src" / "skills" / "voice-calls" / "policy.json"
    skill_md = base / "src" / "skills" / "voice-calls" / "SKILL.md"
    runbook = base / "docs" / "voice-calls.md"

    files_ok = all(
        p.is_file() and p.stat().st_size > 0
        for p in (
            plugin_path,
            env_path,
            skill_policy,
            skill_md,
            runbook,
            PRODUCTION_POLICY_PATH,
        )
    )
    checks.append(
        {
            "id": "unit.voice.prod07_templates_present",
            "result": "PASS" if files_ok else "FAIL",
            "detail": (
                f"plugin={plugin_path.exists()} env={env_path.exists()} "
                f"skill_policy={skill_policy.exists()} runbook={runbook.exists()}"
            ),
        }
    )

    fragment = load_plugin_fragment(plugin_path)
    cfg = load_voice_call_config(
        plugin_path,
        env={
            "VOICE_CALL_PROVIDER": "mock",
            "VOICE_CALL_TO_NUMBER": owner,
            "VOICE_CALL_OUTBOUND_ALLOWLIST": owner,
        },
        force_mock=True,
    )
    vc_cfg = (
        ((fragment.get("plugins") or {}).get("entries") or {})
        .get("voice-call", {})
        .get("config")
        or {}
    )
    fragment_ok = (
        cfg.provider == "mock"
        and cfg.to_number == owner
        and cfg.outbound_allowed(owner)
        and not cfg.outbound_allowed(other)
        and cfg.after_call_whatsapp_summary is True
        and str(vc_cfg.get("serve", {}).get("path") or "") == "/voice/webhook"
        and "publicUrl" in vc_cfg
        and str(vc_cfg.get("inboundPolicy") or "") == "disabled"
    )
    checks.append(
        {
            "id": "unit.voice.prod07_config_webhook_allowlist",
            "result": "PASS" if fragment_ok else "FAIL",
            "detail": (
                f"provider={cfg.provider} to={cfg.to_number} "
                f"allow={sorted(cfg.outbound_allowlist)} "
                f"webhook={vc_cfg.get('publicUrl')}"
            ),
        }
    )

    skill_mismatches = policy_matches_allowlist(load_call_mode_policy(SKILL_POLICY_PATH))
    prod_mismatches = policy_matches_allowlist(
        load_call_mode_policy(PRODUCTION_POLICY_PATH)
    )
    gate_ok = (
        gate_tool("buy", call_mode_active=True) == "call_mode_forbidden_hard_action"
        and gate_tool("book", call_mode_active=True) == "call_mode_forbidden_hard_action"
        and gate_tool("self_mod_apply", call_mode_active=True)
        == "call_mode_forbidden_hard_action"
        and gate_tool("memory_read", call_mode_active=True) is None
        and gate_tool("buy", call_mode_active=False) is None
        and not skill_mismatches
        and not prod_mismatches
    )
    checks.append(
        {
            "id": "unit.voice.prod07_inv_appr_005_policy",
            "result": "PASS" if gate_ok else "FAIL",
            "detail": (
                f"skill_mismatches={skill_mismatches} "
                f"prod_mismatches={prod_mismatches}"
            ),
        }
    )

    clock = FakeClock()
    catcher = OutboundMessageCatcher()
    prod = build_voice_provider(catcher, clock, cfg)
    assert isinstance(prod, ProductionVoiceProvider)
    blocked = False
    try:
        prod.place_call(to=other, script="Calling about: leak")
    except PermissionError as exc:
        blocked = "outbound_not_allowlisted" in str(exc)
    session = prod.place_call(to=owner, script="Calling about: morning stretch")
    buy = prod.invoke_tool(session.id, "buy", {"sku": "x"})
    read = prod.invoke_tool(session.id, "todo_read", {})
    ended = prod.end_call(session.id, outcome="prod07_ok")
    summaries = [
        m
        for m in catcher.messages
        if m.meta.get("kind") == "after_call_summary" and m.channel == "whatsapp"
    ]
    prod_ok = (
        blocked
        and len(prod.rejected_outbound) == 1
        and read.ok
        and (not buy.ok)
        and buy.reason == "call_mode_forbidden_hard_action"
        and ended.summary_queued
        and len(summaries) == 1
        and "morning stretch" in (summaries[0].body or "")
    )
    checks.append(
        {
            "id": "unit.voice.prod07_provider_allowlist_and_summary",
            "result": "PASS" if prod_ok else "FAIL",
            "detail": (
                f"blocked_other={blocked} buy={buy.reason} "
                f"summaries={len(summaries)} rejected={len(prod.rejected_outbound)}"
            ),
        }
    )

    live_cfg = load_voice_call_config(
        plugin_path,
        env={
            "VOICE_CALL_PROVIDER": "twilio",
            "VOICE_CALL_FROM_NUMBER": "+15550001234",
            "VOICE_CALL_TO_NUMBER": owner,
            "VOICE_CALL_PUBLIC_URL": "https://gateway.example.com/voice/webhook",
            "TWILIO_ACCOUNT_SID": "ACtest",
            "TWILIO_AUTH_TOKEN": "secret",
            "VOICE_CALL_SKIP_SIGNATURE_VERIFICATION": "1",
        },
    )
    missing = live_cfg.missing_live_credentials()
    skip_guard = "skipSignatureVerification_must_be_false_in_production" in missing
    checks.append(
        {
            "id": "unit.voice.prod07_live_skip_signature_guard",
            "result": "PASS" if skip_guard else "FAIL",
            "detail": f"missing={missing}",
        }
    )
    return checks
