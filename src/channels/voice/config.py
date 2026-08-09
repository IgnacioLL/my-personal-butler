"""Production voice-call configuration loader (Twilio / Telnyx / mock).

Live carrier calls are placed by the OpenClaw ``@openclaw/voice-call`` plugin.
This module loads the production templates + env overlays for validation,
outbound allowlist checks, and harness factory wiring. No Twilio/Telnyx SDKs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PLUGIN_PATH = (
    _REPO_ROOT / "config" / "production" / "openclaw.voice-call.json"
)
DEFAULT_POLICY_PATH = (
    _REPO_ROOT / "config" / "production" / "call-mode.policy.json"
)

VALID_PROVIDERS = frozenset({"mock", "twilio", "telnyx"})


@dataclass(frozen=True)
class VoiceCallConfig:
    """Resolved production voice-call settings (secrets never required in CI)."""

    provider: str = "mock"
    from_number: str = ""
    to_number: str = ""
    outbound_allowlist: frozenset[str] = field(default_factory=frozenset)
    public_url: str = ""
    webhook_path: str = "/voice/webhook"
    webhook_port: int = 3334
    inbound_policy: str = "disabled"
    skip_signature_verification: bool = False
    max_duration_seconds: int = 300
    max_concurrent_calls: int = 1
    after_call_whatsapp_summary: bool = True
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    telnyx_api_key: str = ""
    telnyx_connection_id: str = ""
    telnyx_public_key: str = ""
    source: str = "defaults"

    def is_live(self) -> bool:
        return self.provider in {"twilio", "telnyx"}

    def outbound_allowed(self, number: str) -> bool:
        """True if *number* may be dialed (empty allowlist → only to_number)."""
        target = (number or "").strip()
        if not target:
            return False
        if self.outbound_allowlist:
            return target in self.outbound_allowlist
        if self.to_number:
            return target == self.to_number
        # Mock/CI without configured operator: allow any non-empty destination.
        return self.provider == "mock"

    def missing_live_credentials(self) -> list[str]:
        """Keys missing for a live provider (empty when mock or complete)."""
        if self.provider == "mock":
            return []
        missing: list[str] = []
        if not self.from_number:
            missing.append("fromNumber")
        if not self.to_number:
            missing.append("toNumber")
        if not self.public_url:
            missing.append("publicUrl")
        if self.provider == "twilio":
            if not self.twilio_account_sid:
                missing.append("twilio.accountSid")
            if not self.twilio_auth_token:
                missing.append("twilio.authToken")
        elif self.provider == "telnyx":
            if not self.telnyx_api_key:
                missing.append("telnyx.apiKey")
            if not self.telnyx_connection_id:
                missing.append("telnyx.connectionId")
            if not self.telnyx_public_key and not self.skip_signature_verification:
                missing.append("telnyx.publicKey")
        if self.skip_signature_verification and self.is_live():
            missing.append("skipSignatureVerification_must_be_false_in_production")
        return missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "from_number": self.from_number,
            "to_number": self.to_number,
            "outbound_allowlist": sorted(self.outbound_allowlist),
            "public_url": self.public_url,
            "webhook_path": self.webhook_path,
            "webhook_port": self.webhook_port,
            "inbound_policy": self.inbound_policy,
            "skip_signature_verification": self.skip_signature_verification,
            "max_duration_seconds": self.max_duration_seconds,
            "max_concurrent_calls": self.max_concurrent_calls,
            "after_call_whatsapp_summary": self.after_call_whatsapp_summary,
            "is_live": self.is_live(),
            "source": self.source,
            # Never dump secrets — only presence flags.
            "twilio_account_sid_set": bool(self.twilio_account_sid),
            "twilio_auth_token_set": bool(self.twilio_auth_token),
            "telnyx_api_key_set": bool(self.telnyx_api_key),
            "telnyx_connection_id_set": bool(self.telnyx_connection_id),
            "telnyx_public_key_set": bool(self.telnyx_public_key),
        }


def _parse_allowlist(raw: str | list[Any] | None) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, list):
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    parts = [p.strip() for p in str(raw).split(",")]
    return frozenset(p for p in parts if p)


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_plugin_fragment(path: Path | str | None = None) -> dict[str, Any]:
    """Load ``openclaw.voice-call.json`` fragment (no secrets)."""
    target = Path(path) if path is not None else DEFAULT_PLUGIN_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"voice-call plugin fragment must be an object: {target}")
    return data


def voice_call_config_from_plugin(
    fragment: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
) -> VoiceCallConfig:
    """Build :class:`VoiceCallConfig` from plugin fragment + optional env overlay."""
    environ = env if env is not None else dict(os.environ)
    entries = (fragment.get("plugins") or {}).get("entries") or {}
    vc = (entries.get("voice-call") or {}).get("config") or {}
    butler = (fragment.get("personalButler") or {}).get("voiceCalls") or {}

    provider = (
        environ.get("VOICE_CALL_PROVIDER")
        or str(vc.get("provider") or "mock")
    ).strip().lower()
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"unsupported voice provider: {provider!r}")

    from_number = (
        environ.get("VOICE_CALL_FROM_NUMBER")
        or environ.get("TWILIO_FROM_NUMBER")
        or str(vc.get("fromNumber") or "")
    ).strip()
    to_number = (
        environ.get("VOICE_CALL_TO_NUMBER") or str(vc.get("toNumber") or "")
    ).strip()

    allowlist = _parse_allowlist(environ.get("VOICE_CALL_OUTBOUND_ALLOWLIST"))
    if not allowlist:
        allowlist = _parse_allowlist(butler.get("outboundAllowlist"))
    if not allowlist and to_number:
        allowlist = frozenset({to_number})

    serve = vc.get("serve") or {}
    public_url = (
        environ.get("VOICE_CALL_PUBLIC_URL") or str(vc.get("publicUrl") or "")
    ).strip()
    webhook_path = (
        environ.get("VOICE_CALL_WEBHOOK_PATH")
        or str(serve.get("path") or "/voice/webhook")
    ).strip()
    port_raw = environ.get("VOICE_CALL_WEBHOOK_PORT") or serve.get("port") or 3334
    webhook_port = int(port_raw)

    inbound = (
        environ.get("VOICE_CALL_INBOUND_POLICY")
        or str(vc.get("inboundPolicy") or "disabled")
    ).strip()
    skip = _truthy(
        environ.get("VOICE_CALL_SKIP_SIGNATURE_VERIFICATION"),
        default=bool(vc.get("skipSignatureVerification") or False),
    )
    max_dur = int(
        environ.get("VOICE_CALL_MAX_DURATION_SECONDS")
        or vc.get("maxDurationSeconds")
        or 300
    )
    max_conc = int(
        environ.get("VOICE_CALL_MAX_CONCURRENT")
        or vc.get("maxConcurrentCalls")
        or 1
    )
    after = butler.get("afterCallWhatsAppSummary")
    if after is None:
        after = True

    twilio = vc.get("twilio") or {}
    telnyx = vc.get("telnyx") or {}

    return VoiceCallConfig(
        provider=provider,
        from_number=from_number,
        to_number=to_number,
        outbound_allowlist=allowlist,
        public_url=public_url,
        webhook_path=webhook_path,
        webhook_port=webhook_port,
        inbound_policy=inbound,
        skip_signature_verification=skip,
        max_duration_seconds=max_dur,
        max_concurrent_calls=max_conc,
        after_call_whatsapp_summary=bool(after),
        twilio_account_sid=(
            environ.get("TWILIO_ACCOUNT_SID") or str(twilio.get("accountSid") or "")
        ).strip(),
        twilio_auth_token=(
            environ.get("TWILIO_AUTH_TOKEN") or str(twilio.get("authToken") or "")
        ).strip(),
        telnyx_api_key=(
            environ.get("TELNYX_API_KEY") or str(telnyx.get("apiKey") or "")
        ).strip(),
        telnyx_connection_id=(
            environ.get("TELNYX_CONNECTION_ID")
            or str(telnyx.get("connectionId") or "")
        ).strip(),
        telnyx_public_key=(
            environ.get("TELNYX_PUBLIC_KEY") or str(telnyx.get("publicKey") or "")
        ).strip(),
        source=str(fragment.get("_meta", {}).get("task") or "plugin"),
    )


def load_voice_call_config(
    path: Path | str | None = None,
    *,
    env: dict[str, str] | None = None,
    force_mock: bool = False,
) -> VoiceCallConfig:
    """Load production voice-call config; *force_mock* for CI/harness."""
    environ = env if env is not None else dict(os.environ)
    if force_mock:
        environ = {**environ, "VOICE_CALL_PROVIDER": "mock"}
    fragment = load_plugin_fragment(path)
    return voice_call_config_from_plugin(fragment, env=environ)


def harness_mock_config(*, operator: str = "+15550001111") -> VoiceCallConfig:
    """CI-safe mock config pointing outbound allowlist at *operator*."""
    return VoiceCallConfig(
        provider="mock",
        from_number="+15550001234",
        to_number=operator,
        outbound_allowlist=frozenset({operator}),
        public_url="",
        webhook_path="/voice/webhook",
        webhook_port=3334,
        inbound_policy="disabled",
        skip_signature_verification=False,
        after_call_whatsapp_summary=True,
        source="harness_mock",
    )
