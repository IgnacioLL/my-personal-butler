"""TTS policy hook — assert mode rules only (noop/spy). No real synthesis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TtsMode(str, Enum):
    """When WhatsApp may send a spoken reply."""

    NEVER = "never"
    INBOUND = "inbound"  # speak back only if the user spoke (preferred v1)
    ALWAYS = "always"


@dataclass
class TtsCall:
    text: str
    inbound_was_audio: bool
    spoken: bool
    reason: str


@dataclass
class TtsPolicySpy:
    """Noop TTS with call ledger for policy assertions.

    Preferred product mode is ``inbound``: only speak when inbound was audio.
    """

    mode: TtsMode = TtsMode.INBOUND
    calls: list[TtsCall] = field(default_factory=list)

    @property
    def speak_count(self) -> int:
        return sum(1 for c in self.calls if c.spoken)

    def should_speak(self, *, inbound_was_audio: bool) -> tuple[bool, str]:
        if self.mode is TtsMode.NEVER:
            return False, "mode_never"
        if self.mode is TtsMode.ALWAYS:
            return True, "mode_always"
        if self.mode is TtsMode.INBOUND:
            if inbound_was_audio:
                return True, "mode_inbound_audio"
            return False, "mode_inbound_text_skip"
        # Exhaustive: newly added TtsMode variants must be handled above.
        _exhaustive: never = self.mode
        raise AssertionError(f"unhandled TtsMode: {_exhaustive}")

    def maybe_speak(self, text: str, *, inbound_was_audio: bool) -> bool:
        allowed, reason = self.should_speak(inbound_was_audio=inbound_was_audio)
        spoken = bool(allowed and (text or "").strip())
        if allowed and not (text or "").strip():
            reason = "empty_text"
            spoken = False
        self.calls.append(
            TtsCall(
                text=text,
                inbound_was_audio=inbound_was_audio,
                spoken=spoken,
                reason=reason,
            )
        )
        return spoken

    def reset(self) -> None:
        self.calls.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "speak_count": self.speak_count,
            "calls": [
                {
                    "text": c.text,
                    "inbound_was_audio": c.inbound_was_audio,
                    "spoken": c.spoken,
                    "reason": c.reason,
                }
                for c in self.calls
            ],
        }
