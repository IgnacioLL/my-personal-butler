"""Gateway profile paths for harness and always-on hosting (stdlib JSON + env).

YAML templates live under config/ for human editing; harness loads JSON profiles.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_HARNESS_PROFILE = Path("config/gateway.harness.json")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_profile_path(path: Path | str | None = None) -> Path:
    """Resolve gateway profile from explicit path or HARNESS_GATEWAY_PROFILE env."""
    if path is not None:
        candidate = Path(path)
    else:
        env = os.environ.get("HARNESS_GATEWAY_PROFILE", "")
        candidate = Path(env) if env else DEFAULT_HARNESS_PROFILE

    if not candidate.is_absolute():
        candidate = _repo_root() / candidate
    return candidate


def load_gateway_profile(path: Path | str | None = None) -> dict[str, Any]:
    """Load harness-friendly gateway profile (JSON)."""
    profile_path = resolve_profile_path(path)
    if profile_path.suffix in {".yaml", ".yml"}:
        # YAML is documentation-only in CI; fall back to bundled harness JSON.
        profile_path = _repo_root() / DEFAULT_HARNESS_PROFILE
    if not profile_path.exists():
        raise FileNotFoundError(f"gateway profile not found: {profile_path}")
    return json.loads(profile_path.read_text(encoding="utf-8"))


def gateway_data_paths(profile: dict[str, Any] | None = None) -> dict[str, Path]:
    """Return resolved data paths for approvals, memory, and backup roots."""
    root = _repo_root()
    data = profile or load_gateway_profile()
    paths = data.get("paths", {})
    data_root = Path(data.get("data_root", "./data"))
    if not data_root.is_absolute():
        data_root = root / data_root

    approvals = Path(paths.get("approvals", data_root / "approvals" / "items.json"))
    if not approvals.is_absolute():
        approvals = root / approvals

    memory = Path(paths.get("memory", data_root / "memory"))
    if not memory.is_absolute():
        memory = root / memory

    backup_root = Path(paths.get("backup_root", data_root.parent / "backups"))
    if not backup_root.is_absolute():
        backup_root = root / backup_root

    return {
        "data_root": data_root,
        "approvals": approvals,
        "memory": memory,
        "backup_root": backup_root,
        "config": root / "config",
    }
