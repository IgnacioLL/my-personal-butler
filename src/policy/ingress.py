"""WhatsApp ingress allowlist — DM allowlist only; groups off by default.

Full INV-INGRESS coverage lands in TASK-03; this stub is enough for T0 contract hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class IngressDecision:
    allowed: bool
    reason: str


def is_sender_allowed(
    sender: str,
    allowlist: Iterable[str],
    *,
    is_group: bool = False,
    groups_enabled: bool = False,
) -> bool:
    return evaluate_ingress(
        sender,
        allowlist,
        is_group=is_group,
        groups_enabled=groups_enabled,
    ).allowed


def evaluate_ingress(
    sender: str,
    allowlist: Iterable[str],
    *,
    is_group: bool = False,
    groups_enabled: bool = False,
    broken_allow_all: bool = False,
) -> IngressDecision:
    """Decide whether an inbound WhatsApp message may enter the agent.

    When broken_allow_all=True (fail-closed proof only), every sender is allowed —
    INV-INGRESS-* must catch that and fail CI.
    """
    if broken_allow_all:
        return IngressDecision(allowed=True, reason="broken_allow_all")

    if is_group and not groups_enabled:
        return IngressDecision(allowed=False, reason="groups_disabled")

    allowed = {s.strip() for s in allowlist if s and str(s).strip()}
    if sender in allowed:
        return IngressDecision(allowed=True, reason="allowlisted_dm")
    return IngressDecision(allowed=False, reason="sender_not_allowlisted")
