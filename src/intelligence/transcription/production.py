"""Production STT/TTS provider config (OpenClaw media + inbound TTS).

Additive to the harness fixture path. CI continues to use ``SttStub`` /
``TtsPolicySpy``; this module loads and validates production fragments only —
no live HTTP / OpenAI calls.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from intelligence.transcription.tts import TtsMode


class SttProviderKind(str, Enum):
    """Which STT backend the runtime should use."""

    FIXTURE = "fixture"  # harness / CI — SttStub
    OPENAI = "openai"  # production OpenClaw media path
    WHISPER_CLI = "whisper_cli"  # optional local CLI fallback entry


PRIMARY_STT_MODEL = "gpt-4o-transcribe"
FALLBACK_STT_MODEL = "gpt-4o-mini-transcribe"
PRIMARY_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "alloy"
DEFAULT_TTS_AUTO = "inbound"

# OpenClaw messages.tts.auto values ↔ harness TtsMode.
_OPENCLAW_TTS_AUTO_TO_MODE: dict[str, TtsMode] = {
    "off": TtsMode.NEVER,
    "never": TtsMode.NEVER,
    "inbound": TtsMode.INBOUND,
    "always": TtsMode.ALWAYS,
    "tagged": TtsMode.NEVER,  # tagged has no harness twin; treat as off for spies
}


def repo_root() -> Path:
    # src/intelligence/transcription/production.py → repo root
    return Path(__file__).resolve().parents[3]


def default_voice_config_path() -> Path:
    return repo_root() / "config" / "production" / "openclaw.voice.json"


def default_whisper_fallback_path() -> Path:
    return (
        repo_root()
        / "config"
        / "production"
        / "openclaw.voice.whisper-fallback.json"
    )


def default_voice_env_example_path() -> Path:
    return repo_root() / "config" / "production" / "voice.env.example"


def resolve_stt_provider_kind(
    *,
    env: Mapping[str, str] | None = None,
) -> SttProviderKind:
    """Select STT backend from env. Default is fixture (CI-safe)."""
    source = env if env is not None else os.environ
    raw = (source.get("STT_PROVIDER") or SttProviderKind.FIXTURE.value).strip().lower()
    if raw in {"openai", "production", "prod"}:
        return SttProviderKind.OPENAI
    if raw in {"whisper", "whisper_cli", "whisper-cli"}:
        return SttProviderKind.WHISPER_CLI
    return SttProviderKind.FIXTURE


@dataclass(frozen=True)
class SttModelEntry:
    provider: str | None = None
    model: str | None = None
    entry_type: str | None = None  # "cli" for Whisper fallback
    command: str | None = None
    args: tuple[str, ...] = ()
    timeout_seconds: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, hash=False)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SttModelEntry":
        args_raw = raw.get("args") or []
        args = tuple(str(a) for a in args_raw) if isinstance(args_raw, list) else ()
        return cls(
            provider=(str(raw["provider"]) if raw.get("provider") is not None else None),
            model=(str(raw["model"]) if raw.get("model") is not None else None),
            entry_type=(str(raw["type"]) if raw.get("type") is not None else None),
            command=(str(raw["command"]) if raw.get("command") is not None else None),
            args=args,
            timeout_seconds=(
                int(raw["timeoutSeconds"])
                if raw.get("timeoutSeconds") is not None
                else None
            ),
            raw=dict(raw),
        )

    @property
    def is_openai(self) -> bool:
        return (self.provider or "").lower() == "openai" and bool(self.model)

    @property
    def is_whisper_cli(self) -> bool:
        return (self.entry_type or "").lower() == "cli" and (self.command or "") == "whisper"


@dataclass(frozen=True)
class ProductionTtsConfig:
    auto: str
    provider: str
    model: str
    voice: str
    mode: str = "final"
    max_text_length: int = 4000
    timeout_ms: int = 30000
    providers: dict[str, Any] = field(default_factory=dict, hash=False)

    @property
    def harness_mode(self) -> TtsMode:
        return _OPENCLAW_TTS_AUTO_TO_MODE.get(self.auto.lower(), TtsMode.INBOUND)

    def is_inbound(self) -> bool:
        return self.auto.lower() == DEFAULT_TTS_AUTO


@dataclass(frozen=True)
class ProductionVoiceConfig:
    """Validated production voice fragment (STT chain + inbound TTS)."""

    stt_enabled: bool
    stt_max_bytes: int
    stt_timeout_seconds: int
    stt_models: tuple[SttModelEntry, ...]
    tts: ProductionTtsConfig
    echo_transcript: bool = False
    source_path: str = ""
    raw: dict[str, Any] = field(default_factory=dict, hash=False)

    @property
    def primary_stt_model(self) -> str | None:
        for entry in self.stt_models:
            if entry.is_openai and entry.model:
                return entry.model
        return None

    @property
    def openai_stt_models(self) -> list[str]:
        return [e.model for e in self.stt_models if e.is_openai and e.model]

    def openclaw_merge_fragment(self) -> dict[str, Any]:
        """Return tools+messages only (safe to deep-merge into openclaw.json)."""
        out: dict[str, Any] = {}
        if "tools" in self.raw:
            out["tools"] = self.raw["tools"]
        if "messages" in self.raw:
            out["messages"] = self.raw["messages"]
        return out


class ProductionVoiceConfigError(ValueError):
    """Raised when a production voice fragment fails structural validation."""


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProductionVoiceConfigError(f"expected object in {path}")
    return data


def load_production_voice_config(
    path: Path | None = None,
) -> ProductionVoiceConfig:
    """Load and structurally validate ``openclaw.voice.json``."""
    cfg_path = path or default_voice_config_path()
    raw = _load_json(cfg_path)
    return parse_production_voice_config(raw, source_path=str(cfg_path))


def parse_production_voice_config(
    raw: Mapping[str, Any],
    *,
    source_path: str = "",
) -> ProductionVoiceConfig:
    tools = raw.get("tools")
    if not isinstance(tools, dict):
        raise ProductionVoiceConfigError("missing tools object")
    media = tools.get("media")
    if not isinstance(media, dict):
        raise ProductionVoiceConfigError("missing tools.media object")
    audio = media.get("audio")
    if not isinstance(audio, dict):
        raise ProductionVoiceConfigError("missing tools.media.audio object")

    enabled = bool(audio.get("enabled", False))
    if not enabled:
        raise ProductionVoiceConfigError("tools.media.audio.enabled must be true")

    models_raw = audio.get("models")
    if not isinstance(models_raw, list) or not models_raw:
        raise ProductionVoiceConfigError("tools.media.audio.models must be a non-empty list")

    models = tuple(SttModelEntry.from_dict(m) for m in models_raw if isinstance(m, dict))
    openai_models = [m for m in models if m.is_openai]
    if not openai_models:
        raise ProductionVoiceConfigError("expected at least one OpenAI STT model entry")
    primary = openai_models[0].model
    if primary != PRIMARY_STT_MODEL:
        raise ProductionVoiceConfigError(
            f"primary STT model must be {PRIMARY_STT_MODEL!r}, got {primary!r}"
        )
    model_ids = [m.model for m in openai_models if m.model]
    if FALLBACK_STT_MODEL not in model_ids:
        raise ProductionVoiceConfigError(
            f"expected secondary STT model {FALLBACK_STT_MODEL!r} in chain"
        )

    messages = raw.get("messages")
    if not isinstance(messages, dict):
        raise ProductionVoiceConfigError("missing messages object")
    tts_raw = messages.get("tts")
    if not isinstance(tts_raw, dict):
        raise ProductionVoiceConfigError("missing messages.tts object")

    auto = str(tts_raw.get("auto") or "").strip().lower()
    if auto != DEFAULT_TTS_AUTO:
        raise ProductionVoiceConfigError(
            f"messages.tts.auto must be {DEFAULT_TTS_AUTO!r} for WhatsApp inbound voice"
        )
    provider = str(tts_raw.get("provider") or "openai").strip().lower()
    providers = tts_raw.get("providers") if isinstance(tts_raw.get("providers"), dict) else {}
    openai_tts = providers.get("openai") if isinstance(providers.get("openai"), dict) else {}
    # Legacy flat block still accepted by OpenClaw migrations.
    if not openai_tts and isinstance(tts_raw.get("openai"), dict):
        openai_tts = tts_raw["openai"]
    tts_model = str(openai_tts.get("model") or PRIMARY_TTS_MODEL)
    tts_voice = str(openai_tts.get("voice") or DEFAULT_TTS_VOICE)

    tts = ProductionTtsConfig(
        auto=auto,
        provider=provider,
        model=tts_model,
        voice=tts_voice,
        mode=str(tts_raw.get("mode") or "final"),
        max_text_length=int(tts_raw.get("maxTextLength") or 4000),
        timeout_ms=int(tts_raw.get("timeoutMs") or 30000),
        providers=dict(providers),
    )
    if tts.provider != "openai":
        raise ProductionVoiceConfigError("messages.tts.provider must be 'openai' for v1")
    if tts.model != PRIMARY_TTS_MODEL:
        raise ProductionVoiceConfigError(
            f"TTS model must be {PRIMARY_TTS_MODEL!r}, got {tts.model!r}"
        )
    if not tts.is_inbound() or tts.harness_mode is not TtsMode.INBOUND:
        raise ProductionVoiceConfigError("TTS must map to inbound harness mode")

    max_bytes = int(audio.get("maxBytes") or 0)
    if max_bytes <= 0:
        raise ProductionVoiceConfigError("tools.media.audio.maxBytes must be > 0")

    return ProductionVoiceConfig(
        stt_enabled=True,
        stt_max_bytes=max_bytes,
        stt_timeout_seconds=int(audio.get("timeoutSeconds") or 120),
        stt_models=models,
        tts=tts,
        echo_transcript=bool(audio.get("echoTranscript", False)),
        source_path=source_path,
        raw=dict(raw),
    )


def load_whisper_fallback_entry(
    path: Path | None = None,
) -> SttModelEntry:
    """Load the optional Whisper CLI model entry (append-only)."""
    fb_path = path or default_whisper_fallback_path()
    raw = _load_json(fb_path)
    try:
        models = raw["tools"]["media"]["audio"]["models"]
    except (KeyError, TypeError) as exc:
        raise ProductionVoiceConfigError(
            "whisper fallback missing tools.media.audio.models"
        ) from exc
    if not isinstance(models, list) or not models:
        raise ProductionVoiceConfigError("whisper fallback models list empty")
    entry = SttModelEntry.from_dict(models[0])
    if not entry.is_whisper_cli:
        raise ProductionVoiceConfigError(
            "whisper fallback entry must be type=cli command=whisper"
        )
    return entry


def validate_production_voice_tree(root: Path | None = None) -> dict[str, Any]:
    """Structural check used by CI — no network.

    Ensures production fragments exist, parse, and keep fixture STT as the
    default provider selection when ``STT_PROVIDER`` is unset.
    """
    base = root or repo_root()
    voice_path = base / "config" / "production" / "openclaw.voice.json"
    whisper_path = (
        base / "config" / "production" / "openclaw.voice.whisper-fallback.json"
    )
    env_example = base / "config" / "production" / "voice.env.example"
    readme = base / "config" / "production" / "README.md"
    docs = base / "docs" / "production-voice.md"

    missing = [
        str(p)
        for p in (voice_path, whisper_path, env_example, readme, docs)
        if not p.is_file()
    ]
    if missing:
        raise ProductionVoiceConfigError(f"missing production voice files: {missing}")

    cfg = load_production_voice_config(voice_path)
    whisper = load_whisper_fallback_entry(whisper_path)
    env_text = env_example.read_text(encoding="utf-8")
    if "OPENAI_API_KEY" not in env_text:
        raise ProductionVoiceConfigError("voice.env.example missing OPENAI_API_KEY")

    # Default provider must remain fixture so CI never hits live STT.
    default_kind = resolve_stt_provider_kind(env={})
    if default_kind is not SttProviderKind.FIXTURE:
        raise ProductionVoiceConfigError("default STT_PROVIDER must resolve to fixture")

    fragment = cfg.openclaw_merge_fragment()
    return {
        "voice_config": str(voice_path),
        "primary_stt": cfg.primary_stt_model,
        "openai_stt_models": cfg.openai_stt_models,
        "tts_auto": cfg.tts.auto,
        "tts_model": cfg.tts.model,
        "tts_harness_mode": cfg.tts.harness_mode.value,
        "whisper_cli": whisper.command,
        "default_stt_provider": default_kind.value,
        "fragment_keys": sorted(fragment.keys()),
        "env_example": str(env_example),
        "docs": str(docs),
    }


def production_voice_snapshot(root: Path | None = None) -> dict[str, Any]:
    """JSON-serializable snapshot for artifacts / CI details."""
    try:
        return {"ok": True, **validate_production_voice_tree(root)}
    except ProductionVoiceConfigError as exc:
        return {"ok": False, "error": str(exc)}
