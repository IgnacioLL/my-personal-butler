"""STT stub: fixture map audio id/path → transcript (+ error/unclear cases).

Harness-only. No live STT providers. Deterministic for INV-INGRESS-003 and E2E-01.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

# Words that imply a hard action; low-confidence hits must clarify (never silent guess).
HARD_ACTION_TOKENS = frozenset(
    {
        "buy",
        "purchase",
        "order",
        "book",
        "transfer",
        "pay",
        "self-mod",
        "self_mod",
        "patch",
        "deploy",
    }
)


class SttOutcome(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    GARBAGE = "garbage"
    LOW_CONFIDENCE = "low_confidence"
    OVERSIZE = "oversize"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AudioClipFixture:
    id: str
    path: str
    outcome: SttOutcome
    expected_transcript: str | None = None
    confidence: float = 0.0
    language: str = "en"
    bytes: int | None = None
    duration_sec: float | None = None
    clarification: str | None = None
    hard_action_hint: bool = False
    echo_transcript: bool = False
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AudioClipFixture":
        outcome_raw = str(raw.get("outcome") or SttOutcome.UNKNOWN.value)
        try:
            outcome = SttOutcome(outcome_raw)
        except ValueError:
            outcome = SttOutcome.UNKNOWN
        return cls(
            id=str(raw["id"]),
            path=str(raw.get("path") or ""),
            outcome=outcome,
            expected_transcript=raw.get("expected_transcript"),
            confidence=float(raw.get("confidence") or 0.0),
            language=str(raw.get("language") or "en"),
            bytes=raw.get("bytes"),
            duration_sec=raw.get("duration_sec"),
            clarification=raw.get("clarification"),
            hard_action_hint=bool(raw.get("hard_action_hint")),
            echo_transcript=bool(raw.get("echo_transcript")),
            notes=str(raw.get("notes") or ""),
        )


@dataclass
class SttResult:
    """Result of transcribing one inbound voice note."""

    fixture_id: str
    outcome: SttOutcome
    transcript: str | None
    confidence: float
    clarification_needed: bool
    clarification_message: str | None = None
    turn_body: str | None = None  # "[Audio] <transcript>" when usable
    echo_transcript: bool = False
    hard_action_hint: bool = False
    language: str = "en"
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """True when the agent may treat this as a normal user turn."""
        return (
            not self.clarification_needed
            and self.outcome == SttOutcome.OK
            and bool((self.transcript or "").strip())
        )


DEFAULT_CLARIFICATION = (
    "Could not transcribe audio — please resend as a short voice note or type your request."
)


def default_manifest_path() -> Path:
    # src/intelligence/transcription/stt.py → repo root
    return (
        Path(__file__).resolve().parents[3] / "fixtures" / "audio" / "manifest.json"
    )


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or default_manifest_path()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "clips" not in data:
        raise ValueError(f"invalid audio manifest: {manifest_path}")
    return data


def transcript_suggests_hard_action(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in HARD_ACTION_TOKENS)


class SttStub:
    """Fixture-backed STT: map audio id/path → expected transcript or error case."""

    def __init__(
        self,
        *,
        manifest_path: Path | None = None,
        manifest: Mapping[str, Any] | None = None,
        overrides: Mapping[str, str] | None = None,
        max_bytes: int | None = None,
        clarification_default: str | None = None,
    ) -> None:
        if manifest is not None:
            data = dict(manifest)
        else:
            data = load_manifest(manifest_path)

        self.max_bytes = int(
            max_bytes if max_bytes is not None else data.get("max_bytes") or 1024
        )
        self.clarification_default = (
            clarification_default
            or str(data.get("clarification_default") or DEFAULT_CLARIFICATION)
        )
        self._by_id: dict[str, AudioClipFixture] = {}
        self._by_path: dict[str, AudioClipFixture] = {}
        for raw in data.get("clips") or []:
            clip = AudioClipFixture.from_dict(raw)
            self._by_id[clip.id] = clip
            if clip.path:
                self._by_path[clip.path] = clip
                self._by_path[Path(clip.path).name] = clip

        # Optional inline overrides (legacy stt_map / test injection).
        self._overrides: dict[str, str] = dict(overrides or {})
        self.calls: list[dict[str, Any]] = []

    @classmethod
    def from_map(
        cls,
        stt_map: Mapping[str, str],
        *,
        clarification_default: str | None = None,
    ) -> "SttStub":
        """Build a stub from a simple id→transcript map (TASK-03 scaffold compat)."""
        clips = []
        for fid, transcript in stt_map.items():
            clips.append(
                {
                    "id": fid,
                    "path": f"{fid}.ogg",
                    "expected_transcript": transcript,
                    "outcome": "ok" if (transcript or "").strip() else "empty",
                    "confidence": 0.9 if (transcript or "").strip() else 0.0,
                }
            )
        return cls(
            manifest={"clips": clips, "max_bytes": 1024},
            clarification_default=clarification_default,
        )

    def resolve_clip(
        self, audio_fixture_id: str | None = None, *, path: str | None = None
    ) -> AudioClipFixture | None:
        if audio_fixture_id and audio_fixture_id in self._by_id:
            return self._by_id[audio_fixture_id]
        if path:
            if path in self._by_path:
                return self._by_path[path]
            name = Path(path).name
            if name in self._by_path:
                return self._by_path[name]
        if audio_fixture_id and audio_fixture_id in self._overrides:
            text = self._overrides[audio_fixture_id]
            return AudioClipFixture(
                id=audio_fixture_id,
                path=f"{audio_fixture_id}.ogg",
                outcome=SttOutcome.OK if text.strip() else SttOutcome.EMPTY,
                expected_transcript=text,
                confidence=0.9 if text.strip() else 0.0,
            )
        return None

    def transcribe(
        self,
        audio_fixture_id: str | None = None,
        *,
        path: str | None = None,
        audio_bytes: int | None = None,
    ) -> SttResult:
        """Transcribe one voice note by fixture id or path.

        Unknown fixtures and empty/garbage/oversize outcomes require clarification.
        Never invents intent — hard-action guesses stay blocked.
        """
        key = audio_fixture_id or path or ""
        clip = self.resolve_clip(audio_fixture_id, path=path)
        self.calls.append(
            {
                "fixture_id": audio_fixture_id,
                "path": path,
                "audio_bytes": audio_bytes,
                "resolved": clip.id if clip else None,
            }
        )

        if clip is None:
            return SttResult(
                fixture_id=key or "unknown",
                outcome=SttOutcome.UNKNOWN,
                transcript=None,
                confidence=0.0,
                clarification_needed=True,
                clarification_message=self.clarification_default,
                meta={"reason": "unknown_fixture"},
            )

        # Bound max size (manifest bytes or caller-supplied).
        size = audio_bytes if audio_bytes is not None else clip.bytes
        if size is not None and size > self.max_bytes:
            return SttResult(
                fixture_id=clip.id,
                outcome=SttOutcome.OVERSIZE,
                transcript=None,
                confidence=0.0,
                clarification_needed=True,
                clarification_message=(
                    clip.clarification
                    or "That voice note is too long or large — please send a shorter clip."
                ),
                meta={"bytes": size, "max_bytes": self.max_bytes},
            )

        if clip.outcome == SttOutcome.OVERSIZE:
            return SttResult(
                fixture_id=clip.id,
                outcome=SttOutcome.OVERSIZE,
                transcript=None,
                confidence=0.0,
                clarification_needed=True,
                clarification_message=(
                    clip.clarification
                    or "That voice note is too long or large — please send a shorter clip."
                ),
                meta={"bytes": size, "max_bytes": self.max_bytes},
            )

        transcript = clip.expected_transcript
        text = (transcript or "").strip()

        if clip.outcome in {SttOutcome.EMPTY, SttOutcome.ERROR} or not text:
            if clip.outcome == SttOutcome.OK and not text:
                outcome = SttOutcome.EMPTY
            else:
                outcome = (
                    clip.outcome
                    if clip.outcome != SttOutcome.OK
                    else SttOutcome.EMPTY
                )
            return SttResult(
                fixture_id=clip.id,
                outcome=outcome if outcome != SttOutcome.OK else SttOutcome.EMPTY,
                transcript=transcript if transcript is not None else "",
                confidence=clip.confidence,
                clarification_needed=True,
                clarification_message=clip.clarification or self.clarification_default,
                language=clip.language,
            )

        if clip.outcome == SttOutcome.GARBAGE:
            return SttResult(
                fixture_id=clip.id,
                outcome=SttOutcome.GARBAGE,
                transcript=text,
                confidence=clip.confidence,
                clarification_needed=True,
                clarification_message=clip.clarification or self.clarification_default,
                language=clip.language,
            )

        hard_hint = clip.hard_action_hint or transcript_suggests_hard_action(text)
        # Low confidence + hard-action language → echo + clarify (INV-INGRESS-003).
        if clip.outcome == SttOutcome.LOW_CONFIDENCE or (
            clip.confidence < 0.5 and hard_hint
        ):
            echo = clip.echo_transcript or hard_hint
            msg = clip.clarification
            if not msg:
                if echo:
                    msg = (
                        f'I heard: "{text}" — please confirm or rephrase '
                        "before I take any action."
                    )
                else:
                    msg = self.clarification_default
            return SttResult(
                fixture_id=clip.id,
                outcome=SttOutcome.LOW_CONFIDENCE,
                transcript=text,
                confidence=clip.confidence,
                clarification_needed=True,
                clarification_message=msg,
                turn_body=None,
                echo_transcript=echo,
                hard_action_hint=hard_hint,
                language=clip.language,
            )

        # Usable transcript turn.
        turn_body = f"[Audio] {text}"
        return SttResult(
            fixture_id=clip.id,
            outcome=SttOutcome.OK,
            transcript=text,
            confidence=clip.confidence,
            clarification_needed=False,
            clarification_message=None,
            turn_body=turn_body,
            echo_transcript=False,
            hard_action_hint=hard_hint,
            language=clip.language,
            meta={"path": clip.path},
        )

    def expected_transcript(self, fixture_id: str) -> str | None:
        clip = self._by_id.get(fixture_id)
        if clip is None:
            return self._overrides.get(fixture_id)
        return clip.expected_transcript

    def snapshot(self) -> dict[str, Any]:
        return {
            "clip_ids": sorted(self._by_id),
            "max_bytes": self.max_bytes,
            "call_count": len(self.calls),
            "calls": list(self.calls),
        }
