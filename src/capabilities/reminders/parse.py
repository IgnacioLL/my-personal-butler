"""Natural-language reminder parsing for harness / E2E-01 transcripts.

Enough for: “Remind me Sunday at 18:00 to call grandma.”
Also covers tomorrow / every <weekday> recurring forms used in unit tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

WEEKDAY_NAMES: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_TIME_RE = re.compile(
    r"\b(?:at\s+)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)?\b",
    re.IGNORECASE,
)
_EVERY_RE = re.compile(r"\bevery\s+(?P<day>\w+)\b", re.IGNORECASE)
_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
_WEEKDAY_RE = re.compile(
    r"\b(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_REMIND_PREFIX = re.compile(
    r"^\s*(?:\[Audio\]\s*)?remind\s+me\b",
    re.IGNORECASE,
)
_TO_CLAUSE = re.compile(r"\bto\s+(?P<body>.+?)\s*[.!]?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedReminder:
    """Structured intent from a reminder utterance."""

    text: str
    kind: str  # "one_shot" | "recurring"
    timezone: str
    due_at: datetime
    weekday: Optional[int]
    hour: int
    minute: int
    body: str
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


def _parse_time(utterance: str, *, default_hour: int = 18, default_minute: int = 0) -> tuple[int, int]:
    match = _TIME_RE.search(utterance)
    if not match:
        return default_hour, default_minute
    hour = int(match.group("h"))
    minute = int(match.group("m") or 0)
    ampm = (match.group("ampm") or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise ValueError(f"invalid time in utterance: {utterance!r}")
    return hour, minute


def _extract_body(utterance: str) -> str:
    match = _TO_CLAUSE.search(utterance)
    if match:
        return match.group("body").strip().rstrip(".")
    # Fall back: strip remind-me / schedule preface.
    cleaned = _REMIND_PREFIX.sub("", utterance).strip()
    cleaned = _EVERY_RE.sub("", cleaned)
    cleaned = _TOMORROW_RE.sub("", cleaned)
    cleaned = _WEEKDAY_RE.sub("", cleaned)
    cleaned = _TIME_RE.sub("", cleaned)
    cleaned = re.sub(r"\bat\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!")
    return cleaned or utterance.strip()


def next_weekday_at(
    now_local: datetime,
    *,
    weekday: int,
    hour: int,
    minute: int,
) -> datetime:
    """Next local occurrence of weekday@hour:minute (today if still ahead)."""
    tz = now_local.tzinfo
    candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - now_local.weekday()) % 7
    if days_ahead == 0 and candidate <= now_local:
        days_ahead = 7
    if days_ahead:
        # Advance by calendar days then re-apply wall clock (DST-safe).
        base = (now_local + timedelta(days=days_ahead)).date()
        candidate = datetime(base.year, base.month, base.day, hour, minute, tzinfo=tz)
    return candidate


def next_weekly_after(previous_due: datetime, *, weekday: int, hour: int, minute: int) -> datetime:
    """Compute the following weekly occurrence in the same timezone."""
    tz = previous_due.tzinfo
    local = previous_due.astimezone(tz) if tz else previous_due
    # Jump ~7 days then snap to wall-clock in local TZ (handles DST).
    approx = local + timedelta(days=7)
    base = approx.date()
    # Prefer exact weekday match if DST/date math drifted.
    while base.weekday() != weekday:
        base = (datetime(base.year, base.month, base.day) + timedelta(days=1)).date()
    return datetime(base.year, base.month, base.day, hour, minute, tzinfo=tz)


def parse_reminder(
    utterance: str,
    *,
    now: datetime,
    timezone: str = "UTC",
) -> ParsedReminder:
    """Parse a reminder utterance into due time + body.

    Raises ValueError when no schedule signal is found.
    """
    raw = (utterance or "").strip()
    if not raw:
        raise ValueError("empty reminder utterance")

    tz = _resolve_tz(timezone)
    now_local = _local_now(now, tz)
    hour, minute = _parse_time(raw)
    body = _extract_body(raw)

    every = _EVERY_RE.search(raw)
    if every:
        day_name = every.group("day").lower()
        if day_name not in WEEKDAY_NAMES:
            raise ValueError(f"unknown weekday in every-clause: {day_name!r}")
        weekday = WEEKDAY_NAMES[day_name]
        due = next_weekday_at(now_local, weekday=weekday, hour=hour, minute=minute)
        return ParsedReminder(
            text=body,
            kind="recurring",
            timezone=timezone,
            due_at=due,
            weekday=weekday,
            hour=hour,
            minute=minute,
            body=body,
            raw=raw,
        )

    if _TOMORROW_RE.search(raw):
        tomorrow = (now_local + timedelta(days=1)).date()
        due = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute, tzinfo=tz)
        return ParsedReminder(
            text=body,
            kind="one_shot",
            timezone=timezone,
            due_at=due,
            weekday=None,
            hour=hour,
            minute=minute,
            body=body,
            raw=raw,
        )

    day_match = _WEEKDAY_RE.search(raw)
    if day_match:
        weekday = WEEKDAY_NAMES[day_match.group("day").lower()]
        due = next_weekday_at(now_local, weekday=weekday, hour=hour, minute=minute)
        # Bare weekday without "every" → one-shot (E2E-01).
        return ParsedReminder(
            text=body,
            kind="one_shot",
            timezone=timezone,
            due_at=due,
            weekday=weekday,
            hour=hour,
            minute=minute,
            body=body,
            raw=raw,
        )

    raise ValueError(f"could not parse reminder schedule from: {raw!r}")
