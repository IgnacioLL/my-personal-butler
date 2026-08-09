"""Mock WhatsApp transport — inbound injector + outbound catcher + side-effect ledger.

Harness double for Gateway WhatsApp channel. No live network. Used by INV-INGRESS-*
and Virtual User scaffolding. Audio path: STT stub → transcript turn or clarification
(INV-INGRESS-003).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from harness.outbound import OutboundMessageCatcher
from intelligence.transcription.pipeline import TranscriptionPipeline
from intelligence.transcription.stt import SttStub
from intelligence.transcription.tts import TtsMode, TtsPolicySpy
from policy.ingress import IngressDecision, evaluate_ingress

# Hard action tool names that must never fire from rejected / unclarified audio.
HARD_TOOL_NAMES = frozenset(
    {"buy", "book", "self_mod_apply", "policy_change", "transfer_money"}
)


@dataclass
class InboundWhatsAppMessage:
    """Injected inbound WhatsApp event (text or media placeholder)."""

    sender: str
    body: str = ""
    is_group: bool = False
    group_id: str | None = None
    message_id: str | None = None
    media_type: str | None = None  # None/"text" | "audio" | ...
    audio_fixture_id: str | None = None
    audio_path: str | None = None
    audio_bytes: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SideEffectCounters:
    """Prove non-allowlisted / group traffic produces zero agent side effects."""

    tool_calls: int = 0
    outbound_sends: int = 0
    hard_action_attempts: int = 0
    clarification_asks: int = 0
    stt_calls: int = 0
    transcript_turns: int = 0
    tts_speaks: int = 0

    @property
    def total(self) -> int:
        return self.tool_calls + self.outbound_sends + self.hard_action_attempts

    def snapshot(self) -> dict[str, int]:
        return {
            "tool_calls": self.tool_calls,
            "outbound_sends": self.outbound_sends,
            "hard_action_attempts": self.hard_action_attempts,
            "clarification_asks": self.clarification_asks,
            "stt_calls": self.stt_calls,
            "transcript_turns": self.transcript_turns,
            "tts_speaks": self.tts_speaks,
            "total": self.total,
        }

    def reset(self) -> None:
        self.tool_calls = 0
        self.outbound_sends = 0
        self.hard_action_attempts = 0
        self.clarification_asks = 0
        self.stt_calls = 0
        self.transcript_turns = 0
        self.tts_speaks = 0


@dataclass
class TransportTurnResult:
    allowed: bool
    reason: str
    decision: IngressDecision
    tool_calls: list[str] = field(default_factory=list)
    outbound_count: int = 0
    counters_delta: dict[str, int] = field(default_factory=dict)
    transcript: str | None = None
    clarification: str | None = None
    turn_body: str | None = None
    stt_outcome: str | None = None
    tts_spoken: bool = False
    inbound: InboundWhatsAppMessage | None = None


AgentHandler = Callable[
    ["MockWhatsAppTransport", InboundWhatsAppMessage, IngressDecision], list[str]
]


def default_agent_handler(
    transport: "MockWhatsAppTransport",
    msg: InboundWhatsAppMessage,
    decision: IngressDecision,
) -> list[str]:
    """Stub agent: one respond tool + outbound ack. Clarification already handled upstream."""
    tools: list[str] = []
    body = msg.body
    transport._record_tool("agent.respond")
    tools.append("agent.respond")
    reply = f"ack:{body}"
    transport._send_outbound(
        decision.normalized_sender or msg.sender,
        reply,
        kind="reply",
    )
    # Optional TTS when inbound was audio (policy spy).
    if msg.media_type == "audio":
        spoken = transport.pipeline.maybe_tts_reply(reply, inbound_was_audio=True)
        if spoken:
            transport.counters.tts_speaks += 1
            transport.last_tts_spoken = True
    return tools


class MockWhatsAppTransport:
    """Inbound injector + outbound catcher integration with side-effect counters."""

    def __init__(
        self,
        allowlist: list[str],
        catcher: OutboundMessageCatcher | None = None,
        *,
        groups_enabled: bool = False,
        broken_allow_all: bool = False,
        agent_handler: AgentHandler | None = None,
        stt_map: dict[str, str] | None = None,
        pipeline: TranscriptionPipeline | None = None,
        tts_mode: TtsMode | str = TtsMode.INBOUND,
    ) -> None:
        self.allowlist = list(allowlist)
        self.catcher = catcher if catcher is not None else OutboundMessageCatcher()
        self.groups_enabled = groups_enabled
        self.broken_allow_all = broken_allow_all
        self.agent_handler = agent_handler or default_agent_handler

        if pipeline is not None:
            self.pipeline = pipeline
        elif stt_map is not None:
            mode = TtsMode(tts_mode) if isinstance(tts_mode, str) else tts_mode
            self.pipeline = TranscriptionPipeline(
                stt=SttStub.from_map(stt_map),
                tts=TtsPolicySpy(mode=mode),
            )
        else:
            mode = TtsMode(tts_mode) if isinstance(tts_mode, str) else tts_mode
            self.pipeline = TranscriptionPipeline.from_fixtures(
                # default manifest under fixtures/audio/
            )
            self.pipeline.tts = TtsPolicySpy(mode=mode)

        # Back-compat: expose simple map view for tests that read .stt_map
        self.stt_map = dict(stt_map or {})
        self.counters = SideEffectCounters()
        self.tool_call_log: list[str] = []
        self.inbound_log: list[InboundWhatsAppMessage] = []
        self.last_clarification: str | None = None
        self.last_transcript: str | None = None
        self.last_turn_body: str | None = None
        self.last_stt_outcome: str | None = None
        self.last_tts_spoken: bool = False
        self._seen_message_ids: set[str] = set()

    def inject(self, msg: InboundWhatsAppMessage) -> TransportTurnResult:
        """Inject one inbound WhatsApp event through allowlist → STT (if audio) → agent."""
        if msg.message_id:
            if msg.message_id in self._seen_message_ids:
                decision = evaluate_ingress(
                    msg.sender,
                    self.allowlist,
                    is_group=msg.is_group,
                    groups_enabled=self.groups_enabled,
                    group_id=msg.group_id,
                    broken_allow_all=self.broken_allow_all,
                )
                return TransportTurnResult(
                    allowed=decision.allowed,
                    reason="duplicate_webhook",
                    decision=decision,
                    tool_calls=[],
                    outbound_count=0,
                    counters_delta={},
                    transcript=None,
                    clarification=None,
                    turn_body=None,
                    stt_outcome=None,
                    tts_spoken=False,
                    inbound=msg,
                )
            self._seen_message_ids.add(msg.message_id)

        self.inbound_log.append(msg)

        working = msg
        transcript: str | None = None
        turn_body: str | None = None
        clarification: str | None = None
        stt_outcome: str | None = None
        tts_spoken = False
        self.last_clarification = None
        self.last_tts_spoken = False

        before = self.counters.snapshot()

        # Audio must pass through STT before agent reasoning (INV-INGRESS-003).
        if msg.media_type == "audio":
            audio_result = self.pipeline.process_voice_note(
                msg.audio_fixture_id,
                path=msg.audio_path,
                audio_bytes=msg.audio_bytes,
            )
            self.counters.stt_calls += 1
            stt_outcome = audio_result.stt.outcome.value
            self.last_stt_outcome = stt_outcome
            transcript = audio_result.stt.transcript
            self.last_transcript = transcript

            decision = evaluate_ingress(
                msg.sender,
                self.allowlist,
                is_group=msg.is_group,
                groups_enabled=self.groups_enabled,
                group_id=msg.group_id,
                broken_allow_all=self.broken_allow_all,
            )
            if not decision.allowed:
                after = self.counters.snapshot()
                return TransportTurnResult(
                    allowed=False,
                    reason=decision.reason,
                    decision=decision,
                    tool_calls=[],
                    outbound_count=0,
                    counters_delta=_delta(before, after),
                    transcript=transcript,
                    clarification=None,
                    turn_body=None,
                    stt_outcome=stt_outcome,
                    tts_spoken=False,
                    inbound=msg,
                )

            if audio_result.is_clarification:
                clarification = audio_result.clarification or (
                    "Could not transcribe audio — please resend or type your request."
                )
                self.last_clarification = clarification
                self._record_tool("agent.clarify")
                self._send_outbound(
                    decision.normalized_sender or msg.sender,
                    clarification,
                    kind="clarification",
                )
                self.counters.clarification_asks += 1
                after = self.counters.snapshot()
                return TransportTurnResult(
                    allowed=True,
                    reason=decision.reason,
                    decision=decision,
                    tool_calls=["agent.clarify"],
                    outbound_count=1,
                    counters_delta=_delta(before, after),
                    transcript=transcript,
                    clarification=clarification,
                    turn_body=None,
                    stt_outcome=stt_outcome,
                    tts_spoken=False,
                    inbound=msg,
                )

            # Usable transcript → agent turn with auditable "[Audio] …" body.
            turn_body = audio_result.turn_body or (
                f"[Audio] {transcript}" if transcript else ""
            )
            self.last_turn_body = turn_body
            self.counters.transcript_turns += 1
            working = InboundWhatsAppMessage(
                sender=msg.sender,
                body=turn_body,
                is_group=msg.is_group,
                group_id=msg.group_id,
                message_id=msg.message_id,
                media_type="audio",
                audio_fixture_id=msg.audio_fixture_id,
                audio_path=msg.audio_path,
                audio_bytes=msg.audio_bytes,
                meta={**dict(msg.meta), "stt_outcome": stt_outcome},
            )

        decision = evaluate_ingress(
            working.sender,
            self.allowlist,
            is_group=working.is_group,
            groups_enabled=self.groups_enabled,
            group_id=working.group_id,
            broken_allow_all=self.broken_allow_all,
        )

        if not decision.allowed:
            after = self.counters.snapshot()
            return TransportTurnResult(
                allowed=False,
                reason=decision.reason,
                decision=decision,
                tool_calls=[],
                outbound_count=0,
                counters_delta=_delta(before, after),
                transcript=transcript,
                clarification=None,
                turn_body=turn_body,
                stt_outcome=stt_outcome,
                tts_spoken=False,
                inbound=msg,
            )

        tools = list(self.agent_handler(self, working, decision))
        tts_spoken = self.last_tts_spoken
        after = self.counters.snapshot()
        outbound_delta = after["outbound_sends"] - before["outbound_sends"]
        return TransportTurnResult(
            allowed=True,
            reason=decision.reason,
            decision=decision,
            tool_calls=tools,
            outbound_count=outbound_delta,
            counters_delta=_delta(before, after),
            transcript=transcript,
            clarification=self.last_clarification if "agent.clarify" in tools else None,
            turn_body=turn_body or working.body,
            stt_outcome=stt_outcome,
            tts_spoken=tts_spoken,
            inbound=msg,
        )

    def inject_text(
        self,
        sender: str,
        body: str,
        *,
        is_group: bool = False,
        group_id: str | None = None,
        message_id: str | None = None,
    ) -> TransportTurnResult:
        return self.inject(
            InboundWhatsAppMessage(
                sender=sender,
                body=body,
                is_group=is_group,
                group_id=group_id,
                message_id=message_id,
                media_type="text",
            )
        )

    def inject_audio(
        self,
        sender: str,
        *,
        audio_fixture_id: str | None = None,
        body: str = "",
        is_group: bool = False,
        group_id: str | None = None,
        audio_path: str | None = None,
        audio_bytes: int | None = None,
    ) -> TransportTurnResult:
        return self.inject(
            InboundWhatsAppMessage(
                sender=sender,
                body=body,
                is_group=is_group,
                group_id=group_id,
                media_type="audio",
                audio_fixture_id=audio_fixture_id,
                audio_path=audio_path,
                audio_bytes=audio_bytes,
            )
        )

    def attempt_hard_tool(self, name: str, payload: dict[str, Any] | None = None) -> bool:
        """Record a hard-tool attempt; only succeeds on an already-allowed path.

        Used by adversarial tests to prove rejected ingress cannot invoke buy/book.
        Callers must only invoke this from inside an allowed agent_handler.
        """
        del payload  # harness ledger only
        self.counters.hard_action_attempts += 1
        if name in HARD_TOOL_NAMES:
            self._record_tool(name)
            return True
        return False

    def _record_tool(self, name: str) -> None:
        self.tool_call_log.append(name)
        self.counters.tool_calls += 1

    def _send_outbound(self, to: str, body: str, **meta: Any) -> None:
        self.catcher.send("whatsapp", to, body, **meta)
        self.counters.outbound_sends += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "allowlist": list(self.allowlist),
            "groups_enabled": self.groups_enabled,
            "counters": self.counters.snapshot(),
            "tool_call_log": list(self.tool_call_log),
            "inbound_count": len(self.inbound_log),
            "outbound": self.catcher.to_list(),
            "pipeline": self.pipeline.snapshot(),
        }

    def reset_effects(self) -> None:
        self.counters.reset()
        self.tool_call_log.clear()
        self.catcher.clear()
        self.last_clarification = None
        self.last_transcript = None
        self.last_turn_body = None
        self.last_stt_outcome = None
        self.last_tts_spoken = False
        self.pipeline.tts.reset()
        self.pipeline.stt.calls.clear()
        self._seen_message_ids.clear()


def _delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {k: after[k] - before.get(k, 0) for k in after}
