"""INV-APPR-005 — Call-mode sessions cannot invoke buy/book/self-mod-apply tools."""

from __future__ import annotations

from typing import Any

from channels.voice.allowlist import CALL_MODE_FORBIDDEN_TOOLS
from channels.voice.provider import MockVoiceProvider
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher

INV_ID = "INV-APPR-005"
DESCRIPTION = "Call-mode sessions cannot invoke buy/book/self-mod-apply tools"


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    _ = ctx
    clock = FakeClock()
    catcher = OutboundMessageCatcher()
    voice = MockVoiceProvider(catcher, clock, default_to="+15550001111")
    failures: list[str] = []

    session = voice.place_call(
        script="Calling about: morning stretch",
        reminder_id="rem-inv005",
    )
    if session.status != "active":
        failures.append(f"expected active call, got {session.status}")

    # Positive control: read-only tools remain available mid-call.
    read_ok = voice.invoke_tool(session.id, "calendar_read", {"day": "friday"})
    if not read_ok.ok:
        failures.append(f"calendar_read should be allowed mid-call ({read_ok.reason})")

    # INV-APPR-005: hard tools blocked; adapters never run (no side-effect counters here —
    # the call-mode gate refuses before any commerce/selfmod adapter is reached).
    for tool in sorted(CALL_MODE_FORBIDDEN_TOOLS):
        result = voice.invoke_tool(session.id, tool, {"item": tool})
        if result.ok:
            failures.append(f"{tool}: call-mode invoke succeeded (must be blocked)")
        if result.reason != "call_mode_forbidden_hard_action":
            failures.append(
                f"{tool}: expected call_mode_forbidden_hard_action, got {result.reason!r}"
            )
        if result.invocation.allowed:
            failures.append(f"{tool}: invocation.allowed unexpectedly True")

    forbidden = voice.forbidden_attempts()
    if len(forbidden) != len(CALL_MODE_FORBIDDEN_TOOLS):
        failures.append(
            f"forbidden attempt log size={len(forbidden)} "
            f"expected={len(CALL_MODE_FORBIDDEN_TOOLS)}"
        )
    if any(inv.allowed for inv in forbidden):
        failures.append("forbidden_attempts contains an allowed=True entry")

    # After-call summary still queues (orthogonal to allowlist, proves session lifecycle).
    ended = voice.end_call(session.id, outcome="inv_appr_005_probe")
    if not ended.summary_queued:
        failures.append("after-call WhatsApp summary was not queued")
    summaries = [
        m
        for m in catcher.messages
        if m.meta.get("kind") == "after_call_summary" and m.channel == "whatsapp"
    ]
    if len(summaries) != 1:
        failures.append(f"expected 1 after-call WhatsApp summary, got {len(summaries)}")

    # Ended session cannot invoke tools either.
    late = voice.invoke_tool(session.id, "buy", {"sku": "late"})
    if late.ok:
        failures.append("buy succeeded on ended call session")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            f"call-mode blocked {sorted(CALL_MODE_FORBIDDEN_TOOLS)}; "
            f"calendar_read allowed; after-call summary queued"
        ),
    }
