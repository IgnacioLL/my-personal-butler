"""Transcription intelligence: STT stub, TTS policy spy, audio→turn pipeline.

Production OpenClaw STT/TTS fragments live under ``config/production/`` and are
loaded via ``production`` (structural only — CI keeps ``SttStub``).
"""

from intelligence.transcription.pipeline import AudioTurnResult, TranscriptionPipeline
from intelligence.transcription.production import (
    FALLBACK_STT_MODEL,
    PRIMARY_STT_MODEL,
    PRIMARY_TTS_MODEL,
    ProductionTtsConfig,
    ProductionVoiceConfig,
    ProductionVoiceConfigError,
    SttProviderKind,
    load_production_voice_config,
    resolve_stt_provider_kind,
    validate_production_voice_tree,
)
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
    "FALLBACK_STT_MODEL",
    "HARD_ACTION_TOKENS",
    "PRIMARY_STT_MODEL",
    "PRIMARY_TTS_MODEL",
    "ProductionTtsConfig",
    "ProductionVoiceConfig",
    "ProductionVoiceConfigError",
    "SttOutcome",
    "SttProviderKind",
    "SttResult",
    "SttStub",
    "TranscriptionPipeline",
    "TtsMode",
    "TtsPolicySpy",
    "load_manifest",
    "load_production_voice_config",
    "resolve_stt_provider_kind",
    "transcript_suggests_hard_action",
    "validate_production_voice_tree",
]
