"""Voice channel doubles — mock outbound call provider + call-mode allowlist."""

from channels.voice.allowlist import (
    CALL_MODE_ALLOWED_TOOLS,
    CALL_MODE_FORBIDDEN_TOOLS,
    call_mode_block_reason,
    is_call_mode_allowed,
)
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
    "ToolInvocation",
    "ToolInvokeResult",
    "call_mode_block_reason",
    "is_call_mode_allowed",
]
