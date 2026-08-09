"""Structured meal plan types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class Meal:
    slot: str
    name: str
    ingredients: list[str]
    tags: list[str] = field(default_factory=list)
    quick: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "name": self.name,
            "ingredients": list(self.ingredients),
            "tags": list(self.tags),
            "quick": self.quick,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Meal":
        return cls(
            slot=str(data.get("slot") or ""),
            name=str(data.get("name") or ""),
            ingredients=[str(i) for i in data.get("ingredients") or []],
            tags=[str(t) for t in data.get("tags") or []],
            quick=bool(data.get("quick")),
        )


@dataclass
class MealPlan:
    plan_date: date
    timezone: str
    meals: list[Meal]
    grocery_items: list[str]
    schedule_notes: list[str] = field(default_factory=list)
    constraints_applied: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_date": self.plan_date.isoformat(),
            "timezone": self.timezone,
            "meals": [m.to_dict() for m in self.meals],
            "grocery_items": list(self.grocery_items),
            "schedule_notes": list(self.schedule_notes),
            "constraints_applied": dict(self.constraints_applied),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MealPlan":
        raw_date = data.get("plan_date")
        if not raw_date:
            raise ValueError("meal plan requires plan_date")
        return cls(
            plan_date=date.fromisoformat(str(raw_date)),
            timezone=str(data.get("timezone") or "UTC"),
            meals=[Meal.from_dict(m) for m in data.get("meals") or []],
            grocery_items=[str(i) for i in data.get("grocery_items") or []],
            schedule_notes=[str(n) for n in data.get("schedule_notes") or []],
            constraints_applied=dict(data.get("constraints_applied") or {}),
        )
