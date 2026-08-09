"""Natural-language booking request parsing (WhatsApp text / STT turns).

Enough for E2E-06: “Book a haircut next week afternoon.”
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

EXPECTED_E2E06_UTTERANCE = "Book a haircut next week afternoon."

_BOOK_PREFIX = re.compile(
    r"^\s*(?:\[Audio\]\s*)?book\b",
    re.IGNORECASE,
)
_HAIRCUT_RE = re.compile(r"\bhaircut\b|\bbarber\b|\btrim\b", re.IGNORECASE)
_NEXT_WEEK_RE = re.compile(r"\bnext\s+week\b", re.IGNORECASE)
_THIS_WEEK_RE = re.compile(r"\bthis\s+week\b", re.IGNORECASE)
_MORNING_RE = re.compile(r"\bmorning\b", re.IGNORECASE)
_AFTERNOON_RE = re.compile(r"\bafternoon\b", re.IGNORECASE)
_SERVICE_RE = re.compile(
    r"\bbook\s+(?:a|an|the)?\s*(?P<service>[\w\s-]{2,40?}?)(?:\s+(?:next|this|on|for)\b|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedBookingRequest:
    service: str
    period: str  # morning | afternoon | any
    window_start: datetime
    window_end: datetime
    timezone: str
    raw: str


def _resolve_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"unknown timezone: {name!r}") from exc


def _local_now(now: datetime, tz: ZoneInfo) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def looks_like_booking(text: str) -> bool:
    body = (text or "").strip()
    if not _BOOK_PREFIX.search(body):
        return False
    # Avoid colliding with "Book a flight" later — v1 is haircut/barber/spa-ish.
    return bool(_HAIRCUT_RE.search(body) or re.search(r"\b(spa|massage|nails)\b", body, re.I))


def parse_booking(
    utterance: str,
    *,
    now: datetime,
    timezone: str = "UTC",
) -> ParsedBookingRequest:
    """Parse booking NL into a calendar search window + service."""
    tz = _resolve_tz(timezone)
    now_local = _local_now(now, tz)
    body = (utterance or "").strip()
    if not looks_like_booking(body):
        raise ValueError("not_a_booking_request")

    service = "haircut"
    m = _SERVICE_RE.search(body)
    if m:
        raw_svc = (m.group("service") or "").strip().lower()
        raw_svc = re.sub(r"\s+", " ", raw_svc)
        if raw_svc and raw_svc not in {"a", "an", "the"}:
            service = raw_svc

    period = "any"
    if _AFTERNOON_RE.search(body):
        period = "afternoon"
    elif _MORNING_RE.search(body):
        period = "morning"

    # Default window: next week Mon–Sun (local).
    days_until_monday = (7 - now_local.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    if _THIS_WEEK_RE.search(body) and not _NEXT_WEEK_RE.search(body):
        # Remaining days of current week including today.
        week_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        days_to_sunday = 6 - now_local.weekday()
        week_end = week_start + timedelta(days=days_to_sunday + 1)
    else:
        # next week (also default when unspecified for E2E-06)
        week_start = (now_local + timedelta(days=days_until_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=7)

    if period == "morning":
        window_start = week_start.replace(hour=9, minute=0)
        # Prefer morning band; still search whole week mornings via portal filter.
        window_end = week_end
    elif period == "afternoon":
        window_start = week_start.replace(hour=12, minute=0)
        window_end = week_end
    else:
        window_start = week_start.replace(hour=9, minute=0)
        window_end = week_end

    return ParsedBookingRequest(
        service=service,
        period=period,
        window_start=window_start,
        window_end=window_end,
        timezone=timezone,
        raw=body,
    )
