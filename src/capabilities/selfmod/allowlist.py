"""Path allowlist matching for self-mod writes (INV-SELF-001)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any


def _norm(path: str) -> str:
    """Normalize to forward-slash relative path without leading ./."""
    cleaned = str(path).replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if cleaned.startswith("/"):
        cleaned = cleaned.lstrip("/")
    return PurePosixPath(cleaned).as_posix()


def _match_any(path: str, patterns: list[str]) -> bool:
    target = _norm(path)
    name = PurePosixPath(target).name
    for raw in patterns:
        pat = _norm(raw)
        if fnmatch(target, pat) or fnmatch(name, pat):
            return True
        # Directory-prefix style: "skills/**" already covered by fnmatch;
        # also allow bare directory prefixes like "skills/"
        if pat.endswith("/") and (target == pat.rstrip("/") or target.startswith(pat)):
            return True
    return False


@dataclass(frozen=True)
class AllowlistConfig:
    """Configured path rails for a self-mod workspace."""

    allowed_globs: tuple[str, ...] = (
        "skills/**",
        "config/**",
        "agent-plan/**",
        "tests/**",
        "src/policy/**",
    )
    policy_path_globs: tuple[str, ...] = (
        "src/policy/**",
        "**/approvals*.py",
        "**/kill_switches*.py",
        "**/safety*.py",
        "**/approval-matrix*",
    )
    forbidden_globs: tuple[str, ...] = (
        ".env",
        ".env.*",
        "**/secrets/**",
        "**/credentials/**",
    )
    branch_prefix: str = "cursor/agent-self-"
    diff_ceiling_lines: int = 400
    workspace_root: str = "sample-workspace"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AllowlistConfig":
        return cls(
            allowed_globs=tuple(data.get("allowed_globs") or cls.allowed_globs),
            policy_path_globs=tuple(
                data.get("policy_path_globs") or cls.policy_path_globs
            ),
            forbidden_globs=tuple(data.get("forbidden_globs") or cls.forbidden_globs),
            branch_prefix=str(data.get("branch_prefix") or cls.branch_prefix),
            diff_ceiling_lines=int(
                data.get("diff_ceiling_lines") or cls.diff_ceiling_lines
            ),
            workspace_root=str(data.get("workspace_root") or cls.workspace_root),
        )

    @classmethod
    def from_file(cls, path: Path | str) -> "AllowlistConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw if isinstance(raw, dict) else {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_globs": list(self.allowed_globs),
            "policy_path_globs": list(self.policy_path_globs),
            "forbidden_globs": list(self.forbidden_globs),
            "branch_prefix": self.branch_prefix,
            "diff_ceiling_lines": self.diff_ceiling_lines,
            "workspace_root": self.workspace_root,
        }


def path_allowed(path: str, config: AllowlistConfig | None = None) -> bool:
    """Return True iff *path* is allowlisted and not forbidden."""
    cfg = config or AllowlistConfig()
    target = _norm(path)
    if not target or target in {".", ".."} or ".." in PurePosixPath(target).parts:
        return False
    if _match_any(target, list(cfg.forbidden_globs)):
        return False
    return _match_any(target, list(cfg.allowed_globs))


def is_policy_path(path: str, config: AllowlistConfig | None = None) -> bool:
    """Heuristic: approval-matrix / kill-switch / safety code → policy-change."""
    cfg = config or AllowlistConfig()
    return _match_any(_norm(path), list(cfg.policy_path_globs))


def assert_paths_allowed(
    paths: list[str],
    config: AllowlistConfig | None = None,
) -> None:
    """Raise ValueError listing any path outside the allowlist (fail closed)."""
    cfg = config or AllowlistConfig()
    bad = [p for p in paths if not path_allowed(p, cfg)]
    if bad:
        raise ValueError(f"outside_allowlist:{','.join(_norm(p) for p in bad)}")


@dataclass
class PathCheckResult:
    path: str
    allowed: bool
    policy: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "allowed": self.allowed,
            "policy": self.policy,
            "reason": self.reason,
        }


def classify_paths(
    paths: list[str],
    config: AllowlistConfig | None = None,
) -> list[PathCheckResult]:
    cfg = config or AllowlistConfig()
    out: list[PathCheckResult] = []
    for raw in paths:
        p = _norm(raw)
        allowed = path_allowed(p, cfg)
        policy = is_policy_path(p, cfg) if allowed else False
        reason = ""
        if not allowed:
            if _match_any(p, list(cfg.forbidden_globs)):
                reason = "forbidden_glob"
            else:
                reason = "outside_allowlist"
        out.append(PathCheckResult(path=p, allowed=allowed, policy=policy, reason=reason))
    return out
