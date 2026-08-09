"""File-backed personal memory: hot profile + episodic JSON store.

Canonical production paths live under ``data/memory/`` in this repository and
are git-committed after durable writes (see ``intelligence.memory.commit``).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from intelligence.memory.commit import MemoryCommitResult, MemoryGitCommitter
from intelligence.memory.secrets import validate_no_secrets

PROFILE_FILENAME = "profile.json"
EPISODES_FILENAME = "episodes.jsonl"

HOT_SECTIONS = ("identity", "preferences", "goals")
REPO_MEMORY_DIR = Path("data") / "memory"


def default_profile_template() -> dict[str, Any]:
    """Hermes-inspired curated USER profile — durable facts only (no secrets)."""
    return {
        "version": 1,
        "identity": {
            "name": "",
            "language": "en",
            "household": "",
            "timezone": "UTC",
            "people": [],
        },
        "preferences": {
            "food_likes": [],
            "food_dislikes": [],
            "allergies": [],
            "quiet_hours": {"start": "22:00", "end": "07:30"},
            "brands": [],
            "haircut_style": "",
            "booking_windows": [],
        },
        "goals": {
            "diet_phase": "",
            "trip_wishlist": [],
            "habit_targets": [],
        },
        "procedures": {
            "spend_approval": "",
            "booksy_flow": "",
        },
    }


class MemoryStore:
    """Hot profile (always loadable) + episodic append-only log on disk."""

    def __init__(
        self,
        root: Path | str,
        *,
        committer: MemoryGitCommitter | None = None,
        auto_commit: bool | None = None,
    ) -> None:
        self.root = Path(root)
        self.profile_path = self.root / PROFILE_FILENAME
        self.episodes_path = self.root / EPISODES_FILENAME
        self._profile: dict[str, Any] | None = None
        self.committer = committer
        # Default: commit when store is under repo data/memory/ or committer set.
        if auto_commit is None:
            auto_commit = committer is not None or self._looks_like_repo_memory()
        self.auto_commit = bool(auto_commit)
        self.last_commit: MemoryCommitResult | None = None

    def _looks_like_repo_memory(self) -> bool:
        try:
            parts = self.root.resolve().parts
        except OSError:
            return False
        return len(parts) >= 2 and parts[-2] == "data" and parts[-1] == "memory"

    def attach_committer(self, committer: MemoryGitCommitter | None) -> None:
        """Wire (or clear) the git committer used after durable writes."""
        self.committer = committer
        if committer is not None:
            self.auto_commit = True

    @classmethod
    def seed(
        cls,
        root: Path | str,
        template: dict[str, Any] | None = None,
        *,
        committer: MemoryGitCommitter | None = None,
        auto_commit: bool | None = None,
        commit_message: str | None = None,
    ) -> "MemoryStore":
        """Create a fresh store directory with profile template."""
        store = cls(root, committer=committer, auto_commit=auto_commit)
        store.root.mkdir(parents=True, exist_ok=True)
        profile = template if template is not None else default_profile_template()
        validate_no_secrets(profile)
        store.profile_path.write_text(
            json.dumps(profile, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if not store.episodes_path.exists():
            store.episodes_path.write_text("", encoding="utf-8")
        store._profile = profile
        if commit_message:
            store._commit_memory_paths(
                [store.profile_path, store.episodes_path],
                message=commit_message,
            )
        return store

    @classmethod
    def seed_from_fixture(
        cls,
        root: Path | str,
        fixture_path: Path | str,
        *,
        committer: MemoryGitCommitter | None = None,
        auto_commit: bool | None = None,
    ) -> "MemoryStore":
        """Seed a store at *root* from a fixture JSON template."""
        data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        return cls.seed(
            root,
            template=data,
            committer=committer,
            auto_commit=auto_commit,
        )

    @classmethod
    def open(
        cls,
        root: Path | str,
        *,
        committer: MemoryGitCommitter | None = None,
        auto_commit: bool | None = None,
    ) -> "MemoryStore":
        store = cls(root, committer=committer, auto_commit=auto_commit)
        if not store.profile_path.exists():
            raise FileNotFoundError(f"missing profile at {store.profile_path}")
        return store

    @classmethod
    def open_repo_memory(
        cls,
        repo_root: Path | str,
        *,
        committer: MemoryGitCommitter | None = None,
    ) -> "MemoryStore":
        """Open the versioned ``data/memory`` store inside this repository."""
        root = Path(repo_root) / REPO_MEMORY_DIR
        git = committer or MemoryGitCommitter(repo_root=repo_root)
        return cls.open(root, committer=git, auto_commit=True)

    def load_hot_profile(self) -> dict[str, Any]:
        """Identity + preferences + goals — compact facts for every turn."""
        raw = json.loads(self.profile_path.read_text(encoding="utf-8"))
        hot: dict[str, Any] = {}
        for section in HOT_SECTIONS:
            if section in raw:
                hot[section] = raw[section]
        self._profile = raw
        return hot

    def load_full_profile(self) -> dict[str, Any]:
        if self._profile is None:
            self._profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
        return dict(self._profile)

    def hot_context_lines(self) -> list[str]:
        """Trace-friendly lines for turn assembly (no episodic dump)."""
        hot = self.load_hot_profile()
        lines: list[str] = []
        identity = hot.get("identity", {})
        if identity.get("name"):
            lines.append(f"User: {identity['name']}")
        if identity.get("household"):
            lines.append(f"Household: {identity['household']}")
        prefs = hot.get("preferences", {})
        if prefs.get("allergies"):
            lines.append(f"Allergies: {', '.join(prefs['allergies'])}")
        if prefs.get("food_dislikes"):
            lines.append(f"Food dislikes: {', '.join(prefs['food_dislikes'])}")
        goals = hot.get("goals", {})
        if goals.get("diet_phase"):
            lines.append(f"Diet phase: {goals['diet_phase']}")
        return lines

    def planning_constraints(self) -> dict[str, Any]:
        """Diet / planner input assembly — constraints from hot profile."""
        hot = self.load_hot_profile()
        prefs = hot.get("preferences", {})
        goals = hot.get("goals", {})
        return {
            "allergies": list(prefs.get("allergies") or []),
            "food_dislikes": list(prefs.get("food_dislikes") or []),
            "food_likes": list(prefs.get("food_likes") or []),
            "diet_phase": goals.get("diet_phase") or "",
            "quiet_hours": prefs.get("quiet_hours") or {},
        }

    def remember(
        self,
        section: str,
        key: str,
        value: Any,
        *,
        explicit: bool = True,
    ) -> None:
        """Persist a durable fact into the hot profile (explicit 'remember…')."""
        validate_no_secrets(value, path=f"{section}.{key}")
        profile = self.load_full_profile()
        if section not in profile:
            profile[section] = {}
        bucket = profile[section]
        if not isinstance(bucket, dict):
            raise ValueError(f"section {section!r} is not a mapping")
        bucket[key] = value
        self._write_profile(profile)
        self._commit_memory_paths(
            [self.profile_path],
            message=f"memory: update {section}.{key}",
        )

    def append_episode(self, summary: str, *, tags: list[str] | None = None) -> str:
        """Append one episodic memory line (search on demand, not hot)."""
        validate_no_secrets(summary, path="episode.summary")
        if tags:
            validate_no_secrets(tags, path="episode.tags")
        episode_id = str(uuid4())
        record = {
            "id": episode_id,
            "at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "tags": tags or [],
        }
        validate_no_secrets(record)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.episodes_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._commit_memory_paths(
            [self.episodes_path],
            message=f"memory: episode {episode_id}",
        )
        return episode_id

    def read_episodes(
        self,
        *,
        limit: int = 50,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.episodes_path.exists():
            return []
        episodes: list[dict[str, Any]] = []
        for line in self.episodes_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if tag is not None and tag not in record.get("tags", []):
                continue
            episodes.append(record)
        if limit > 0:
            return episodes[-limit:]
        return episodes

    def _write_profile(self, profile: dict[str, Any]) -> None:
        validate_no_secrets(profile)
        self.root.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(
            json.dumps(profile, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._profile = profile

    def _commit_memory_paths(
        self,
        paths: list[Path],
        *,
        message: str,
    ) -> MemoryCommitResult | None:
        """Commit versioned memory files when auto_commit is enabled."""
        if not self.auto_commit:
            return None
        committer = self.committer or MemoryGitCommitter()
        result = committer.commit_paths(
            paths,
            message=message,
            cwd_hint=self.root,
        )
        self.last_commit = result
        return result

    def copy_template_from(self, template_path: Path | str) -> None:
        """Seed this store from an on-disk fixture template."""
        template = json.loads(Path(template_path).read_text(encoding="utf-8"))
        validate_no_secrets(template)
        self._write_profile(template)
        if not self.episodes_path.exists():
            self.episodes_path.write_text("", encoding="utf-8")
        self._commit_memory_paths(
            [self.profile_path, self.episodes_path],
            message="memory: seed profile template",
        )

    def wipe(self) -> None:
        """Remove store directory (harness cleanup)."""
        if self.root.exists():
            shutil.rmtree(self.root)
