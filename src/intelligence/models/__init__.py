"""Models routing stubs: Luna default, Terra/Sol escalation (harness-only)."""

from intelligence.models.roles import IntentKind, ModelRole
from intelligence.models.router import RoutingDecision, RoutingSignals, route
from intelligence.models.stubs import ChatModelStub, ModelStubRegistry, StubCompletion

__all__ = [
    "ChatModelStub",
    "IntentKind",
    "ModelRole",
    "ModelStubRegistry",
    "RoutingDecision",
    "RoutingSignals",
    "route",
    "StubCompletion",
]
