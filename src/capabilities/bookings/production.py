"""Production bookings skill config — dry-run default; live behind explicit flag.

CI must never resolve to live execute. Stub portal remains the CI path.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PRODUCTION = ROOT / "config" / "production" / "bookings.json"
DEFAULT_HARNESS = ROOT / "config" / "bookings.harness.json"

# Env values that mean "this is CI / harness" — live must refuse.
_CI_TRUTHY = {"1", "true", "yes", "ci", "harness"}


@dataclass(frozen=True)
class BookingLiveFlag:
    env: str = "BOOKINGS_LIVE"
    config_mode_value: str = "live"
    requires_both: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BookingLiveFlag":
        raw = data or {}
        return cls(
            env=str(raw.get("env") or "BOOKINGS_LIVE"),
            config_mode_value=str(raw.get("config_mode_value") or "live"),
            requires_both=bool(raw.get("requires_both", True)),
        )


@dataclass(frozen=True)
class BookingApprovalPolicy:
    tier: str = "hard_approve"
    mandatory: bool = True
    action_type: str = "book"
    card_fields: tuple[str, ...] = (
        "shop",
        "service",
        "date_time",
        "estimated_price",
        "cancellation_policy",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BookingApprovalPolicy":
        raw = data or {}
        fields = raw.get("card_fields") or [
            "shop",
            "service",
            "date_time",
            "estimated_price",
            "cancellation_policy",
        ]
        return cls(
            tier=str(raw.get("tier") or "hard_approve"),
            mandatory=bool(raw.get("mandatory", True)),
            action_type=str(raw.get("action_type") or "book"),
            card_fields=tuple(str(f) for f in fields),
        )


@dataclass(frozen=True)
class BookingBrowserPolicy:
    enabled: bool = True
    profile_name: str = "bookings"
    provider_class: str = "booksy"
    separate_from_personal: bool = True
    allowed_hosts: tuple[str, ...] = ("booksy.com", "www.booksy.com")
    max_book_retries: int = 1
    no_aggressive_retry_book: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BookingBrowserPolicy":
        raw = data or {}
        hosts = raw.get("allowed_hosts") or ["booksy.com", "www.booksy.com"]
        return cls(
            enabled=bool(raw.get("enabled", True)),
            profile_name=str(raw.get("profile_name") or "bookings"),
            provider_class=str(raw.get("provider_class") or "booksy"),
            separate_from_personal=bool(raw.get("separate_from_personal", True)),
            allowed_hosts=tuple(str(h) for h in hosts),
            max_book_retries=int(raw.get("max_book_retries") or 1),
            no_aggressive_retry_book=bool(raw.get("no_aggressive_retry_book", True)),
        )


@dataclass
class BookingProductionConfig:
    """Loaded production bookings profile (OpenClaw skill + Gateway)."""

    skill: str = "bookings"
    profile: str = "production"
    mode: str = "dry_run"
    live_flag: BookingLiveFlag = field(default_factory=BookingLiveFlag)
    approval: BookingApprovalPolicy = field(default_factory=BookingApprovalPolicy)
    browser: BookingBrowserPolicy = field(default_factory=BookingBrowserPolicy)
    providers: list[dict[str, Any]] = field(default_factory=list)
    calendar_writeback: bool = True
    ci_live_forbidden: bool = True
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BookingProductionConfig":
        ci = data.get("ci") if isinstance(data.get("ci"), dict) else {}
        return cls(
            skill=str(data.get("skill") or "bookings"),
            profile=str(data.get("profile") or "production"),
            mode=str(data.get("mode") or "dry_run"),
            live_flag=BookingLiveFlag.from_dict(
                data.get("live_flag") if isinstance(data.get("live_flag"), dict) else None
            ),
            approval=BookingApprovalPolicy.from_dict(
                data.get("approval") if isinstance(data.get("approval"), dict) else None
            ),
            browser=BookingBrowserPolicy.from_dict(
                data.get("browser") if isinstance(data.get("browser"), dict) else None
            ),
            providers=[
                dict(p)
                for p in (data.get("providers") or [])
                if isinstance(p, dict)
            ],
            calendar_writeback=bool(data.get("calendar_writeback", True)),
            ci_live_forbidden=bool(ci.get("live_forbidden", True)),
            raw=dict(data),
        )

    @classmethod
    def from_file(cls, path: Path | str) -> "BookingProductionConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("bookings production config must be a JSON object")
        return cls.from_dict(data)

    def hard_approve_mandatory(self) -> bool:
        return (
            self.approval.mandatory
            and self.approval.tier == "hard_approve"
            and self.approval.action_type == "book"
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
        """Raise if live execute would be enabled under CI-like env."""
        environ = env if env is not None else os.environ
        if not self.ci_live_forbidden:
            return
        if self._ci_context(environ) and self.resolve_execute_mode(env=environ) == "live":
            raise RuntimeError(
                "bookings live execute forbidden in CI "
                f"(mode={self.mode!r} {self.live_flag.env}={environ.get(self.live_flag.env)!r})"
            )

    @staticmethod
    def _ci_context(environ: Mapping[str, str]) -> bool:
        for key in ("CI", "OPENCLAW_CI", "PERSONAL_AGENT_CI", "GITHUB_ACTIONS"):
            if str(environ.get(key, "")).strip().lower() in _CI_TRUTHY:
                return True
        return False


def load_booking_production_config(
    path: Path | str | None = None,
) -> BookingProductionConfig:
    target = Path(path) if path else DEFAULT_PRODUCTION
    return BookingProductionConfig.from_file(target)


def load_booking_harness_config(path: Path | str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_HARNESS
    data = json.loads(Path(target).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("bookings harness config must be a JSON object")
    return data


__all__ = [
    "BookingApprovalPolicy",
    "BookingBrowserPolicy",
    "BookingLiveFlag",
    "BookingProductionConfig",
    "DEFAULT_HARNESS",
    "DEFAULT_PRODUCTION",
    "load_booking_harness_config",
    "load_booking_production_config",
]
