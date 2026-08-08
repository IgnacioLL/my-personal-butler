"""WhatsApp audio → STT → turn pipeline (harness).

Every voice note becomes either:
  - a transcript user turn (``[Audio] <text>``), or
  - a clarification ask

Never silently guesses hard-action intent (INV-INGRESS-003).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from intelligence.transcription.stt import SttResult, SttStub
from intelligence.transcription.tts import TtsMode, TtsPolicySpy


@dataclass
class AudioTurnResult:
    """Outcome of the audio→turn pipeline before/alongside agent handling."""

    stt: SttResult
    kind: str  # "transcript_turn" | "clarification"
    turn_body: str | None = None
    clarification: str | None = None
    tts_spoken: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_transcript_turn(self) -> bool:
        return self.kind == "transcript_turn"

    @property
    def is_clarification(self) -> bool:
        return self.kind == "clarification"


@dataclass
class TranscriptionPipeline:
    """STT stub + optional TTS policy for WhatsApp voice notes."""

    stt: SttStub
    tts: TtsPolicySpy = field(default_factory=lambda: TtsPolicySpy(mode=TtsMode.INBOUND))

    @classmethod
    def from_fixtures(cls, **stt_kwargs: Any) -> "TranscriptionPipeline":
        return cls(stt=SttStub(**stt_kwargs))

    @classmethod
    def from_map(cls, stt_map: dict[str, str]) -> "TranscriptionPipeline":
        return cls(stt=SttStub.from_map(stt_map))

    def process_voice_note(
        self,
        audio_fixture_id: str | None = None,
        *,
        path: str | None = None,
        audio_bytes: int | None = None,
    ) -> AudioTurnResult:
        stt = self.stt.transcribe(
            audio_fixture_id, path=path, audio_bytes=audio_bytes
        )
        if stt.clarification_needed or not stt.usable:
            return AudioTurnResult(
                stt=stt,
                kind="clarification",
                turn_body=None,
                clarification=stt.clarification_message,
                meta={"outcome": stt.outcome.value},
            )
        return AudioTurnResult(
            stt=stt,
            kind="transcript_turn",
            turn_body=stt.turn_body,
            clarification=None,
            meta={"outcome": stt.outcome.value, "confidence": stt.confidence},
        )

    def maybe_tts_reply(self, reply_text: str, *, inbound_was_audio: bool) -> bool:
        return self.tts.maybe_speak(reply_text, inbound_was_audio=inbound_was_audio)

    def snapshot(self) -> dict[str, Any]:
        return {"stt": self.stt.snapshot(), "tts": self.tts.snapshot()}
