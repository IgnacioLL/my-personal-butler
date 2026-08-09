"""INV-SELF-001 — Writes outside path allowlist fail closed."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capabilities.selfmod.allowlist import AllowlistConfig, path_allowed
from capabilities.selfmod.service import SelfModService
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway

INV_ID = "INV-SELF-001"
DESCRIPTION = "Writes outside path allowlist fail closed"

ROOT = Path(__file__).resolve().parents[2]


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    cfg = AllowlistConfig.from_file(ROOT / "fixtures" / "selfmod" / "allowlist.json")

    if path_allowed("skills/reminders.md", cfg) is not True:
        failures.append("skills/reminders.md should be allowlisted")
    if path_allowed("config/agent.json", cfg) is not True:
        failures.append("config/agent.json should be allowlisted")
    if path_allowed("../../etc/passwd", cfg):
        failures.append("path escape must fail closed")
    if path_allowed("secrets/api_key.txt", cfg):
        failures.append("forbidden secrets/ must fail closed")
    if path_allowed(".env", cfg):
        failures.append(".env must fail closed")
    if path_allowed("src/runtime/gateway.py", cfg):
        failures.append("non-allowlisted src path must fail closed")

    tz = ZoneInfo("Europe/Madrid")
    clock = FakeClock(start=datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz))
    catcher = OutboundMessageCatcher()
    gw = ActionGateway(clock=clock)
    svc = SelfModService(
        clock=clock,
        catcher=catcher,
        gateway=gw,
        recipient="+15550001111",
        workspace_fixture=ROOT / "fixtures" / "selfmod" / "sample-workspace",
        allowlist_path=ROOT / "fixtures" / "selfmod" / "allowlist.json",
    )

    # Direct propose of an outside-allowlist write must fail closed (no approval).
    outside = svc.propose_patch(
        intent="edit outside",
        summary="Touch /etc/passwd via relative escape",
        files={"../../etc/passwd": "pwned"},
        diff_text="--- a/../../etc/passwd\n+++ b/../../etc/passwd\n+pwned\n",
    )
    if outside.ok:
        failures.append("outside-allowlist propose should not succeed")
    if not str(outside.reason).startswith("outside_allowlist"):
        failures.append(f"expected outside_allowlist reason, got {outside.reason!r}")
    if outside.approval_id is not None:
        failures.append("outside-allowlist must not create approval")
    if gw.selfmod.apply_count != 0:
        failures.append(f"apply leaked: {gw.selfmod.apply_count}")
    if not svc.workspace.working_tree_clean():
        failures.append("working tree dirty after rejected outside write")

    # Forbidden .env even under config-looking names.
    env_prop = svc.propose_patch(
        intent="write env",
        summary="Write .env",
        files={".env": "API_KEY=secret"},
        diff_text="--- a/.env\n+++ b/.env\n+API_KEY=secret\n",
    )
    if env_prop.ok or env_prop.approval_id:
        failures.append(".env propose must fail closed")

    svc.close()

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": "outside allowlist / forbidden globs fail closed; tree unchanged",
    }
