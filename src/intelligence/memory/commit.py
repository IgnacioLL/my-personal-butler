"""Commit versioned memory files into the personal-butler git repo.

Durable profile + episodic memory live under ``data/memory/`` and are tracked
like skills/config. After an accepted ``memory_update`` (or episodic append),
the runtime stages those paths and creates a local git commit when the store
root sits inside a git worktree.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


MEMORY_REL_PREFIX = "data/memory/"


@dataclass
class MemoryCommitResult:
    """Outcome of a memory git commit attempt."""

    committed: bool
    sha: str | None = None
    message: str = ""
    paths: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "committed": self.committed,
            "sha": self.sha,
            "message": self.message,
            "paths": list(self.paths),
            "skipped_reason": self.skipped_reason,
        }


def find_git_root(start: Path | str) -> Path | None:
    """Walk parents for a ``.git`` directory; return worktree root or None."""
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _rel_memory_paths(repo_root: Path, paths: Sequence[Path | str]) -> list[str]:
    """Return repo-relative posix paths under ``data/memory/`` only."""
    root = repo_root.resolve()
    out: list[str] = []
    for raw in paths:
        path = Path(raw).resolve()
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if not rel.startswith(MEMORY_REL_PREFIX):
            continue
        if ".." in Path(rel).parts:
            continue
        out.append(rel)
    # Stable unique order
    return sorted(dict.fromkeys(out))


class MemoryGitCommitter:
    """Stage + commit ``data/memory/**`` changes in the butler repo.

    Harness/CI temp stores outside any git tree (or outside ``data/memory/``)
    skip silently. Set ``BUTLER_MEMORY_GIT_COMMIT=0`` to disable commits.
    """

    def __init__(
        self,
        *,
        repo_root: Path | str | None = None,
        enabled: bool | None = None,
        record_only: bool = False,
    ) -> None:
        env_flag = os.environ.get("BUTLER_MEMORY_GIT_COMMIT", "1").strip().lower()
        if enabled is None:
            enabled = env_flag not in {"0", "false", "no", "off"}
        self.enabled = bool(enabled)
        self.record_only = bool(record_only)
        self.repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self.history: list[MemoryCommitResult] = []

    def commit_paths(
        self,
        paths: Sequence[Path | str],
        *,
        message: str,
        cwd_hint: Path | str | None = None,
    ) -> MemoryCommitResult:
        if not self.enabled:
            result = MemoryCommitResult(
                committed=False,
                message=message,
                skipped_reason="disabled",
            )
            self.history.append(result)
            return result

        hint = Path(cwd_hint).resolve() if cwd_hint is not None else None
        root = self.repo_root
        if root is None and hint is not None:
            root = find_git_root(hint)
        if root is None and paths:
            root = find_git_root(Path(paths[0]))
        if root is None:
            result = MemoryCommitResult(
                committed=False,
                message=message,
                skipped_reason="no_git_root",
            )
            self.history.append(result)
            return result

        rel_paths = _rel_memory_paths(root, paths)
        if not rel_paths:
            result = MemoryCommitResult(
                committed=False,
                message=message,
                skipped_reason="no_versioned_memory_paths",
            )
            self.history.append(result)
            return result

        if self.record_only:
            fake_sha = f"record-{len(self.history) + 1:04d}"
            result = MemoryCommitResult(
                committed=True,
                sha=fake_sha,
                message=message,
                paths=rel_paths,
            )
            self.history.append(result)
            return result

        try:
            add = subprocess.run(
                ["git", "add", "--", *rel_paths],
                cwd=str(root),
                check=False,
                capture_output=True,
                text=True,
            )
            if add.returncode != 0:
                result = MemoryCommitResult(
                    committed=False,
                    message=message,
                    paths=rel_paths,
                    skipped_reason=f"git_add_failed:{add.stderr.strip() or add.returncode}",
                )
                self.history.append(result)
                return result

            # Skip empty commits (no staged memory delta).
            status = subprocess.run(
                ["git", "diff", "--cached", "--quiet", "--", *rel_paths],
                cwd=str(root),
                check=False,
                capture_output=True,
                text=True,
            )
            if status.returncode == 0:
                result = MemoryCommitResult(
                    committed=False,
                    message=message,
                    paths=rel_paths,
                    skipped_reason="no_changes",
                )
                self.history.append(result)
                return result

            commit = subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    message,
                    "--",
                    *rel_paths,
                ],
                cwd=str(root),
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": os.environ.get(
                        "BUTLER_MEMORY_GIT_AUTHOR_NAME", "Butler Memory"
                    ),
                    "GIT_AUTHOR_EMAIL": os.environ.get(
                        "BUTLER_MEMORY_GIT_AUTHOR_EMAIL", "memory@butler.local"
                    ),
                    "GIT_COMMITTER_NAME": os.environ.get(
                        "BUTLER_MEMORY_GIT_AUTHOR_NAME", "Butler Memory"
                    ),
                    "GIT_COMMITTER_EMAIL": os.environ.get(
                        "BUTLER_MEMORY_GIT_AUTHOR_EMAIL", "memory@butler.local"
                    ),
                },
            )
            if commit.returncode != 0:
                result = MemoryCommitResult(
                    committed=False,
                    message=message,
                    paths=rel_paths,
                    skipped_reason=(
                        f"git_commit_failed:{commit.stderr.strip() or commit.returncode}"
                    ),
                )
                self.history.append(result)
                return result

            sha_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                check=False,
                capture_output=True,
                text=True,
            )
            sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
            result = MemoryCommitResult(
                committed=True,
                sha=sha,
                message=message,
                paths=rel_paths,
            )
            self.history.append(result)
            return result
        except OSError as exc:
            result = MemoryCommitResult(
                committed=False,
                message=message,
                paths=rel_paths,
                skipped_reason=f"git_os_error:{exc}",
            )
            self.history.append(result)
            return result


__all__ = [
    "MEMORY_REL_PREFIX",
    "MemoryCommitResult",
    "MemoryGitCommitter",
    "find_git_root",
]
