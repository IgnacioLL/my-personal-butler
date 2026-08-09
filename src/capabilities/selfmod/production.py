"""Production self-mod config for this repo (PROD-09).

CI keeps using fixtures/selfmod + config/selfmod.harness.json.
This module loads the real-repo allowlist and skill paths for Gateway wiring.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from capabilities.selfmod.allowlist import (
    AllowlistConfig,
    classify_paths,
    is_policy_path,
    path_allowed,
)

ROOT = Path(__file__).resolve().parents[3]
PROD_ALLOWLIST_PATH = ROOT / "config" / "selfmod.allowlist.production.json"
PROD_CONFIG_PATH = ROOT / "config" / "selfmod.production.json"
PROD_SKILL_PATH = ROOT / "src" / "skills" / "self-modification" / "SKILL.md"
HARNESS_CONFIG_PATH = ROOT / "config" / "selfmod.harness.json"
FIXTURE_ALLOWLIST_PATH = ROOT / "fixtures" / "selfmod" / "allowlist.json"


@dataclass(frozen=True)
class ProductionSelfModConfig:
    """Resolved production self-mod settings (no live apply side effects)."""

    allowlist: AllowlistConfig
    raw: dict[str, Any]
    allowlist_path: Path
    config_path: Path
    skill_path: Path

    @property
    def mode(self) -> str:
        return str(self.raw.get("mode") or "production_repo")

    @property
    def skill_name(self) -> str:
        return str(self.raw.get("skill") or "self_modification")

    @property
    def branch_prefix(self) -> str:
        return self.allowlist.branch_prefix

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "skill": self.skill_name,
            "allowlist_path": str(self.allowlist_path.relative_to(ROOT)),
            "config_path": str(self.config_path.relative_to(ROOT)),
            "skill_path": str(self.skill_path.relative_to(ROOT)),
            "branch_prefix": self.branch_prefix,
            "diff_ceiling_lines": self.allowlist.diff_ceiling_lines,
            "allowed_globs": list(self.allowlist.allowed_globs),
            "forbidden_globs": list(self.allowlist.forbidden_globs),
            "policy_path_globs": list(self.allowlist.policy_path_globs),
            "approval": dict(self.raw.get("approval") or {}),
            "rollback": dict(self.raw.get("rollback") or {}),
        }


def load_production_allowlist(
    path: Path | str | None = None,
) -> AllowlistConfig:
    """Load the production allowlist for this repository."""
    target = Path(path) if path is not None else PROD_ALLOWLIST_PATH
    if not target.is_file():
        raise FileNotFoundError(f"missing_production_allowlist:{target}")
    return AllowlistConfig.from_file(target)


def load_production_config(
    path: Path | str | None = None,
) -> ProductionSelfModConfig:
    """Load production config + allowlist; verify skill file exists."""
    cfg_path = Path(path) if path is not None else PROD_CONFIG_PATH
    if not cfg_path.is_file():
        raise FileNotFoundError(f"missing_production_config:{cfg_path}")
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("production_config_not_object")

    allow_rel = str(raw.get("allowlist") or "config/selfmod.allowlist.production.json")
    allow_path = (ROOT / allow_rel).resolve()
    if not str(allow_path).startswith(str(ROOT.resolve())):
        raise ValueError("allowlist_path_escape")
    allowlist = load_production_allowlist(allow_path)

    skill_rel = str(raw.get("skill_path") or "src/skills/self-modification/SKILL.md")
    skill_path = (ROOT / skill_rel).resolve()
    if not skill_path.is_file():
        raise FileNotFoundError(f"missing_production_skill:{skill_path}")

    # Prefer config branch/ceiling when present; keep allowlist as source of truth
    # for globs (AllowlistConfig already loaded those from the allowlist file).
    return ProductionSelfModConfig(
        allowlist=allowlist,
        raw=raw,
        allowlist_path=allow_path,
        config_path=cfg_path.resolve(),
        skill_path=skill_path,
    )


def production_skill_present() -> bool:
    return PROD_SKILL_PATH.is_file()


def production_paths_smoke(cfg: AllowlistConfig | None = None) -> dict[str, Any]:
    """Deterministic allow/deny table for CI (no workspace writes)."""
    allow = cfg or load_production_allowlist()
    must_allow = [
        "src/skills/self-modification/SKILL.md",
        "docs/ci-gates.md",
        "config/selfmod.production.json",
        "config/selfmod.allowlist.production.json",
        "agent-plan/capabilities/self-modification.md",
        "scripts/test-ci.sh",
        "src/policy/approvals.py",
        "data/memory/profile.json",
        "data/memory/episodes.jsonl",
        "README.md",
        "status.md",
    ]
    must_deny = [
        ".env",
        ".env.local",
        "secrets/api_key.txt",
        "credentials/google.json",
        "config/gateway.local.yaml",
        "config/harness.local.env",
        "data/secrets/token.txt",
        "data/approvals/items.json",
        "data/todos/items.json",
        "src/runtime/gateway.py",
        "../../etc/passwd",
        ".git/config",
    ]
    allowed_ok = all(path_allowed(p, allow) for p in must_allow)
    denied_ok = all(not path_allowed(p, allow) for p in must_deny)
    policy_ok = is_policy_path("src/policy/approvals.py", allow) and is_policy_path(
        "agent-plan/trust-and-safety/approval-matrix.md", allow
    )
    normal_skill = not is_policy_path(
        "src/skills/self-modification/SKILL.md", allow
    )
    classified = classify_paths(
        ["src/policy/kill_switches.py", "docs/ci-gates.md", ".env"],
        allow,
    )
    return {
        "allowed_ok": allowed_ok,
        "denied_ok": denied_ok,
        "policy_ok": policy_ok and normal_skill,
        "must_allow": must_allow,
        "must_deny": must_deny,
        "classified": [c.to_dict() for c in classified],
        "ok": allowed_ok and denied_ok and policy_ok and normal_skill,
    }


__all__ = [
    "FIXTURE_ALLOWLIST_PATH",
    "HARNESS_CONFIG_PATH",
    "PROD_ALLOWLIST_PATH",
    "PROD_CONFIG_PATH",
    "PROD_SKILL_PATH",
    "ProductionSelfModConfig",
    "load_production_allowlist",
    "load_production_config",
    "production_paths_smoke",
    "production_skill_present",
]
