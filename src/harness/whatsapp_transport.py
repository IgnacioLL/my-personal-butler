"""Mock WhatsApp transport — inbound injector + outbound catcher + side-effect ledger.

Harness double for Gateway WhatsApp channel. No live network. Used by INV-INGRESS-*
and Virtual User scaffolding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from harness.outbound import OutboundMessageCatcher
from policy.ingress import IngressDecision, evaluate_ingress

# Hard action tool names that must never fire from rejected ingress (INV-INGRESS-003 scaffold).
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
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SideEffectCounters:
    """Prove non-allowlisted / group traffic produces zero agent side effects."""

    tool_calls: int = 0
    outbound_sends: int = 0
    hard_action_attempts: int = 0
    clarification_asks: int = 0

    @property
    def total(self) -> int:
        return self.tool_calls + self.outbound_sends + self.hard_action_attempts

    def snapshot(self) -> dict[str, int]:
        return {
            "tool_calls": self.tool_calls,
            "outbound_sends": self.outbound_sends,
            "hard_action_attempts": self.hard_action_attempts,
            "clarification_asks": self.clarification_asks,
            "total": self.total,
        }

    def reset(self) -> None:
        self.tool_calls = 0
        self.outbound_sends = 0
        self.hard_action_attempts = 0
        self.clarification_asks = 0


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
    inbound: InboundWhatsAppMessage | None = None


AgentHandler = Callable[["MockWhatsAppTransport", InboundWhatsAppMessage, IngressDecision], list[str]]


def default_agent_handler(
    transport: "MockWhatsAppTransport",
    msg: InboundWhatsAppMessage,
    decision: IngressDecision,
) -> list[str]:
    """Stub agent: one respond tool + outbound ack. Audio without transcript → clarify."""
    tools: list[str] = []

    if msg.media_type == "audio" and not msg.body.strip():
        # INV-INGRESS-003 scaffold: never silently guess hard intent from mute audio.
        clarification = "Could not transcribe audio — please resend or type your request."
        transport._record_tool("agent.clarify")
        tools.append("agent.clarify")
        transport._send_outbound(
            decision.normalized_sender or msg.sender,
            clarification,
            kind="clarification",
        )
        transport.counters.clarification_asks += 1
        transport.last_clarification = clarification
        return tools

    body = msg.body
    transport._record_tool("agent.respond")
    tools.append("agent.respond")
    transport._send_outbound(
        decision.normalized_sender or msg.sender,
        f"ack:{body}",
        kind="reply",
    )
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
    ) -> None:
        self.allowlist = list(allowlist)
        self.catcher = catcher if catcher is not None else OutboundMessageCatcher()
        self.groups_enabled = groups_enabled
        self.broken_allow_all = broken_allow_all
        self.agent_handler = agent_handler or default_agent_handler
        self.stt_map = dict(stt_map or {})
        self.counters = SideEffectCounters()
        self.tool_call_log: list[str] = []
        self.inbound_log: list[InboundWhatsAppMessage] = []
        self.last_clarification: str | None = None
        self.last_transcript: str | None = None

    def inject(self, msg: InboundWhatsAppMessage) -> TransportTurnResult:
        """Inject one inbound WhatsApp event through allowlist → agent stub."""
        self.inbound_log.append(msg)

        # Optional STT for audio fixtures (TASK-06 will deepen; scaffold for 003).
        working = msg
        transcript: str | None = None
        if msg.media_type == "audio" and msg.audio_fixture_id:
            transcript = self.stt_map.get(msg.audio_fixture_id)
            if transcript is not None:
                working = InboundWhatsAppMessage(
                    sender=msg.sender,
                    body=transcript,
                    is_group=msg.is_group,
                    group_id=msg.group_id,
                    message_id=msg.message_id,
                    media_type="audio",
                    audio_fixture_id=msg.audio_fixture_id,
                    meta=dict(msg.meta),
                )
                self.last_transcript = transcript

        before = self.counters.snapshot()
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
                inbound=msg,
            )

        tools = list(self.agent_handler(self, working, decision))
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
    ) -> TransportTurnResult:
        return self.inject(
            InboundWhatsAppMessage(
                sender=sender,
                body=body,
                is_group=is_group,
                group_id=group_id,
                media_type="audio",
                audio_fixture_id=audio_fixture_id,
            )
        )

    def attempt_hard_tool(self, name: str, payload: dict[str, Any] | None = None) -> bool:
        """Record a hard-tool attempt; only succeeds on an already-allowed path.

        Used by adversarial tests to prove rejected ingress cannot invoke buy/book.
        Callers must only invoke this from inside an allowed agent_handler.
        """
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
        }

    def reset_effects(self) -> None:
        self.counters.reset()
        self.tool_call_log.clear()
        self.catcher.clear()
        self.last_clarification = None
        self.last_transcript = None


def _delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {k: after[k] - before[k] for k in after}
