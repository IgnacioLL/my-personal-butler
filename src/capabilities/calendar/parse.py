"""Natural-language calendar schedule parsing (WhatsApp text / STT turns).

Enough for E2E-04: “Schedule focus block Friday 09:00–11:00.”

Note: weekday helpers are local (not imported from reminders.parse) to avoid a
circular import: calendar → reminders → harness → virtual_user → calendar.
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

_SCHEDULE_PREFIX = re.compile(
    r"^\s*(?:\[Audio\]\s*)?schedule\b",
    re.IGNORECASE,
)
_WEEKDAY_RE = re.compile(
    r"\b(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_TIME_RANGE_RE = re.compile(
    r"\b(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<ampm1>am|pm)?"
    r"\s*[-–—−]\s*"
    r"(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<ampm2>am|pm)?\b",
    re.IGNORECASE,
)
_MORNING_RE = re.compile(r"\bmorning\b", re.IGNORECASE)
_AFTERNOON_RE = re.compile(r"\bafternoon\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedCalendarEvent:
    title: str
    start: datetime
    end: datetime
    timezone: str
    weekday: Optional[int]
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


def _next_weekday_at(
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
        base = (now_local + timedelta(days=days_ahead)).date()
        candidate = datetime(base.year, base.month, base.day, hour, minute, tzinfo=tz)
    return candidate


def _hour_minute(h: str, m: Optional[str], ampm: Optional[str]) -> tuple[int, int]:
    hour = int(h)
    minute = int(m or 0)
    ap = (ampm or "").lower()
    if ap == "pm" and hour < 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise ValueError(f"invalid time {hour}:{minute:02d}")
    return hour, minute


def _extract_title(utterance: str) -> str:
    cleaned = _SCHEDULE_PREFIX.sub("", utterance).strip()
    cleaned = _WEEKDAY_RE.sub("", cleaned)
    cleaned = _TIME_RANGE_RE.sub("", cleaned)
    cleaned = _MORNING_RE.sub("", cleaned)
    cleaned = _AFTERNOON_RE.sub("", cleaned)
    cleaned = re.sub(r"\bat\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!:;")
    return cleaned or "Scheduled block"


def looks_like_schedule(body: str) -> bool:
    """Fast intent check for agent routing."""
    text = (body or "").strip()
    if not _SCHEDULE_PREFIX.match(text):
        return False
    return bool(
        _WEEKDAY_RE.search(text) or _MORNING_RE.search(text) or _TIME_RANGE_RE.search(text)
    )


def parse_schedule(
    utterance: str,
    *,
    now: datetime,
    timezone: str = "UTC",
) -> ParsedCalendarEvent:
    """Parse a schedule utterance into start/end datetimes.

    Raises ValueError when schedule signals are missing.
    """
    raw = (utterance or "").strip()
    if not raw:
        raise ValueError("empty schedule utterance")
    if not _SCHEDULE_PREFIX.match(raw):
        raise ValueError(f"not a schedule utterance: {utterance!r}")

    tz = _resolve_tz(timezone)
    now_local = _local_now(now, tz)

    day_match = _WEEKDAY_RE.search(raw)
    if not day_match:
        raise ValueError(f"could not parse weekday from: {raw!r}")
    weekday = WEEKDAY_NAMES[day_match.group("day").lower()]

    range_match = _TIME_RANGE_RE.search(raw)
    if range_match:
        h1, m1 = _hour_minute(
            range_match.group("h1"),
            range_match.group("m1"),
            range_match.group("ampm1"),
        )
        h2, m2 = _hour_minute(
            range_match.group("h2"),
            range_match.group("m2"),
            range_match.group("ampm2"),
        )
    elif _MORNING_RE.search(raw):
        h1, m1, h2, m2 = 9, 0, 11, 0
    elif _AFTERNOON_RE.search(raw):
        h1, m1, h2, m2 = 14, 0, 16, 0
    else:
        raise ValueError(f"could not parse time range from: {raw!r}")

    start = _next_weekday_at(now_local, weekday=weekday, hour=h1, minute=m1)
    end = _next_weekday_at(now_local, weekday=weekday, hour=h2, minute=m2)
    if end.date() != start.date() or end <= start:
        end = start.replace(hour=h2, minute=m2, second=0, microsecond=0)
        if end <= start:
            raise ValueError(f"end must be after start in utterance: {raw!r}")

    title = _extract_title(raw)
    return ParsedCalendarEvent(
        title=title,
        start=start,
        end=end,
        timezone=timezone,
        weekday=weekday,
        raw=raw,
    )
