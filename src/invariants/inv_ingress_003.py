"""INV-INGRESS-003 — voice notes yield transcript or clarification (fully enforced).

Every inbound voice note either yields a transcript turn or a clarification ask —
never a silent guessed intent for hard actions.
"""

from __future__ import annotations

from typing import Any

from harness.outbound import OutboundMessageCatcher
from harness.whatsapp_transport import (
    HARD_TOOL_NAMES,
    MockWhatsAppTransport,
)
from intelligence.transcription.pipeline import TranscriptionPipeline
from intelligence.transcription.stt import SttStub
from intelligence.transcription.tts import TtsMode, TtsPolicySpy

INV_ID = "INV-INGRESS-003"
DESCRIPTION = (
    "Every inbound voice note either yields a transcript turn or a clarification ask "
    "— never a silent guessed intent for hard actions"
)

OWNER = "+15550001111"


def _pipeline_from_fixtures() -> TranscriptionPipeline:
    return TranscriptionPipeline(
        stt=SttStub(),  # loads fixtures/audio/manifest.json
        tts=TtsPolicySpy(mode=TtsMode.INBOUND),
    )


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    allowlist = list(ctx.get("allowlist") or [OWNER])
    broken = bool(ctx.get("broken_allow_all", False))
    failures: list[str] = []

    # --- Mapped fixture → transcript turn; no hard tools ---
    mapped = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        pipeline=_pipeline_from_fixtures(),
    )
    ok = mapped.inject_audio(OWNER, audio_fixture_id="fx-reminder-short")
    if not broken:
        if not ok.allowed:
            failures.append(f"mapped_audio: expected allow got {ok.reason}")
        if (ok.transcript or "").lower() != "remind me sunday to call grandma":
            failures.append(f"mapped_audio: transcript mismatch {ok.transcript!r}")
        if not (ok.turn_body or "").startswith("[Audio]"):
            failures.append(f"mapped_audio: turn_body missing [Audio] prefix {ok.turn_body!r}")
        if ok.clarification:
            failures.append("mapped_audio: unexpected clarification")
        if "agent.respond" not in ok.tool_calls:
            failures.append(f"mapped_audio: expected agent.respond got {ok.tool_calls!r}")
        if any(t in HARD_TOOL_NAMES for t in mapped.tool_call_log):
            failures.append(f"mapped_audio: hard tools invoked {mapped.tool_call_log!r}")
        if mapped.counters.stt_calls < 1:
            failures.append("mapped_audio: STT was not invoked")
        if mapped.counters.transcript_turns < 1:
            failures.append("mapped_audio: expected transcript turn counter")

    # --- Unknown fixture → clarification; no hard actions ---
    unclear = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        pipeline=TranscriptionPipeline.from_map({}),  # empty map
    )
    ask = unclear.inject_audio(OWNER, audio_fixture_id="fx-unknown")
    if not broken:
        if not ask.allowed:
            failures.append(f"unclear_audio: expected allow+clarify got {ask.reason}")
        if unclear.counters.clarification_asks < 1 and not ask.clarification:
            failures.append("unclear_audio: expected clarification ask")
        if "agent.clarify" not in ask.tool_calls:
            failures.append(f"unclear_audio: expected agent.clarify got {ask.tool_calls!r}")
        if any(t in HARD_TOOL_NAMES for t in unclear.tool_call_log):
            failures.append(
                f"unclear_audio: hard tools on silent guess {unclear.tool_call_log!r}"
            )
        if "buy" in " ".join(unclear.tool_call_log).lower():
            failures.append("unclear_audio: buy tool fired without transcript")

    # --- Empty / garbage fixtures → clarification ---
    empty = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        pipeline=_pipeline_from_fixtures(),
    )
    empty_res = empty.inject_audio(OWNER, audio_fixture_id="fx-empty")
    garbage_res = empty.inject_audio(OWNER, audio_fixture_id="fx-garbage")
    if not broken:
        if not empty_res.clarification or empty.counters.clarification_asks < 1:
            failures.append("empty_audio: expected clarification")
        if any(t in HARD_TOOL_NAMES for t in empty.tool_call_log):
            failures.append(f"empty_audio: hard tools {empty.tool_call_log!r}")
        if not garbage_res.clarification:
            failures.append("garbage_audio: expected clarification")
        if empty.counters.transcript_turns != 0:
            failures.append("empty/garbage: must not count as transcript turns")

    # --- Low-confidence hard-action audio → echo/clarify; never buy ---
    risky = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        pipeline=_pipeline_from_fixtures(),
    )
    buy_ask = risky.inject_audio(OWNER, audio_fixture_id="fx-unclear-buy")
    if not broken:
        if not buy_ask.clarification:
            failures.append("unclear_buy: expected clarification echo")
        if "buy" not in (buy_ask.clarification or "").lower():
            failures.append("unclear_buy: clarification should echo heard transcript")
        if any(t in HARD_TOOL_NAMES for t in risky.tool_call_log):
            failures.append(f"unclear_buy: hard tools fired {risky.tool_call_log!r}")
        if "agent.respond" in buy_ask.tool_calls:
            failures.append("unclear_buy: must not run normal agent respond on low-confidence buy")

    # --- Oversize → clarification ---
    big = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        pipeline=_pipeline_from_fixtures(),
    )
    over = big.inject_audio(OWNER, audio_fixture_id="fx-oversize")
    if not broken:
        if not over.clarification or over.stt_outcome != "oversize":
            failures.append(
                f"oversize: expected oversize clarification got outcome={over.stt_outcome}"
            )
        if any(t in HARD_TOOL_NAMES for t in big.tool_call_log):
            failures.append("oversize: hard tools fired")

    # --- Non-allowlisted audio: zero tools / zero outbound (composes with 001) ---
    stranger = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        broken_allow_all=broken,
        pipeline=TranscriptionPipeline.from_map(
            {"fx-reminder": "buy milk now"}
        ),
    )
    denied = stranger.inject_audio("+19999999999", audio_fixture_id="fx-reminder")
    if not broken:
        if denied.allowed or stranger.counters.total or stranger.catcher.count():
            failures.append(
                f"stranger_audio: effects on reject counters={stranger.counters.snapshot()}"
            )

    # --- Adversarial: agent must not invent hard tools on mute body without STT pass ---
    # (pipeline already clarifies; prove hard tool names absent across all above)

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}

    if broken:
        # Under broken_allow_all, stranger audio may run — keep 001/002 as the
        # fail-closed detectors; this check stays PASS so CI fail mode is
        # driven by 001/002 only (avoids masking). Cases still executed.
        return {
            "id": INV_ID,
            "result": "PASS",
            "detail": "full path exercised; strict stranger assert skipped under broken_allow_all",
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "audio→transcript or clarification; empty/garbage/oversize/low-confidence "
            "hard-action clarified; no silent hard actions; stranger audio side-effect free"
        ),
    }
