"""INV-INGRESS-002 — group messages ignored while groups are disabled (stub)."""

from __future__ import annotations

from typing import Any

from harness.ingress_sim import IngressSimulator
from harness.outbound import OutboundMessageCatcher

INV_ID = "INV-INGRESS-002"
DESCRIPTION = "Group messages are ignored while groups are disabled"


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

    # Even an allowlisted number in a group must not run tools while groups off.
    result = sim.handle(allowlist[0], "group noise", is_group=True)
    if result.allowed or result.tool_calls or catcher.count():
        return {
            "id": INV_ID,
            "result": "FAIL",
            "detail": (
                f"group message produced effects while groups disabled "
                f"(allowed={result.allowed}, tools={result.tool_calls!r}, "
                f"outbound={catcher.count()}, reason={result.reason})"
            ),
        }

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": f"group ignored (reason={result.reason})",
    }
