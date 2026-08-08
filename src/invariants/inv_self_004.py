"""INV-SELF-004 — Secrets patterns are rejected from proposed commits."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from capabilities.selfmod.secrets import (
    SelfModSecretsError,
    scan_diff_for_secrets,
    validate_patch_no_secrets,
)
from capabilities.selfmod.service import SelfModService
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway

INV_ID = "INV-SELF-004"
DESCRIPTION = "Secrets patterns are rejected from proposed commits"

ROOT = Path(__file__).resolve().parents[2]


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []

    # Unit: scanner catches common credential shapes.
    samples = [
        "api_key = sk-abcdefghijklmnopqrstuvwxyz012345",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
        "AWS_KEY=AKIAIOSFODNN7EXAMPLE",
        "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "password = hunter2-secret",
    ]
    for sample in samples:
        hits = scan_diff_for_secrets(sample)
        if not hits:
            failures.append(f"scanner missed secret sample: {sample[:32]!r}")
        try:
            validate_patch_no_secrets(sample)
            failures.append(f"validate_patch_no_secrets accepted: {sample[:32]!r}")
        except SelfModSecretsError:
            pass

    clean = "quiet_hours:\n  enabled: true\n  start: \"22:00\"\n"
    if scan_diff_for_secrets(clean):
        failures.append("clean quiet-hours text flagged as secret")

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

    poisoned = (
        "# Reminders skill\n\n"
        "api_key = sk-abcdefghijklmnopqrstuvwxyz012345\n"
        "quiet_hours:\n  enabled: true\n"
    )
    rejected = svc.propose_patch(
        intent="sneak secret into skill",
        summary="Poisoned quiet hours patch",
        files={"skills/reminders.md": poisoned},
        diff_text=(
            "--- a/skills/reminders.md\n+++ b/skills/reminders.md\n"
            "+api_key = sk-abcdefghijklmnopqrstuvwxyz012345\n"
        ),
    )
    if rejected.ok:
        failures.append("secret-bearing propose should fail")
    if not str(rejected.reason).startswith("secrets_rejected"):
        failures.append(f"expected secrets_rejected, got {rejected.reason!r}")
    if rejected.approval_id is not None:
        failures.append("secret propose must not create approval")
    if gw.selfmod.apply_count != 0:
        failures.append("secret propose leaked apply")
    if not svc.workspace.working_tree_clean():
        failures.append("tree dirty after secrets rejection")

    # Clean propose still works.
    clean_prop = svc.propose_from_utterance(
        "Add quiet hours: no calls after 22:00."
    )
    if not clean_prop.ok or not clean_prop.approval_id:
        failures.append(f"clean propose failed: {clean_prop.reason}")
    if clean_prop.ok and not svc.workspace.working_tree_clean():
        failures.append("clean propose mutated tree")

    svc.close()

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "secret patterns rejected at propose; no approval/apply; "
            "clean quiet-hours propose still ok"
        ),
    }
