"""Optional non-blocking diet plan quality eval stub (eval lane)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_EVAL_THRESHOLD = 0.6


@dataclass
class DietEvalResult:
    score: float
    threshold: float
    passed: bool
    blocking: bool = False
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "threshold": self.threshold,
            "passed": self.passed,
            "blocking": self.blocking,
            "notes": list(self.notes or []),
        }


def evaluate_plan_quality(
    plan: dict[str, Any],
    *,
    threshold: float = DEFAULT_EVAL_THRESHOLD,
) -> DietEvalResult:
    """Heuristic prose/structure score — non-blocking in CI."""
    meals = plan.get("meals") or []
    grocery = plan.get("grocery_items") or []
    notes: list[str] = []
    score = 0.0
    if len(meals) >= 3:
        score += 0.35
        notes.append("three_meals")
    slots = {str(m.get("slot")) for m in meals}
    if slots >= {"breakfast", "lunch", "dinner"}:
        score += 0.25
        notes.append("full_day_slots")
    if grocery:
        score += 0.2
        notes.append("grocery_list")
    if plan.get("constraints_applied"):
        score += 0.1
        notes.append("constraints_recorded")
    if plan.get("schedule_notes"):
        score += 0.1
        notes.append("schedule_aware")
    passed = score >= threshold
    return DietEvalResult(
        score=round(score, 3),
        threshold=threshold,
        passed=passed,
        blocking=False,
        notes=notes,
    )
