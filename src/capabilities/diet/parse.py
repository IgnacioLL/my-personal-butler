"""Natural-language meal-plan intent parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

_PLAN_MEALS = re.compile(
    r"^(?:\[Audio\]\s*)?plan\s+meals\s+for\s+"
    r"(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"\s*\.?\s*$",
    re.IGNORECASE,
)

_WEEKDAY_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

EXPECTED_E2E05_UTTERANCE = "Plan meals for tomorrow."


@dataclass(frozen=True)
class ParsedMealPlanRequest:
    target_phrase: str
    plan_date: date


def parse_meal_plan_request(utterance: str, *, now: datetime) -> ParsedMealPlanRequest:
    """Parse 'Plan meals for tomorrow.' (and audio-prefixed variants)."""
    text = (utterance or "").strip()
    match = _PLAN_MEALS.match(text)
    if not match:
        raise ValueError(f"not a meal plan utterance: {utterance!r}")
    phrase = match.group(1).strip().lower()
    plan_date = _resolve_plan_date(phrase, now)
    return ParsedMealPlanRequest(target_phrase=phrase, plan_date=plan_date)


def looks_like_meal_plan(body: str) -> bool:
    """Fast intent check for agent routing."""
    return bool(_PLAN_MEALS.match((body or "").strip()))


def _resolve_plan_date(phrase: str, now: datetime) -> date:
    local = now
    if phrase == "today":
        return local.date()
    if phrase == "tomorrow":
        return (local + timedelta(days=1)).date()
    if phrase in _WEEKDAY_TO_INDEX:
        target = _WEEKDAY_TO_INDEX[phrase]
        days_ahead = (target - local.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return (local + timedelta(days=days_ahead)).date()
    raise ValueError(f"unsupported plan date phrase: {phrase!r}")
