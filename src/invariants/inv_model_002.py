"""INV-MODEL-002 — Hard planning and non-trivial self-mod escalate to Terra or Sol."""

from __future__ import annotations

from typing import Any

from intelligence.models.fixtures import load_routing_fixture
from intelligence.models.roles import ModelRole
from intelligence.models.router import RoutingSignals, route

INV_ID = "INV-MODEL-002"
DESCRIPTION = (
    "Multi-constraint planning and booking retry → Terra; "
    "deep plan / multi-file self-mod / policy change → Sol"
)


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    fixture = load_routing_fixture()
    failures: list[str] = []

    for case in fixture.get("cases", []):
        expected = case.get("expected_model")
        if expected not in {ModelRole.TERRA.value, ModelRole.SOL.value}:
            continue
        case_id = case.get("id", "?")
        signals = RoutingSignals.from_dict(case.get("signals") or {})
        decision = route(signals)
        if decision.model.value != expected:
            failures.append(
                f"{case_id}: expected {expected} got {decision.model.value} "
                f"reasons={decision.reasons}"
            )
        if not decision.escalated:
            failures.append(f"{case_id}: expected escalated=True")

    # Terra must not be used for trivial Luna intents.
    reminder = route(RoutingSignals(intent="reminder", utterance="ping me at 5"))
    if reminder.model is not ModelRole.LUNA:
        failures.append(f"reminder should stay luna got {reminder.model.value}")

    # Sol must win over Terra when both signals present.
    both = route(
        RoutingSignals(
            intent="planning",
            utterance="deep plan for travel week",
            multi_day_plan=True,
            has_calendar_constraints=True,
            has_diet_constraints=True,
            has_travel_constraints=True,
            booking_retry=True,
        )
    )
    if both.model is not ModelRole.SOL:
        failures.append(f"sol-over-terra: expected sol got {both.model.value}")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    escalated = [
        c.get("id")
        for c in fixture.get("cases", [])
        if c.get("expected_model") in {ModelRole.TERRA.value, ModelRole.SOL.value}
    ]
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": f"escalation verified for {len(escalated)} fixtures; sol-over-terra ok",
    }
