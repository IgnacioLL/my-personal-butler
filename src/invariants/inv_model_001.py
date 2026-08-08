"""INV-MODEL-001 — Luna is the default chat model for ordinary intents."""

from __future__ import annotations

from typing import Any

from intelligence.models.fixtures import load_routing_fixture
from intelligence.models.roles import ModelRole
from intelligence.models.router import RoutingSignals, route

INV_ID = "INV-MODEL-001"
DESCRIPTION = "Ordinary intents route to Luna (default brain); no escalation"


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    fixture = load_routing_fixture()
    failures: list[str] = []
    luna_cases = [
        c for c in fixture.get("cases", []) if c.get("expected_model") == ModelRole.LUNA.value
    ]

    if not luna_cases:
        failures.append("fixture missing luna cases")

    for case in luna_cases:
        case_id = case.get("id", "?")
        signals = RoutingSignals.from_dict(case.get("signals") or {})
        decision = route(signals)
        if decision.model is not ModelRole.LUNA:
            failures.append(
                f"{case_id}: expected luna got {decision.model.value} reasons={decision.reasons}"
            )
        if decision.escalated:
            failures.append(f"{case_id}: ordinary intent should not escalate")

    # Spot-check default for bare general intent.
    default_dec = route(RoutingSignals(intent="general", utterance="hello"))
    if default_dec.model is not ModelRole.LUNA:
        failures.append(f"general hello: expected luna got {default_dec.model.value}")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": f"luna default for {len(luna_cases)} fixture intents + general hello",
    }
