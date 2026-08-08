"""Discoverable INV-* invariant checks for the contract/policy CI layer."""

from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules
from typing import Any, Callable

CheckFn = Callable[[dict[str, Any]], dict[str, Any]]


def discover_invariants() -> list[tuple[str, CheckFn]]:
    """Load check_* callables from src.invariants modules (INV_* ids)."""
    import invariants as package

    found: list[tuple[str, CheckFn]] = []
    for modinfo in iter_modules(package.__path__, package.__name__ + "."):
        module = import_module(modinfo.name)
        inv_id = getattr(module, "INV_ID", None)
        check = getattr(module, "check", None)
        if inv_id and callable(check):
            found.append((str(inv_id), check))
    found.sort(key=lambda item: item[0])
    return found


def run_all(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for inv_id, check in discover_invariants():
        try:
            outcome = check(ctx)
        except Exception as exc:  # noqa: BLE001 — fail closed on check crashes
            outcome = {
                "id": inv_id,
                "result": "FAIL",
                "detail": f"check raised: {exc}",
            }
        if "id" not in outcome:
            outcome["id"] = inv_id
        if outcome.get("result") not in {"PASS", "FAIL", "BLOCKED"}:
            outcome["result"] = "FAIL"
            outcome["detail"] = outcome.get("detail", "missing result")
        results.append(outcome)
    return results
