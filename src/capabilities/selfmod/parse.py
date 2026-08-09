"""NL parse for self-mod intents (quiet hours / policy tweak)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

EXPECTED_E2E08_UTTERANCE = "Add quiet hours: no calls after 22:00."

_SELF_MOD_HINTS = (
    "quiet hours",
    "quiet-hours",
    "no calls after",
    "patch",
    "self-mod",
    "self mod",
    "edit the skill",
    "update the skill",
    "change the policy",
    "policy change",
    "raise spend cap",
    "approval matrix",
)

_QUIET_HOURS_RE = re.compile(
    r"quiet\s*hours|no\s+calls\s+after|never\s+calls?\s+after",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):?([0-5]\d)?\b")
_POLICY_RE = re.compile(
    r"policy\s+change|approval\s+matrix|spend\s+cap|kill[\s-]?switch",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedSelfModRequest:
    kind: str  # quiet_hours | policy_change | generic
    raw: str
    no_calls_after: Optional[str] = None
    intent_summary: str = ""


def looks_like_self_mod(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return any(h in lowered for h in _SELF_MOD_HINTS)


def parse_self_mod(text: str) -> ParsedSelfModRequest:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty_self_mod_utterance")

    if _POLICY_RE.search(raw) and not _QUIET_HOURS_RE.search(raw):
        return ParsedSelfModRequest(
            kind="policy_change",
            raw=raw,
            intent_summary=raw,
        )

    if _QUIET_HOURS_RE.search(raw) or looks_like_self_mod(raw):
        after = "22:00"
        m = re.search(
            r"(?:after|from)\s+(?:(2[0-3]|[01]?\d):([0-5]\d)|(2[0-3]|[01]?\d))\b",
            raw,
            re.IGNORECASE,
        )
        if m:
            if m.group(1) is not None:
                hour = int(m.group(1))
                minute = int(m.group(2) or "0")
            else:
                hour = int(m.group(3))
                minute = 0
            after = f"{hour:02d}:{minute:02d}"
        return ParsedSelfModRequest(
            kind="quiet_hours",
            raw=raw,
            no_calls_after=after,
            intent_summary=f"Enable quiet hours — no calls after {after}",
        )

    raise ValueError(f"unrecognized_self_mod:{raw!r}")
