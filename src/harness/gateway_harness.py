"""Harness-friendly Gateway wrapper with reboot simulation (E2E-10 prep)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.clock import FakeClock
from harness.gateway_profile import gateway_data_paths, load_gateway_profile
from policy.action_gateway import ActionGateway


@dataclass
class GatewayHarness:
    """Minimal always-on Gateway double for CI — durable approvals on disk."""

    clock: FakeClock
    profile: dict[str, Any] = field(default_factory=load_gateway_profile)
    gateway: ActionGateway = field(init=False)
    _approvals_path: Path = field(init=False)

    def __post_init__(self) -> None:
        paths = gateway_data_paths(self.profile)
        self._approvals_path = paths["approvals"]
        self.gateway = ActionGateway(clock=self.clock, approvals_path=self._approvals_path)

    @property
    def approvals_path(self) -> Path:
        return self._approvals_path

    def restart(self) -> "GatewayHarness":
        """Simulate Gateway process restart — new handle, same clock + disk state."""
        return GatewayHarness(clock=self.clock, profile=self.profile)

    def data_paths(self) -> dict[str, Path]:
        return gateway_data_paths(self.profile)
