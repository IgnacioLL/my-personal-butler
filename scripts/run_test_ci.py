#!/usr/bin/env python3
"""CI layer runners: unit, contract (INV-*), integration stubs.

Writes artifacts under artifacts/test/ci/. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harness.artifacts import write_report  # noqa: E402
from harness.clock import FakeClock  # noqa: E402
from harness.ingress_sim import IngressSimulator  # noqa: E402
from harness.inv_runner import run_all  # noqa: E402
from harness.outbound import OutboundMessageCatcher  # noqa: E402
from harness.whatsapp_transport import MockWhatsAppTransport  # noqa: E402
from policy.action_gateway import ActionGateway  # noqa: E402
from policy.approvals import (  # noqa: E402
    ApprovalStatus,
    ApprovalTier,
    tier_for,
)
from policy.ingress import evaluate_ingress, normalize_sender  # noqa: E402


def run_unit(out_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    clock = FakeClock()
    start = clock.now()
    clock.advance(timedelta(hours=1))
    ok = clock.now() - start == timedelta(hours=1)
    checks.append(
        {
            "id": "unit.fake_clock.advance",
            "result": "PASS" if ok else "FAIL",
            "detail": "advance(1h) moves now() by 1h" if ok else "clock skew",
        }
    )

    catcher = OutboundMessageCatcher()
    catcher.send("whatsapp", "+15550001111", "hello")
    ok2 = catcher.count() == 1 and catcher.messages[0].body == "hello"
    checks.append(
        {
            "id": "unit.outbound_catcher.capture",
            "result": "PASS" if ok2 else "FAIL",
            "detail": "catcher records one outbound message",
        }
    )

    # Approval matrix tiers (table-driven smoke)
    matrix_ok = (
        tier_for("todo_add") == ApprovalTier.AUTO
        and tier_for("calendar_create") == ApprovalTier.SOFT_CONFIRM
        and tier_for("buy") == ApprovalTier.HARD_APPROVE
        and tier_for("transfer_money") == ApprovalTier.FORBIDDEN
        and tier_for("self_mod_apply") == ApprovalTier.HARD_APPROVE
        and tier_for("policy_change") == ApprovalTier.HARD_APPROVE
    )
    checks.append(
        {
            "id": "unit.approval_matrix.tiers",
            "result": "PASS" if matrix_ok else "FAIL",
            "detail": "Auto/Soft/Hard/Forbidden mapping for sample actions",
        }
    )

    # Status machine: pending → accepted → executed; Accept once idempotent side-effect
    gw = ActionGateway(clock=FakeClock())
    prop = gw.propose("buy", "unit buy", {"sku": "u1", "price": 1.0})
    status_ok = False
    detail = "propose failed"
    if prop.approval_id:
        gw.accept(prop.approval_id)
        first = gw.execute(prop.approval_id)
        # Second accept on executed should fail closed (terminal)
        second_accept_blocked = False
        try:
            gw.accept(prop.approval_id)
        except Exception:  # noqa: BLE001
            second_accept_blocked = True
        item = gw.approvals.get(prop.approval_id)
        status_ok = (
            first.ok
            and gw.commerce.buy_count == 1
            and item is not None
            and item.status == ApprovalStatus.EXECUTED
            and second_accept_blocked
        )
        detail = (
            f"status={item.status.value if item else None} "
            f"buy_count={gw.commerce.buy_count} "
            f"second_accept_blocked={second_accept_blocked}"
        )
    checks.append(
        {
            "id": "unit.approval_status_machine",
            "result": "PASS" if status_ok else "FAIL",
            "detail": detail,
        }
    )

    # Kill switches snapshot
    gw2 = ActionGateway(clock=FakeClock())
    gw2.pause_agent()
    gw2.freeze_spending()
    gw2.freeze_self_mod()
    snap = gw2.kill.snapshot()
    kill_ok = (
        snap.get("pause_agent")
        and snap.get("freeze_spending")
        and snap.get("freeze_self_mod")
    )
    checks.append(
        {
            "id": "unit.kill_switches.flags",
            "result": "PASS" if kill_ok else "FAIL",
            "detail": f"snapshot={snap}",
        }
    )

    # Ingress normalize + empty allowlist fail-closed
    norm_ok = (
        normalize_sender("\u200b+15550001111") == "+15550001111"
        and normalize_sender("  +15550001111  ") == "+15550001111"
        and normalize_sender("") == ""
    )
    empty_dec = evaluate_ingress("+15550001111", [])
    group_dec = evaluate_ingress(
        "+15550001111",
        ["+15550001111"],
        is_group=False,
        group_id="120363@g.us",
        groups_enabled=False,
    )
    ingress_ok = (
        norm_ok
        and (not empty_dec.allowed)
        and empty_dec.reason == "empty_allowlist"
        and (not group_dec.allowed)
        and group_dec.reason == "groups_disabled"
    )
    checks.append(
        {
            "id": "unit.ingress.normalize_and_fail_closed",
            "result": "PASS" if ingress_ok else "FAIL",
            "detail": (
                f"norm_ok={norm_ok} empty={empty_dec.reason} group={group_dec.reason}"
            ),
        }
    )

    # Mock WhatsApp transport: reject → zero counters; allow → tools+outbound
    t_catcher = OutboundMessageCatcher()
    transport = MockWhatsAppTransport(
        allowlist=["+15550001111"], catcher=t_catcher, groups_enabled=False
    )
    denied = transport.inject_text("+19999999999", "nope")
    denied_ok = (
        (not denied.allowed)
        and transport.counters.tool_calls == 0
        and transport.counters.outbound_sends == 0
        and t_catcher.count() == 0
    )
    allowed = transport.inject_text("+15550001111", "ping")
    allowed_ok = (
        allowed.allowed
        and transport.counters.tool_calls == 1
        and transport.counters.outbound_sends == 1
        and t_catcher.count() == 1
    )
    checks.append(
        {
            "id": "unit.mock_whatsapp_transport.counters",
            "result": "PASS" if (denied_ok and allowed_ok) else "FAIL",
            "detail": (
                f"denied_ok={denied_ok} allowed_ok={allowed_ok} "
                f"counters={transport.counters.snapshot()}"
            ),
        }
    )

    result = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    write_report(out_dir / "unit", layer="unit", result=result, checks=checks)
    return {"layer": "unit", "result": result, "checks": checks}


def run_contract(out_dir: Path, *, broken_allow_all: bool) -> dict[str, Any]:
    ctx = {
        "allowlist": ["+15550001111"],
        "broken_allow_all": broken_allow_all,
        "artifacts_dir": str(out_dir / "contract"),
    }
    checks = run_all(ctx)
    result = "PASS" if all(c.get("result") == "PASS" for c in checks) else "FAIL"

    # Capture outbound from a positive allowlisted path for artifact convention.
    catcher = OutboundMessageCatcher()
    sim = IngressSimulator(
        allowlist=["+15550001111"],
        catcher=catcher,
        broken_allow_all=False,
    )
    sim.handle("+15550001111", "ping", is_group=False)
    outbound_path = out_dir / "contract" / "outbound-messages.json"
    catcher.write_json(outbound_path)

    write_report(
        out_dir / "contract",
        layer="contract",
        result=result,
        checks=checks,
        extra={
            "broken_allow_all": broken_allow_all,
            "outbound_messages": str(outbound_path.relative_to(ROOT)),
            "invariants_discovered": [c.get("id") for c in checks],
        },
    )
    return {"layer": "contract", "result": result, "checks": checks}


def run_integration(out_dir: Path) -> dict[str, Any]:
    """Integration stubs — full Virtual User lands later; prove harness wiring."""
    checks: list[dict[str, Any]] = []
    catcher = OutboundMessageCatcher()
    clock = FakeClock()
    sim = IngressSimulator(allowlist=["+15550001111"], catcher=catcher)

    # Reject then accept path with clock tick between.
    denied = sim.handle("+19999999999", "nope")
    clock.advance(60)
    allowed = sim.handle("+15550001111", "remind me")
    ok = (
        (not denied.allowed)
        and allowed.allowed
        and catcher.count() == 1
        and sim.counters.tool_calls == 1
        and sim.counters.outbound_sends == 1
    )
    checks.append(
        {
            "id": "integration.ingress_stub.roundtrip",
            "result": "PASS" if ok else "FAIL",
            "detail": (
                f"denied={denied.reason} allowed={allowed.reason} "
                f"outbound={catcher.count()} tools={sim.counters.tool_calls} "
                f"clock={clock.now().isoformat()}"
            ),
        }
    )

    # Mock transport: group_id without is_group still ignored; DM still works.
    t = MockWhatsAppTransport(
        allowlist=["+15550001111"], catcher=OutboundMessageCatcher()
    )
    sneaky = t.inject_text(
        "+15550001111", "sneaky", is_group=False, group_id="120363@g.us"
    )
    dm = t.inject_text("+15550001111", "ok dm")
    group_ok = (
        (not sneaky.allowed)
        and sneaky.reason == "groups_disabled"
        and dm.allowed
        and t.counters.tool_calls == 1
        and t.counters.outbound_sends == 1
    )
    checks.append(
        {
            "id": "integration.mock_whatsapp.group_id_isolation",
            "result": "PASS" if group_ok else "FAIL",
            "detail": (
                f"sneaky={sneaky.reason} dm={dm.reason} "
                f"counters={t.counters.snapshot()}"
            ),
        }
    )

    # Trust core: hard buy without accept cannot execute; accept then execute + audit.
    gw = ActionGateway(clock=FakeClock())
    prop = gw.propose("buy", "integration buy", {"sku": "int-1", "price": 9.99})
    trust_ok = False
    trust_detail = "propose failed"
    if prop.approval_id:
        blocked = gw.execute(prop.approval_id)
        gw.accept(prop.approval_id)
        done = gw.execute(prop.approval_id)
        audits = gw.audit.for_approval(prop.approval_id)
        trust_ok = (
            (not blocked.ok)
            and done.ok
            and gw.commerce.buy_count == 1
            and len(audits) == 1
            and audits[0].approval_id == prop.approval_id
        )
        trust_detail = (
            f"blocked={blocked.reason} executed={done.ok} "
            f"buy_count={gw.commerce.buy_count} audit={len(audits)}"
        )
    checks.append(
        {
            "id": "integration.trust_core.hard_buy_gate",
            "result": "PASS" if trust_ok else "FAIL",
            "detail": trust_detail,
        }
    )

    result = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    layer_dir = out_dir / "integration"
    catcher.write_json(layer_dir / "outbound-messages.json")
    write_report(layer_dir, layer="integration", result=result, checks=checks)
    return {"layer": "integration", "result": result, "checks": checks}


def aggregate(layers: list[dict[str, Any]], out_dir: Path, *, broken: bool) -> int:
    overall = "PASS" if all(L["result"] == "PASS" for L in layers) else "FAIL"
    flat_checks: list[dict[str, Any]] = []
    for layer in layers:
        for check in layer.get("checks", []):
            flat_checks.append(
                {
                    "id": f"{layer['layer']}:{check.get('id')}",
                    "result": check.get("result"),
                    "detail": check.get("detail", ""),
                }
            )

    write_report(
        out_dir,
        layer="test:ci",
        result=overall,
        checks=flat_checks,
        extra={
            "broken_allow_all": broken,
            "layers": [{"layer": L["layer"], "result": L["result"]} for L in layers],
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
                "artifacts": [
                    "artifacts/test/ci/",
                    "artifacts/test/task-03/",
                ],
            },
        },
    )

    # Compact stamp for autonomous verification loops.
    stamp = {
        "claim": (
            "WhatsApp ingress: allowlisted DM only; groups off; "
            "non-allowlisted → zero tools/outbound; INV-INGRESS-001/002 adversarial; "
            "003 scaffold; fail-closed on broken INV"
        ),
        "result": overall,
        "broken_allow_all": broken,
        "commands": [
            "./scripts/test-ci.sh --break-invariant"
            if broken
            else "./scripts/test-ci.sh"
        ],
        "artifacts": [
            "artifacts/test/ci/report.json",
            "artifacts/test/task-03/verification.json",
        ],
        "invariants": [
            c.get("id")
            for L in layers
            if L["layer"] == "contract"
            for c in L.get("checks", [])
        ],
    }
    (out_dir / "verification.json").write_text(
        json.dumps(stamp, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # TASK-02 dedicated artifact mirror (same CI results + trust focus).
    task02 = ROOT / "artifacts" / "test" / "task-02"
    task02.mkdir(parents=True, exist_ok=True)
    trust_ids = [
        c.get("id")
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith(("INV-APPR-", "INV-KILL-", "INV-AUDIT-"))
    ]
    trust_checks = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith(("INV-APPR-", "INV-KILL-", "INV-AUDIT-"))
    ]
    trust_pass = all(c.get("result") == "PASS" for c in trust_checks) if trust_checks else False
    write_report(
        task02,
        layer="task-02",
        result="PASS" if (overall == "PASS" and trust_pass) else ("FAIL" if not broken else overall),
        checks=trust_checks or flat_checks,
        extra={
            "broken_allow_all": broken,
            "trust_invariant_ids": trust_ids,
            "ci_overall": overall,
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
            },
        },
    )
    (task02 / "verification.json").write_text(
        json.dumps(
            {
                "claim": "No hard action path without accept; INV-APPR/KILL/AUDIT proven",
                "result": "PASS"
                if (overall == "PASS" and trust_pass)
                else ("FAIL" if not broken else overall),
                "ci_overall": overall,
                "trust_invariants": trust_ids,
                "commands": ["./scripts/test-ci.sh", "make test-ci"],
                "artifacts": [
                    "artifacts/test/task-02/report.json",
                    "artifacts/test/ci/report.json",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # TASK-03 WhatsApp ingress artifacts.
    task03 = ROOT / "artifacts" / "test" / "task-03"
    task03.mkdir(parents=True, exist_ok=True)
    ingress_ids = [
        c.get("id")
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-INGRESS-")
    ]
    ingress_checks = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-INGRESS-")
    ]
    ingress_pass = (
        all(c.get("result") == "PASS" for c in ingress_checks) if ingress_checks else False
    )
    # Mirror outbound from contract layer if present.
    contract_outbound = out_dir / "contract" / "outbound-messages.json"
    if contract_outbound.exists():
        (task03 / "outbound-messages.json").write_text(
            contract_outbound.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    write_report(
        task03,
        layer="task-03",
        result="PASS"
        if (overall == "PASS" and ingress_pass)
        else ("FAIL" if not broken else overall),
        checks=ingress_checks or flat_checks,
        extra={
            "broken_allow_all": broken,
            "ingress_invariant_ids": ingress_ids,
            "ci_overall": overall,
            "adversarial_coverage": [
                "non-allowlisted DM",
                "spoofed sender forms",
                "empty allowlist",
                "flood",
                "group is_group flag",
                "group_id without flag",
                "group JID / broadcast sender",
                "mixed DM then group",
                "audio transcript-or-clarify scaffold (003)",
            ],
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
                "artifacts": "artifacts/test/task-03/",
            },
        },
    )
    (task03 / "verification.json").write_text(
        json.dumps(
            {
                "claim": (
                    "Allowlisted DM only; groups disabled ignored; "
                    "non-allowlisted → no tools / no outbound side effects"
                ),
                "result": "PASS"
                if (overall == "PASS" and ingress_pass)
                else ("FAIL" if not broken else overall),
                "ci_overall": overall,
                "ingress_invariants": ingress_ids,
                "commands": [
                    "./scripts/test-ci.sh",
                    "make test-ci",
                    "make test-ci-fail-closed",
                ],
                "artifacts": [
                    "artifacts/test/task-03/report.json",
                    "artifacts/test/task-03/verification.json",
                    "artifacts/test/ci/report.json",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if overall == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run personal-agent CI test layers")
    parser.add_argument(
        "--break-invariant",
        action="store_true",
        help="Enable broken_allow_all so INV-INGRESS-* must fail (fail-closed proof)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=str(ROOT / "artifacts" / "test" / "ci"),
        help="Output directory for report.json / report.md",
    )
    parser.add_argument(
        "--layer",
        choices=("all", "unit", "contract", "integration"),
        default="all",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        layers: list[dict[str, Any]] = []
        if args.layer in ("all", "unit"):
            layers.append(run_unit(out_dir))
        if args.layer in ("all", "contract"):
            layers.append(run_contract(out_dir, broken_allow_all=args.break_invariant))
        if args.layer in ("all", "integration"):
            layers.append(run_integration(out_dir))
        return aggregate(layers, out_dir, broken=args.break_invariant)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        write_report(
            out_dir,
            layer="test:ci",
            result="FAIL",
            checks=[{"id": "runner", "result": "FAIL", "detail": str(exc)}],
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
