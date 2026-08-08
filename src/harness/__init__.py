"""Test harness utilities (fake clock, outbound catcher, INV runner helpers).

OpenClaw-centric: these doubles sit beside Gateway skills/tools for CI; they are
not a custom agent runtime.

Import VirtualUser from harness.virtual_user directly — keeping it out of this
package __init__ avoids circular imports with capabilities that need FakeClock.
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
