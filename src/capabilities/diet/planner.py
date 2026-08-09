"""Deterministic meal planner — memory constraints + calendar schedule hints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from capabilities.calendar.store import CalendarEvent, CalendarStore
from capabilities.diet.constraints import banned_terms, text_violations
from capabilities.diet.store import Meal, MealPlan


@dataclass(frozen=True)
class CatalogMeal:
    slot: str
    name: str
    ingredients: tuple[str, ...]
    tags: tuple[str, ...] = ()
    quick: bool = False


# Harness catalog — explicit ingredients for constraint checks (no LLM).
_MEAL_CATALOG: tuple[CatalogMeal, ...] = (
    CatalogMeal(
        "breakfast",
        "Mediterranean omelette",
        ("eggs", "feta cheese", "tomato", "olive oil"),
        ("mediterranean", "low_carb"),
    ),
    CatalogMeal(
        "breakfast",
        "Oat milk chia pudding",
        ("oat milk", "chia seeds", "berries"),
        ("low_carb",),
    ),
    CatalogMeal(
        "breakfast",
        "Greek yogurt with walnuts",
        ("greek yogurt", "walnuts", "honey"),
        ("mediterranean", "low_carb"),
    ),
    CatalogMeal(
        "lunch",
        "Grilled chicken salad",
        ("chicken breast", "mixed greens", "olive oil", "lemon"),
        ("mediterranean", "low_carb"),
    ),
    CatalogMeal(
        "lunch",
        "Tuna and avocado bowl",
        ("tuna", "avocado", "cucumber", "olive oil"),
        ("mediterranean", "low_carb"),
    ),
    CatalogMeal(
        "lunch",
        "Lentil soup with vegetables",
        ("lentils", "carrot", "celery", "tomato"),
        ("mediterranean",),
    ),
    CatalogMeal(
        "dinner",
        "Baked salmon with broccoli",
        ("salmon", "broccoli", "olive oil", "lemon"),
        ("mediterranean", "low_carb"),
    ),
    CatalogMeal(
        "dinner",
        "Quick chicken stir-fry",
        ("chicken breast", "bell pepper", "soy sauce", "ginger"),
        ("quick", "low_carb"),
        quick=True,
    ),
    CatalogMeal(
        "dinner",
        "Turkey meatballs with zucchini",
        ("ground turkey", "zucchini", "tomato sauce", "oregano"),
        ("mediterranean", "low_carb"),
    ),
    # Deliberately bad options — must be filtered by constraints:
    CatalogMeal(
        "dinner",
        "Peanut noodles",
        ("peanut sauce", "rice noodles", "scallion"),
        (),
    ),
    CatalogMeal(
        "dinner",
        "Shrimp scampi",
        ("shrimp", "garlic", "butter", "parsley"),
        (),
    ),
    CatalogMeal(
        "lunch",
        "Cilantro lime rice bowl",
        ("rice", "black beans", "cilantro", "lime"),
        (),
    ),
)


def _meal_allowed(candidate: CatalogMeal, banned: set[str]) -> bool:
    blob = " ".join([candidate.name, *candidate.ingredients])
    return len(text_violations(blob, banned)) == 0


def _score_meal(candidate: CatalogMeal, *, likes: set[str], prefer_quick: bool) -> int:
    score = 0
    joined = " ".join(candidate.tags).lower()
    for like in likes:
        if like in joined or like in candidate.name.lower():
            score += 2
    if "mediterranean" in candidate.tags:
        score += 1
    if "low_carb" in candidate.tags:
        score += 1
    if prefer_quick and candidate.quick:
        score += 3
    if prefer_quick and not candidate.quick:
        score -= 1
    return score


def _day_bounds(plan_date: date, timezone: str) -> tuple[datetime, datetime]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(timezone)
    start = datetime.combine(plan_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def schedule_hints(
    calendar: CalendarStore,
    plan_date: date,
    timezone: str,
) -> tuple[bool, bool, list[str]]:
    """Return (late_night, busy_day, notes) from calendar events on plan_date."""
    day_start, day_end = _day_bounds(plan_date, timezone)
    events = calendar.list_between(day_start, day_end)
    notes: list[str] = []
    late_night = False
    busy_minutes = 0
    for evt in events:
        busy_minutes += int((min(evt.end, day_end) - max(evt.start, day_start)).total_seconds() // 60)
        if evt.end.hour >= 21 or (evt.end.hour == 20 and evt.end.minute >= 30):
            late_night = True
            notes.append(f"Late event: {evt.title} ends {evt.end.strftime('%H:%M')}")
    busy_day = busy_minutes >= 240
    if busy_day:
        notes.append(f"Busy day ({busy_minutes} min scheduled) — favoring quick meals")
    return late_night, busy_day, notes


def build_meal_plan(
    *,
    plan_date: date,
    timezone: str,
    constraints: dict[str, Any],
    calendar: CalendarStore,
) -> MealPlan:
    """Select one meal per slot respecting constraints and schedule."""
    banned = banned_terms(constraints)
    likes = {str(x).strip().lower() for x in constraints.get("food_likes") or [] if str(x).strip()}
    late_night, busy_day, schedule_notes = schedule_hints(calendar, plan_date, timezone)
    prefer_quick = late_night or busy_day

    meals: list[Meal] = []
    grocery: set[str] = set()
    for slot in ("breakfast", "lunch", "dinner"):
        candidates = [
            c
            for c in _MEAL_CATALOG
            if c.slot == slot and _meal_allowed(c, banned)
        ]
        if not candidates:
            raise ValueError(f"no allowed meals for slot {slot!r}")
        best = max(
            candidates,
            key=lambda c: _score_meal(c, likes=likes, prefer_quick=prefer_quick),
        )
        meal = Meal(
            slot=best.slot,
            name=best.name,
            ingredients=list(best.ingredients),
            tags=list(best.tags),
            quick=best.quick,
        )
        meals.append(meal)
        grocery.update(best.ingredients)

    # Prefer oat milk when user likes it and it is not banned.
    if "oat milk" in likes and "oat milk" not in banned:
        grocery.add("oat milk")

    return MealPlan(
        plan_date=plan_date,
        timezone=timezone,
        meals=meals,
        grocery_items=sorted(grocery),
        schedule_notes=schedule_notes,
        constraints_applied={
            "allergies": list(constraints.get("allergies") or []),
            "food_dislikes": list(constraints.get("food_dislikes") or []),
            "diet_phase": constraints.get("diet_phase") or "",
            "late_night": late_night,
            "busy_day": busy_day,
        },
    )


def events_on_date(calendar: CalendarStore, plan_date: date, timezone: str) -> list[CalendarEvent]:
    day_start, day_end = _day_bounds(plan_date, timezone)
    return calendar.list_between(day_start, day_end)
