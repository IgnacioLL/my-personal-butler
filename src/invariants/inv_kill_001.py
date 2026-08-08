"""INV-KILL-001 — pause agent stops proactive cron emissions."""

from __future__ import annotations

from typing import Any

from harness.clock import FakeClock
from policy.action_gateway import ActionGateway

INV_ID = "INV-KILL-001"
DESCRIPTION = "pause agent stops proactive cron emissions"


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock()
    gw = ActionGateway(clock=clock)

    # Baseline: proactive emission works when not paused
    ok_emit = gw.cron.emit_proactive("morning_brief", {"kind": "heartbeat"})
    if not ok_emit.emitted or gw.cron.emitted_count() != 1:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"baseline emit failed: {ok_emit}",
        }

    gw.pause_agent()
    if not gw.kill.is_paused:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": "pause_agent did not set kill state",
        }

    blocked = gw.cron.emit_proactive("habit_nudge", {"habit": "stretch"})
    if blocked.emitted or blocked.reason != "pause_agent":
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"paused cron should not emit: {blocked}",
        }

    if gw.cron.emitted_count() != 1:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"emitted_count should stay 1, got {gw.cron.emitted_count()}",
        }

    # Resume restores proactive path
    gw.resume_agent()
    resumed = gw.cron.emit_proactive("evening_review", {})
    if not resumed.emitted or gw.cron.emitted_count() != 2:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"resume should allow emit again: {resumed}",
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": "pause blocks proactive cron; resume restores (emitted=2 total)",
    }
