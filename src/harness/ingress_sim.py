"""WhatsApp-like ingress simulator for harness contract tests.

Wraps MockWhatsAppTransport (inbound injector + outbound catcher + counters).
Not a Gateway replacement — exercises allowlist + side-effect isolation + STT path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness.outbound import OutboundMessageCatcher
from harness.whatsapp_transport import (
    InboundWhatsAppMessage,
    MockWhatsAppTransport,
    TransportTurnResult,
)
from intelligence.transcription.pipeline import TranscriptionPipeline


@dataclass
class TurnResult:
    allowed: bool
    reason: str
    tool_calls: list[str] = field(default_factory=list)
    outbound_count: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    transcript: str | None = None
    clarification: str | None = None
    turn_body: str | None = None
    stt_outcome: str | None = None
    tts_spoken: bool = False


class IngressSimulator:
    """Route an inbound DM/group message through allowlist policy into stubs."""

    def __init__(
        self,
        allowlist: list[str],
        catcher: OutboundMessageCatcher | None = None,
        *,
        groups_enabled: bool = False,
        broken_allow_all: bool = False,
        stt_map: dict[str, str] | None = None,
        pipeline: TranscriptionPipeline | None = None,
        transport: MockWhatsAppTransport | None = None,
    ) -> None:
        if transport is not None:
            self.transport = transport
        else:
            self.transport = MockWhatsAppTransport(
                allowlist=list(allowlist),
                catcher=catcher if catcher is not None else OutboundMessageCatcher(),
                groups_enabled=groups_enabled,
                broken_allow_all=broken_allow_all,
                stt_map=stt_map,
                pipeline=pipeline,
            )
        self.allowlist = self.transport.allowlist
        self.catcher = self.transport.catcher
        self.groups_enabled = self.transport.groups_enabled
        self.broken_allow_all = self.transport.broken_allow_all

    @property
    def tool_calls(self) -> list[str]:
        return self.transport.tool_call_log

    @property
    def counters(self):
        return self.transport.counters

    @property
    def pipeline(self) -> TranscriptionPipeline:
        return self.transport.pipeline

    def handle(
        self,
        sender: str,
        body: str,
        *,
        is_group: bool = False,
        group_id: str | None = None,
        message_id: str | None = None,
        media_type: str | None = None,
        audio_fixture_id: str | None = None,
        audio_path: str | None = None,
    ) -> TurnResult:
        result = self.transport.inject(
            InboundWhatsAppMessage(
                sender=sender,
                body=body,
                is_group=is_group,
                group_id=group_id,
                message_id=message_id,
                media_type=media_type or ("audio" if audio_fixture_id else "text"),
                audio_fixture_id=audio_fixture_id,
                audio_path=audio_path,
            )
        )
        return self._to_turn(result)

    def handle_audio(
        self,
        sender: str,
        *,
        audio_fixture_id: str,
        is_group: bool = False,
        group_id: str | None = None,
    ) -> TurnResult:
        return self._to_turn(
            self.transport.inject_audio(
                sender,
                audio_fixture_id=audio_fixture_id,
                is_group=is_group,
                group_id=group_id,
            )
        )

    def inject(self, msg: InboundWhatsAppMessage) -> TurnResult:
        return self._to_turn(self.transport.inject(msg))

    def _to_turn(self, result: TransportTurnResult) -> TurnResult:
        return TurnResult(
            allowed=result.allowed,
            reason=result.reason,
            tool_calls=list(result.tool_calls),
            outbound_count=result.outbound_count,
            counters=dict(result.counters_delta),
            transcript=result.transcript,
            clarification=result.clarification,
            turn_body=result.turn_body,
            stt_outcome=result.stt_outcome,
            tts_spoken=result.tts_spoken,
        )

    def snapshot(self) -> dict[str, Any]:
        return self.transport.snapshot()
