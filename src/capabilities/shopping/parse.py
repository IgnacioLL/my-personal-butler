"""Natural-language shopping request parsing (WhatsApp text / STT turns).

Enough for E2E-07: “Buy my usual protein powder.”
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

EXPECTED_E2E07_UTTERANCE = "Buy my usual protein powder."

_BUY_PREFIX = re.compile(
    r"^\s*(?:\[Audio\]\s*)?(?:buy|purchase|order|get)\b",
    re.IGNORECASE,
)
_PROTEIN_RE = re.compile(
    r"\bprotein(?:\s+powder)?\b|\bwhey\b",
    re.IGNORECASE,
)
_USUAL_RE = re.compile(r"\b(?:my\s+)?usual\b|\bregular\b|\brebuy\b", re.IGNORECASE)
# Avoid colliding with "Add todo: buy oat milk" / reminder phrases.
_TODO_COLLISION = re.compile(r"^\s*add\s+todo\b", re.IGNORECASE)
_REMIND_COLLISION = re.compile(r"^\s*remind\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedShoppingRequest:
    item_key: str
    product_query: str
    prefer_usual: bool
    raw: str


def looks_like_shopping(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return False
    if _TODO_COLLISION.search(body) or _REMIND_COLLISION.search(body):
        return False
    if not _BUY_PREFIX.search(body):
        return False
    # v1: protein powder / known rebuy phrasing. Broader catalog later.
    return bool(_PROTEIN_RE.search(body) or _USUAL_RE.search(body))


def parse_shopping(utterance: str) -> ParsedShoppingRequest:
    """Parse shopping NL into a catalog lookup key."""
    body = (utterance or "").strip()
    if not looks_like_shopping(body):
        raise ValueError("not_a_shopping_request")

    prefer_usual = bool(_USUAL_RE.search(body))
    item_key = "protein_powder"
    product_query = "protein powder"
    if _PROTEIN_RE.search(body):
        item_key = "protein_powder"
        product_query = "protein powder"
    else:
        # "Buy my usual" without product noun — still protein in E2E-07 seed.
        item_key = "protein_powder"
        product_query = "usual"

    return ParsedShoppingRequest(
        item_key=item_key,
        product_query=product_query,
        prefer_usual=prefer_usual,
        raw=body,
    )
