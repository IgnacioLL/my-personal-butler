"""WhatsApp ingress allowlist — DM allowlist only; groups off by default.

Hardened for TASK-03: normalize sender ids, fail closed on empty allowlist,
treat group_id / group JIDs as group traffic, resist trivial spoof forms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Zero-width / bidi / BOM / soft hyphen — common spoof padding.
_INVISIBLE = re.compile(
    "[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad\u2060\u2066\u2067\u2068\u2069]"
)
_GROUP_JID_HINTS = ("@g.us", "@broadcast", "group:")


@dataclass(frozen=True)
class IngressDecision:
    allowed: bool
    reason: str
    normalized_sender: str = ""
    is_group: bool = False


def normalize_sender(sender: str | None) -> str:
    """Canonicalize a WhatsApp sender id for allowlist comparison.

    Strips surrounding whitespace and invisible/bidi characters. Does **not**
    invent a leading '+' or rewrite JIDs — fail closed on format mismatch.
    """
    if sender is None:
        return ""
    text = str(sender).strip()
    text = _INVISIBLE.sub("", text)
    return text.strip()


def looks_like_group_sender(sender: str) -> bool:
    lowered = sender.lower()
    return any(hint in lowered for hint in _GROUP_JID_HINTS)


def is_group_traffic(
    *,
    is_group: bool = False,
    group_id: str | None = None,
    sender: str = "",
) -> bool:
    """True when the inbound event is group/broadcast traffic.

    Adversarial coverage: group_id set without is_group flag, or group JIDs
    presented as the sender field.
    """
    if is_group:
        return True
    if group_id is not None and str(group_id).strip():
        return True
    if sender and looks_like_group_sender(sender):
        return True
    return False


def is_sender_allowed(
    sender: str,
    allowlist: Iterable[str],
    *,
    is_group: bool = False,
    groups_enabled: bool = False,
    group_id: str | None = None,
) -> bool:
    return evaluate_ingress(
        sender,
        allowlist,
        is_group=is_group,
        groups_enabled=groups_enabled,
        group_id=group_id,
    ).allowed


def evaluate_ingress(
    sender: str,
    allowlist: Iterable[str],
    *,
    is_group: bool = False,
    groups_enabled: bool = False,
    group_id: str | None = None,
    broken_allow_all: bool = False,
) -> IngressDecision:
    """Decide whether an inbound WhatsApp message may enter the agent.

    When broken_allow_all=True (fail-closed proof only), every sender is allowed —
    INV-INGRESS-* must catch that and fail CI.
    """
    normalized = normalize_sender(sender)

    if broken_allow_all:
        return IngressDecision(
            allowed=True,
            reason="broken_allow_all",
            normalized_sender=normalized,
            is_group=is_group_traffic(
                is_group=is_group, group_id=group_id, sender=normalized
            ),
        )

    group = is_group_traffic(
        is_group=is_group, group_id=group_id, sender=normalized
    )
    if group and not groups_enabled:
        return IngressDecision(
            allowed=False,
            reason="groups_disabled",
            normalized_sender=normalized,
            is_group=True,
        )

    if not normalized:
        return IngressDecision(
            allowed=False,
            reason="empty_sender",
            normalized_sender="",
            is_group=group,
        )

    allowed = {
        normalize_sender(s)
        for s in allowlist
        if s is not None and normalize_sender(str(s))
    }
    if not allowed:
        return IngressDecision(
            allowed=False,
            reason="empty_allowlist",
            normalized_sender=normalized,
            is_group=group,
        )

    if normalized in allowed:
        return IngressDecision(
            allowed=True,
            reason="allowlisted_dm" if not group else "allowlisted_group",
            normalized_sender=normalized,
            is_group=group,
        )

    return IngressDecision(
        allowed=False,
        reason="sender_not_allowlisted",
        normalized_sender=normalized,
        is_group=group,
    )
