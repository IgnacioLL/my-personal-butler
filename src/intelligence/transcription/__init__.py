"""Transcription intelligence: STT stub, TTS policy spy, audio→turn pipeline."""

from intelligence.transcription.pipeline import AudioTurnResult, TranscriptionPipeline
from intelligence.transcription.stt import (
    HARD_ACTION_TOKENS,
    SttOutcome,
    SttResult,
    SttStub,
    load_manifest,
    transcript_suggests_hard_action,
)
from intelligence.transcription.tts import TtsMode, TtsPolicySpy

__all__ = [
    "AudioTurnResult",
    "HARD_ACTION_TOKENS",
    "SttOutcome",
    "SttResult",
    "SttStub",
    "TranscriptionPipeline",
    "TtsMode",
    "TtsPolicySpy",
    "load_manifest",
    "transcript_suggests_hard_action",
]
