"""PROD-08 CI checks — bookings/shopping production config safety.

Imported by scripts/run_test_ci.py so parallel PROD edits to that file are less
likely to delete these guards. Stub portal / dry-run merchant remain CI paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from capabilities.bookings.production import (
    BookingProductionConfig,
    load_booking_harness_config,
    load_booking_production_config,
)
from capabilities.shopping.production import (
    ShoppingProductionConfig,
    load_shopping_harness_config,
    load_shopping_production_config,
)
from harness.artifacts import write_report


def run_prod_08_booking_unit_checks(root: Path) -> list[dict[str, Any]]:
    """Production bookings config + skill smoke (stub portal remains CI path)."""
    checks: list[dict[str, Any]] = []
    try:
        prod = load_booking_production_config()
        harness = load_booking_harness_config()
        skill_md = root / "src" / "skills" / "bookings" / "SKILL.md"
        default_mode = prod.resolve_execute_mode(env={})
        live_both = prod.resolve_execute_mode(env={prod.live_flag.env: "1"})
        live_forced = BookingProductionConfig.from_dict({**prod.raw, "mode": "live"})
        live_ok = live_forced.resolve_execute_mode(env={prod.live_flag.env: "1"})
        ci_safe = live_forced.resolve_execute_mode(
            env={prod.live_flag.env: "1", "CI": "1"}
        )
        live_forced.assert_ci_safe(env={prod.live_flag.env: "1", "CI": "1"})
        ok = (
            prod.hard_approve_mandatory()
            and prod.mode == "dry_run"
            and default_mode == "dry_run"
            and live_both == "dry_run"
            and live_ok == "live"
            and ci_safe == "dry_run"
            and harness.get("live_forbidden") is True
            and harness.get("mode") == "stub_portal"
            and skill_md.is_file()
            and "hard approve" in skill_md.read_text(encoding="utf-8").lower()
            and (root / "docs" / "bookings-shopping-production.md").is_file()
        )
        checks.append(
            {
                "id": "unit.booking.prod08_production_config",
                "result": "PASS" if ok else "FAIL",
                "detail": (
                    f"mode={prod.mode} default={default_mode} "
                    f"env_alone={live_both} both={live_ok} ci={ci_safe} "
                    f"hard={prod.hard_approve_mandatory()} skill={skill_md.is_file()}"
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            {
                "id": "unit.booking.prod08_production_config",
                "result": "FAIL",
                "detail": f"error:{exc}",
            }
        )
    return checks


def run_prod_08_shopping_unit_checks(root: Path) -> list[dict[str, Any]]:
    """Production shopping config + skill smoke (dry-run merchant remains CI path)."""
    checks: list[dict[str, Any]] = []
    try:
        prod = load_shopping_production_config()
        harness = load_shopping_harness_config()
        skill_md = root / "src" / "skills" / "shopping" / "SKILL.md"
        default_mode = prod.resolve_execute_mode(env={})
        live_forced = ShoppingProductionConfig.from_dict({**prod.raw, "mode": "live"})
        live_ok = live_forced.resolve_execute_mode(env={prod.live_flag.env: "1"})
        env_alone = prod.resolve_execute_mode(env={prod.live_flag.env: "1"})
        ci_safe = live_forced.resolve_execute_mode(
            env={prod.live_flag.env: "1", "CI": "1"}
        )
        live_forced.assert_ci_safe(env={prod.live_flag.env: "1", "CI": "1"})
        ok = (
            prod.hard_approve_mandatory()
            and prod.freeze_spending_honored()
            and prod.mode == "dry_run"
            and prod.adapter_default == "dry_run"
            and prod.spend_caps.daily_limit == 50.0
            and prod.spend_caps.weekly_limit == 150.0
            and default_mode == "dry_run"
            and env_alone == "dry_run"
            and live_ok == "live"
            and ci_safe == "dry_run"
            and harness.get("mode") == "dry_run"
            and harness.get("live_forbidden") is True
            and skill_md.is_file()
            and "freeze" in skill_md.read_text(encoding="utf-8").lower()
            and (root / "config" / "production" / "openclaw.skills.snippet.json").is_file()
        )
        checks.append(
            {
                "id": "unit.shopping.prod08_production_config",
                "result": "PASS" if ok else "FAIL",
                "detail": (
                    f"mode={prod.mode} default={default_mode} "
                    f"env_alone={env_alone} both={live_ok} ci={ci_safe} "
                    f"caps={prod.spend_caps.daily_limit}/{prod.spend_caps.weekly_limit} "
                    f"freeze={prod.freeze_spending_honored()} skill={skill_md.is_file()}"
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            {
                "id": "unit.shopping.prod08_production_config",
                "result": "FAIL",
                "detail": f"error:{exc}",
            }
        )
    return checks


def write_prod_08_artifacts(
    *,
    root: Path,
    layers: list[dict[str, Any]],
    overall: str,
    broken: bool,
) -> bool:
    """Write artifacts/test/prod-08 stamps. Returns pass bool. No-op when broken."""
    prod08_unit = [
        c
        for L in layers
        if L["layer"] == "unit"
        for c in L.get("checks", [])
        if str(c.get("id", "")).endswith(".prod08_production_config")
    ]
    book_invs = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-BOOK-")
    ]
    pay_invs = [
        c
        for L in layers
        if L["layer"] == "contract"
        for c in L.get("checks", [])
        if str(c.get("id", "")).startswith("INV-PAY-")
    ]
    prod08_pass = (
        bool(prod08_unit)
        and all(c.get("result") == "PASS" for c in prod08_unit)
        and bool(book_invs)
        and all(c.get("result") == "PASS" for c in book_invs)
        and bool(pay_invs)
        and all(c.get("result") == "PASS" for c in pay_invs)
    )
    if broken:
        return prod08_pass

    prod08 = root / "artifacts" / "test" / "prod-08"
    prod08.mkdir(parents=True, exist_ok=True)
    try:
        book_cfg = load_booking_production_config()
        shop_cfg = load_shopping_production_config()
        book_harness = load_booking_harness_config()
        shop_harness = load_shopping_harness_config()
        payload = {
            "bookings": {
                "mode": book_cfg.mode,
                "resolve_default": book_cfg.resolve_execute_mode(env={}),
                "hard_approve": book_cfg.hard_approve_mandatory(),
                "live_env": book_cfg.live_flag.env,
                "skill": "src/skills/bookings/SKILL.md",
                "config": "config/production/bookings.json",
                "harness": "config/bookings.harness.json",
                "harness_live_forbidden": book_harness.get("live_forbidden"),
            },
            "shopping": {
                "mode": shop_cfg.mode,
                "resolve_default": shop_cfg.resolve_execute_mode(env={}),
                "hard_approve": shop_cfg.hard_approve_mandatory(),
                "freeze_spending": shop_cfg.freeze_spending_honored(),
                "spend_caps": shop_cfg.spend_caps.to_dict(),
                "live_env": shop_cfg.live_flag.env,
                "skill": "src/skills/shopping/SKILL.md",
                "config": "config/production/shopping.json",
                "harness": "config/shopping.harness.json",
                "harness_live_forbidden": shop_harness.get("live_forbidden"),
            },
            "runbook": "docs/bookings-shopping-production.md",
            "openclaw_snippet": "config/production/openclaw.skills.snippet.json",
        }
    except Exception as exc:  # noqa: BLE001
        payload = {"error": str(exc)}
        prod08_pass = False

    (prod08 / "production-config.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(
        prod08,
        layer="prod-08",
        result="PASS" if prod08_pass else "FAIL",
        checks=prod08_unit + book_invs + pay_invs,
        extra={
            "broken_allow_all": broken,
            "ci_overall": overall,
            "bookings_mode": (payload.get("bookings") or {}).get("mode"),
            "shopping_mode": (payload.get("shopping") or {}).get("mode"),
            "inv_book_green": all(c.get("result") == "PASS" for c in book_invs),
            "inv_pay_green": all(c.get("result") == "PASS" for c in pay_invs),
            "agent_b_rerun": {
                "happy_path": ["./scripts/test-ci.sh", "make test-ci"],
                "fail_closed_proof": [
                    "./scripts/test-ci.sh --break-invariant",
                    "make test-ci-fail-closed",
                ],
                "artifacts": "artifacts/test/prod-08/",
            },
        },
    )
    (prod08 / "verification.json").write_text(
        json.dumps(
            {
                "claim": (
                    "PROD-08 production bookings + shopping: Booksy-class browser "
                    "skill + merchant adapter configs behind hard approve; spend "
                    "caps + freeze spending; dry-run default with BOOKINGS_LIVE / "
                    "SHOPPING_LIVE documented; stub portal + dry-run merchant remain "
                    "CI-only; INV-BOOK-001/002 and INV-PAY-001/002 still gate CI"
                ),
                "result": "PASS" if prod08_pass else "FAIL",
                "ci_overall": overall,
                "unit_checks": [c.get("id") for c in prod08_unit],
                "invariants": [
                    "INV-BOOK-001",
                    "INV-BOOK-002",
                    "INV-PAY-001",
                    "INV-PAY-002",
                ],
                "bookings_config": "config/production/bookings.json",
                "shopping_config": "config/production/shopping.json",
                "skills": [
                    "src/skills/bookings/SKILL.md",
                    "src/skills/shopping/SKILL.md",
                ],
                "runbook": "docs/bookings-shopping-production.md",
                "commands": [
                    "./scripts/test-ci.sh",
                    "make test-ci",
                    "make test-ci-fail-closed",
                    "make e2e-06",
                    "make e2e-07",
                ],
                "artifacts": [
                    "artifacts/test/prod-08/report.json",
                    "artifacts/test/prod-08/verification.json",
                    "artifacts/test/prod-08/production-config.json",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return prod08_pass


__all__ = [
    "run_prod_08_booking_unit_checks",
    "run_prod_08_shopping_unit_checks",
    "write_prod_08_artifacts",
]
