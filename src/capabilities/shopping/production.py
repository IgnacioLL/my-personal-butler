"""Production shopping skill config — dry-run default; live behind explicit flag.

Spend caps + freeze spending remain mandatory. CI never resolves to live charge.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from policy.spend_caps import SpendCapConfig

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PRODUCTION = ROOT / "config" / "production" / "shopping.json"
DEFAULT_HARNESS = ROOT / "config" / "shopping.harness.json"

_CI_TRUTHY = {"1", "true", "yes", "ci", "harness"}


@dataclass(frozen=True)
class ShoppingLiveFlag:
    env: str = "SHOPPING_LIVE"
    config_mode_value: str = "live"
    requires_both: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ShoppingLiveFlag":
        raw = data or {}
        return cls(
            env=str(raw.get("env") or "SHOPPING_LIVE"),
            config_mode_value=str(raw.get("config_mode_value") or "live"),
            requires_both=bool(raw.get("requires_both", True)),
        )


@dataclass(frozen=True)
class ShoppingApprovalPolicy:
    tier: str = "hard_approve"
    mandatory: bool = True
    action_type: str = "buy"
    card_fields: tuple[str, ...] = ("merchant", "sku", "name", "price", "currency")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ShoppingApprovalPolicy":
        raw = data or {}
        fields = raw.get("card_fields") or [
            "merchant",
            "sku",
            "name",
            "price",
            "currency",
        ]
        return cls(
            tier=str(raw.get("tier") or "hard_approve"),
            mandatory=bool(raw.get("mandatory", True)),
            action_type=str(raw.get("action_type") or "buy"),
            card_fields=tuple(str(f) for f in fields),
        )


@dataclass(frozen=True)
class ShoppingKillSwitchPolicy:
    freeze_spending: bool = True
    blocks_stale_accepted: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ShoppingKillSwitchPolicy":
        raw = data or {}
        return cls(
            freeze_spending=bool(raw.get("freeze_spending", True)),
            blocks_stale_accepted=bool(raw.get("blocks_stale_accepted", True)),
        )


@dataclass
class ShoppingProductionConfig:
    """Loaded production shopping profile (merchant adapters + caps)."""

    skill: str = "shopping"
    profile: str = "production"
    mode: str = "dry_run"
    live_flag: ShoppingLiveFlag = field(default_factory=ShoppingLiveFlag)
    approval: ShoppingApprovalPolicy = field(default_factory=ShoppingApprovalPolicy)
    spend_caps: SpendCapConfig = field(default_factory=SpendCapConfig)
    kill_switches: ShoppingKillSwitchPolicy = field(
        default_factory=ShoppingKillSwitchPolicy
    )
    merchants: list[dict[str, Any]] = field(default_factory=list)
    adapter_default: str = "dry_run"
    ci_live_forbidden: bool = True
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShoppingProductionConfig":
        ci = data.get("ci") if isinstance(data.get("ci"), dict) else {}
        adapter = data.get("adapter") if isinstance(data.get("adapter"), dict) else {}
        caps_raw = data.get("spend_caps") if isinstance(data.get("spend_caps"), dict) else {}
        return cls(
            skill=str(data.get("skill") or "shopping"),
            profile=str(data.get("profile") or "production"),
            mode=str(data.get("mode") or "dry_run"),
            live_flag=ShoppingLiveFlag.from_dict(
                data.get("live_flag") if isinstance(data.get("live_flag"), dict) else None
            ),
            approval=ShoppingApprovalPolicy.from_dict(
                data.get("approval") if isinstance(data.get("approval"), dict) else None
            ),
            spend_caps=SpendCapConfig.from_dict(caps_raw),
            kill_switches=ShoppingKillSwitchPolicy.from_dict(
                data.get("kill_switches")
                if isinstance(data.get("kill_switches"), dict)
                else None
            ),
            merchants=[
                dict(m)
                for m in (data.get("merchants") or [])
                if isinstance(m, dict)
            ],
            adapter_default=str(adapter.get("default") or "dry_run"),
            ci_live_forbidden=bool(ci.get("live_forbidden", True)),
            raw=dict(data),
        )

    @classmethod
    def from_file(cls, path: Path | str) -> "ShoppingProductionConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("shopping production config must be a JSON object")
        return cls.from_dict(data)

    def hard_approve_mandatory(self) -> bool:
        return (
            self.approval.mandatory
            and self.approval.tier == "hard_approve"
            and self.approval.action_type == "buy"
        )

    def freeze_spending_honored(self) -> bool:
        return (
            self.kill_switches.freeze_spending
            and self.kill_switches.blocks_stale_accepted
        )

    def resolve_execute_mode(
        self,
        *,
        env: Mapping[str, str] | None = None,
    ) -> str:
        """Return ``dry_run`` or ``live``. Default and CI → dry_run."""
        environ = env if env is not None else os.environ
        if self._ci_context(environ):
            return "dry_run"
        mode = (self.mode or "dry_run").strip().lower()
        flag_name = self.live_flag.env
        flag_on = str(environ.get(flag_name, "0")).strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if self.live_flag.requires_both:
            if mode == self.live_flag.config_mode_value and flag_on:
                return "live"
            return "dry_run"
        if mode == self.live_flag.config_mode_value or flag_on:
            return "live"
        return "dry_run"

    def assert_ci_safe(self, *, env: Mapping[str, str] | None = None) -> None:
        """Raise if live charge would be enabled under CI-like env."""
        environ = env if env is not None else os.environ
        if not self.ci_live_forbidden:
            return
        if self._ci_context(environ) and self.resolve_execute_mode(env=environ) == "live":
            raise RuntimeError(
                "shopping live charge forbidden in CI "
                f"(mode={self.mode!r} {self.live_flag.env}={environ.get(self.live_flag.env)!r})"
            )

    @staticmethod
    def _ci_context(environ: Mapping[str, str]) -> bool:
        for key in ("CI", "OPENCLAW_CI", "PERSONAL_AGENT_CI", "GITHUB_ACTIONS"):
            if str(environ.get(key, "")).strip().lower() in _CI_TRUTHY:
                return True
        return False


def load_shopping_production_config(
    path: Path | str | None = None,
) -> ShoppingProductionConfig:
    target = Path(path) if path else DEFAULT_PRODUCTION
    return ShoppingProductionConfig.from_file(target)


def load_shopping_harness_config(path: Path | str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_HARNESS
    data = json.loads(Path(target).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("shopping harness config must be a JSON object")
    return data


__all__ = [
    "DEFAULT_HARNESS",
    "DEFAULT_PRODUCTION",
    "ShoppingApprovalPolicy",
    "ShoppingKillSwitchPolicy",
    "ShoppingLiveFlag",
    "ShoppingProductionConfig",
    "load_shopping_harness_config",
    "load_shopping_production_config",
]
