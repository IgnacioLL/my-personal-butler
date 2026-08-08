"""INV-INGRESS-001 — non-allowlisted WhatsApp sender: no tools, no outbound.

Scaffolding for TASK-03 full coverage; this stub must already fail closed.
"""

from __future__ import annotations

from typing import Any

from harness.ingress_sim import IngressSimulator
from harness.outbound import OutboundMessageCatcher

INV_ID = "INV-INGRESS-001"
DESCRIPTION = (
    "Non-allowlisted WhatsApp sender produces no agent tools and no outbound side effects"
)


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    allowlist = ctx.get("allowlist") or ["+15550001111"]
    broken = bool(ctx.get("broken_allow_all", False))
    catcher = OutboundMessageCatcher()
    sim = IngressSimulator(
        allowlist=list(allowlist),
        catcher=catcher,
        groups_enabled=False,
        broken_allow_all=broken,
    )

    result = sim.handle("+19999999999", "please buy groceries", is_group=False)
    tools = result.tool_calls
    outbound = catcher.count()

    if tools or outbound:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": (
                f"non-allowlisted sender caused side effects "
                f"(tools={tools!r}, outbound={outbound}, reason={result.reason})"
            ),
        }

    if result.allowed:
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": f"non-allowlisted sender incorrectly allowed (reason={result.reason})",
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": f"rejected with reason={result.reason}; tools=0 outbound=0",
    }
