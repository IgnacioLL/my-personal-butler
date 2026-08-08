"""Test harness utilities (fake clock, outbound catcher, INV runner helpers).

OpenClaw-centric: these doubles sit beside Gateway skills/tools for CI; they are
not a custom agent runtime.
"""

from .clock import FakeClock
from .outbound import OutboundMessage, OutboundMessageCatcher

__all__ = [
    "FakeClock",
    "OutboundMessage",
    "OutboundMessageCatcher",
]
