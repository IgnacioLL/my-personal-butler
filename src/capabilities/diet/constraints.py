"""Diet constraint checks — allergies, dislikes, diet phase."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", (term or "").strip().lower())


def banned_terms(constraints: dict[str, Any]) -> set[str]:
    """Union of allergies, dislikes, and phase-derived exclusions."""
    terms: set[str] = set()
    for allergen in constraints.get("allergies") or []:
        norm = normalize_term(str(allergen))
        if norm:
            terms.add(norm)
    for dislike in constraints.get("food_dislikes") or []:
        norm = normalize_term(str(dislike))
        if norm:
            terms.add(norm)
    diet_phase = normalize_term(str(constraints.get("diet_phase") or ""))
    if "low carb" in diet_phase or "keto" in diet_phase:
        terms.update({"rice", "pasta", "bread", "potato", "potatoes", "noodles"})
    return terms


def text_violations(text: str, banned: set[str]) -> list[str]:
    """Return banned terms found as substrings in *text* (case-insensitive)."""
    lowered = (text or "").lower()
    hits: list[str] = []
    for term in sorted(banned):
        if term and term in lowered:
            hits.append(term)
    return hits


def ingredient_list_violations(ingredients: list[str], banned: set[str]) -> list[str]:
    hits: list[str] = []
    for ingredient in ingredients:
        hits.extend(text_violations(ingredient, banned))
    return sorted(set(hits))


@dataclass
class ConstraintCheckResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    banned_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "violations": list(self.violations),
            "banned_terms": list(self.banned_terms),
        }


def check_meal_plan(
    *,
    meals: list[dict[str, Any]],
    grocery_items: list[str],
    constraints: dict[str, Any],
) -> ConstraintCheckResult:
    """Fail closed if any meal or grocery item contains a banned term."""
    banned = banned_terms(constraints)
    violations: list[str] = []
    for meal in meals:
        name = str(meal.get("name") or "")
        ingredients = [str(i) for i in meal.get("ingredients") or []]
        for hit in text_violations(name, banned):
            violations.append(f"meal:{name}:{hit}")
        for hit in ingredient_list_violations(ingredients, banned):
            violations.append(f"ingredient:{name}:{hit}")
    for item in grocery_items:
        for hit in text_violations(str(item), banned):
            violations.append(f"grocery:{item}:{hit}")
    return ConstraintCheckResult(
        ok=len(violations) == 0,
        violations=violations,
        banned_terms=sorted(banned),
    )
