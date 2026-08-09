"""Deterministic models router: Luna default, Terra/Sol escalation stubs.

Routing is rule-based on structured signals — no live Luna/OpenAI calls in CI.
See agent-plan/intelligence/models-and-credits.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from intelligence.models.roles import IntentKind, ModelRole

# Luna-only intents (ordinary life tasks).
_LUNA_INTENTS = frozenset(
    {
        IntentKind.REMINDER,
        IntentKind.TODO,
        IntentKind.FAQ,
        IntentKind.CALENDAR_READ,
        IntentKind.DIET_SWAP,
        IntentKind.APPROVAL_SUMMARY,
    }
)

# Phrases that signal an explicit deep-plan request (case-insensitive substring).
_DEEP_PLAN_MARKERS = frozenset(
    {
        "deep plan",
        "detailed plan",
        "full weekly plan",
        "think hard",
        "deep research",
    }
)


@dataclass(frozen=True)
class RoutingSignals:
    """Structured routing inputs — produced by harness/fixtures, not live NLU."""

    intent: IntentKind = IntentKind.GENERAL
    utterance: str = ""
    multi_day_plan: bool = False
    has_calendar_constraints: bool = False
    has_diet_constraints: bool = False
    has_travel_constraints: bool = False
    booking_retry: bool = False
    booking_messy_conflict: bool = False
    deep_plan_request: bool = False
    self_mod_files: int = 0
    policy_change: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RoutingSignals:
        intent_raw = str(raw.get("intent") or IntentKind.GENERAL.value)
        try:
            intent = IntentKind(intent_raw)
        except ValueError:
            intent = IntentKind.GENERAL
        utterance = str(raw.get("utterance") or "")
        deep = bool(raw.get("deep_plan_request", False))
        if not deep and utterance:
            lower = utterance.lower()
            deep = any(marker in lower for marker in _DEEP_PLAN_MARKERS)
        return cls(
            intent=intent,
            utterance=utterance,
            multi_day_plan=bool(raw.get("multi_day_plan", False)),
            has_calendar_constraints=bool(raw.get("has_calendar_constraints", False)),
            has_diet_constraints=bool(raw.get("has_diet_constraints", False)),
            has_travel_constraints=bool(raw.get("has_travel_constraints", False)),
            booking_retry=bool(raw.get("booking_retry", False)),
            booking_messy_conflict=bool(raw.get("booking_messy_conflict", False)),
            deep_plan_request=deep,
            self_mod_files=int(raw.get("self_mod_files", 0)),
            policy_change=bool(raw.get("policy_change", False)),
        )


@dataclass(frozen=True)
class RoutingDecision:
    """Router output: selected model + audit trail of matched rules."""

    model: ModelRole
    reasons: tuple[str, ...] = field(default_factory=tuple)
    escalated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.value,
            "reasons": list(self.reasons),
            "escalated": self.escalated,
        }


def _constraint_count(signals: RoutingSignals) -> int:
    return sum(
        1
        for flag in (
            signals.has_calendar_constraints,
            signals.has_diet_constraints,
            signals.has_travel_constraints,
        )
        if flag
    )


def _normalize_intent(intent: IntentKind | str) -> IntentKind:
    if isinstance(intent, IntentKind):
        return intent
    try:
        return IntentKind(str(intent))
    except ValueError:
        return IntentKind.GENERAL


def route(signals: RoutingSignals) -> RoutingDecision:
    """Select Luna (default), Terra (medium), or Sol (heavy) deterministically."""
    intent = _normalize_intent(signals.intent)
    reasons: list[str] = []

    # --- Sol: hard weekly / deep research / non-trivial self-mod ---
    if signals.deep_plan_request:
        reasons.append("deep_plan_request")
    if signals.policy_change:
        reasons.append("policy_change")
    if signals.self_mod_files >= 2:
        reasons.append("self_mod_multi_file")
    if (
        signals.multi_day_plan
        and signals.has_calendar_constraints
        and signals.has_diet_constraints
        and signals.has_travel_constraints
    ):
        reasons.append("multi_day_calendar_diet_travel")
    if signals.booking_messy_conflict:
        reasons.append("booking_messy_conflict")

    if reasons:
        return RoutingDecision(
            model=ModelRole.SOL,
            reasons=tuple(reasons),
            escalated=True,
        )

    # --- Terra: medium planning / booking retry / multi-constraint days ---
    terra_reasons: list[str] = []
    if signals.booking_retry:
        terra_reasons.append("booking_retry")
    constraint_n = _constraint_count(signals)
    if signals.multi_day_plan and constraint_n >= 2:
        terra_reasons.append("multi_day_multi_constraint")
    if constraint_n >= 2 and intent is IntentKind.PLANNING:
        terra_reasons.append("planning_multi_constraint_day")

    if terra_reasons:
        return RoutingDecision(
            model=ModelRole.TERRA,
            reasons=tuple(terra_reasons),
            escalated=True,
        )

    # --- Luna: ordinary intents and tiny tweaks ---
    if intent in _LUNA_INTENTS:
        return RoutingDecision(
            model=ModelRole.LUNA,
            reasons=("luna_intent",),
            escalated=False,
        )
    if intent is IntentKind.DOC_TWEAK and signals.self_mod_files <= 1:
        return RoutingDecision(
            model=ModelRole.LUNA,
            reasons=("tiny_doc_tweak",),
            escalated=False,
        )
    if intent is IntentKind.SELF_MOD and signals.self_mod_files <= 1:
        return RoutingDecision(
            model=ModelRole.LUNA,
            reasons=("trivial_self_mod",),
            escalated=False,
        )

    return RoutingDecision(
        model=ModelRole.LUNA,
        reasons=("default_luna",),
        escalated=False,
    )
