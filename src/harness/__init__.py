"""Test harness utilities (fake clock, outbound catcher, INV runner helpers).

OpenClaw-centric: these doubles sit beside Gateway skills/tools for CI; they are
not a custom agent runtime.
"""

from .clock import FakeClock
from .outbound import OutboundMessage, OutboundMessageCatcher
from .whatsapp_transport import (
    InboundWhatsAppMessage,
    MockWhatsAppTransport,
    SideEffectCounters,
)

__all__ = [
    "FakeClock",
    "InboundWhatsAppMessage",
    "MockWhatsAppTransport",
    "OutboundMessage",
    "OutboundMessageCatcher",
    "SideEffectCounters",
]
