"""Voice channel — mock (CI) + production config/provider (Twilio/Telnyx)."""

from channels.voice.allowlist import (
    CALL_MODE_ALLOWED_TOOLS,
    CALL_MODE_FORBIDDEN_TOOLS,
    call_mode_block_reason,
    is_call_mode_allowed,
)
from channels.voice.config import (
    VoiceCallConfig,
    harness_mock_config,
    load_plugin_fragment,
    load_voice_call_config,
)
from channels.voice.production import ProductionVoiceProvider, build_voice_provider
from channels.voice.provider import (
    CallSession,
    MockVoiceProvider,
    ToolInvocation,
    ToolInvokeResult,
)

__all__ = [
    "CALL_MODE_ALLOWED_TOOLS",
    "CALL_MODE_FORBIDDEN_TOOLS",
    "CallSession",
    "MockVoiceProvider",
    "ProductionVoiceProvider",
    "ToolInvocation",
    "ToolInvokeResult",
    "VoiceCallConfig",
    "build_voice_provider",
    "call_mode_block_reason",
    "harness_mock_config",
    "is_call_mode_allowed",
    "load_plugin_fragment",
    "load_voice_call_config",
]
