"""INV-T0-CLOCK — fake clock advance is monotonic and deterministic (unit-backed)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from harness.clock import FakeClock

INV_ID = "INV-T0-CLOCK"
DESCRIPTION = "Fake clock now()/advance(duration) is deterministic"


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock()
    t0 = clock.now()
    t1 = clock.advance(timedelta(minutes=5))
    t2 = clock.now()
    if t1 != t2:
        return {"id": INV_ID, "result": "FAIL", "detail": "now() != last advance()"}
    if t1 - t0 != timedelta(minutes=5):
        return {"id": INV_ID, "result": "FAIL", "detail": f"advance skew: {t1 - t0}"}
    clock.advance(30)  # seconds sugar
    if clock.now() - t1 != timedelta(seconds=30):
        return {"id": INV_ID, "result": "FAIL", "detail": "seconds advance failed"}
    return {"id": INV_ID, "result": "PASS", "detail": "now/advance OK"}
