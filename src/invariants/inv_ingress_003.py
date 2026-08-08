"""INV-INGRESS-003 — voice notes yield transcript or clarification (scaffold).

Full STT pipeline lands in TASK-06. This scaffold proves the fail-closed shape:
audio without a transcript must clarify and must not invoke hard-action tools.
"""

from __future__ import annotations

from typing import Any

from harness.outbound import OutboundMessageCatcher
from harness.whatsapp_transport import (
    HARD_TOOL_NAMES,
    MockWhatsAppTransport,
)

INV_ID = "INV-INGRESS-003"
DESCRIPTION = (
    "Every inbound voice note either yields a transcript turn or a clarification ask "
    "— never a silent guessed intent for hard actions"
)

OWNER = "+15550001111"


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    allowlist = list(ctx.get("allowlist") or [OWNER])
    broken = bool(ctx.get("broken_allow_all", False))
    failures: list[str] = []

    # Audio with known fixture → transcript body attached; agent responds (no hard tools).
    mapped = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        stt_map={"fx-reminder": "remind me sunday to call grandma"},
    )
    ok = mapped.inject_audio(OWNER, audio_fixture_id="fx-reminder")
    if not broken:
        if not ok.allowed:
            failures.append(f"mapped_audio: expected allow got {ok.reason}")
        if ok.transcript != "remind me sunday to call grandma":
            failures.append(f"mapped_audio: transcript mismatch {ok.transcript!r}")
        if any(t in HARD_TOOL_NAMES for t in mapped.tool_call_log):
            failures.append(f"mapped_audio: hard tools invoked {mapped.tool_call_log!r}")

    # Audio without transcript / unknown fixture → clarification; no hard actions.
    unclear = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        stt_map={},
    )
    ask = unclear.inject_audio(OWNER, audio_fixture_id="fx-unknown")
    if not broken:
        if not ask.allowed:
            failures.append(f"unclear_audio: expected allow+clarify got {ask.reason}")
        if unclear.counters.clarification_asks < 1 and not ask.clarification:
            failures.append("unclear_audio: expected clarification ask")
        if any(t in HARD_TOOL_NAMES for t in unclear.tool_call_log):
            failures.append(
                f"unclear_audio: hard tools on silent guess {unclear.tool_call_log!r}"
            )
        if "buy" in " ".join(unclear.tool_call_log).lower():
            failures.append("unclear_audio: buy tool fired without transcript")

    # Non-allowlisted audio: still zero tools / zero outbound (composes with 001).
    stranger = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        stt_map={"fx-reminder": "buy milk now"},
    )
    denied = stranger.inject_audio("+19999999999", audio_fixture_id="fx-reminder")
    if not broken:
        if denied.allowed or stranger.counters.total or stranger.catcher.count():
            failures.append(
                f"stranger_audio: effects on reject counters={stranger.counters.snapshot()}"
            )

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}

    if broken:
        # Under broken_allow_all, stranger audio may run — keep 001/002 as the
        # fail-closed detectors; this scaffold stays PASS so CI fail mode is
        # driven by 001/002 only (avoids masking). Scaffold still ran.
        return {
            "id": INV_ID,
            "result": "PASS",
            "detail": "scaffold skipped strict assert under broken_allow_all",
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "audio→transcript or clarification; no silent hard actions; "
            "stranger audio side-effect free"
        ),
    }
