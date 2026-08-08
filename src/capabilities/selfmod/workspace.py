"""Fixture workspace copy for self-mod propose/apply (not the live main tree)."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def _file_sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


@dataclass
class FileSnapshot:
    path: str
    content: str
    sha: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha": self.sha, "bytes": len(self.content)}


@dataclass
class WorkspaceSnapshot:
    """Point-in-time tree hash used as rollback_ref parent."""

    ref: str
    files: dict[str, str]  # path → content
    branch: str = "main"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "branch": self.branch,
            "files": sorted(self.files.keys()),
            "file_count": len(self.files),
        }


@dataclass
class AppliedPatch:
    apply_id: str
    approval_id: Optional[str]
    branch: str
    rollback_ref: str
    commit_sha: str
    files_touched: list[str]
    diff_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "apply_id": self.apply_id,
            "approval_id": self.approval_id,
            "branch": self.branch,
            "rollback_ref": self.rollback_ref,
            "commit_sha": self.commit_sha,
            "files_touched": list(self.files_touched),
            "diff_text": self.diff_text,
        }


@dataclass
class FixtureWorkspace:
    """Mutable copy of fixtures/selfmod/sample-workspace for harness tests."""

    root: Path
    branch: str = "main"
    history: list[WorkspaceSnapshot] = field(default_factory=list)
    applied: list[AppliedPatch] = field(default_factory=list)
    _apply_seq: int = 0

    @classmethod
    def from_fixture(
        cls,
        fixture_dir: Path | str,
        *,
        dest: Path | str,
    ) -> "FixtureWorkspace":
        src = Path(fixture_dir)
        dst = Path(dest)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        ws = cls(root=dst)
        ws.history.append(ws.snapshot(branch="main"))
        return ws

    def snapshot(self, *, branch: str | None = None) -> WorkspaceSnapshot:
        files = self.read_all()
        digest = hashlib.sha256()
        for path in sorted(files):
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(files[path].encode("utf-8"))
            digest.update(b"\0")
        ref = digest.hexdigest()[:16]
        snap = WorkspaceSnapshot(
            ref=ref,
            files=files,
            branch=branch if branch is not None else self.branch,
        )
        return snap

    def read_all(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if not self.root.exists():
            return out
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            out[rel] = path.read_text(encoding="utf-8")
        return out

    def read(self, rel_path: str) -> str:
        target = self._resolve(rel_path)
        return target.read_text(encoding="utf-8")

    def exists(self, rel_path: str) -> bool:
        return self._resolve(rel_path).is_file()

    def working_tree_clean(self) -> bool:
        """True when tree matches latest history snapshot (pre-Accept / after Deny)."""
        if not self.history:
            return True
        current = self.read_all()
        return current == self.history[-1].files

    def dirty_paths(self) -> list[str]:
        if not self.history:
            return sorted(self.read_all().keys())
        baseline = self.history[-1].files
        current = self.read_all()
        dirty: list[str] = []
        for path in sorted(set(baseline) | set(current)):
            if baseline.get(path) != current.get(path):
                dirty.append(path)
        return dirty

    def current_ref(self) -> str:
        return self.snapshot().ref

    def rollback_ref(self) -> str:
        """Parent commit SHA / tree ref before the next apply."""
        if self.history:
            return self.history[-1].ref
        return self.current_ref()

    def write_file(self, rel_path: str, content: str) -> None:
        target = self._resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def apply_files(
        self,
        files: dict[str, str],
        *,
        branch: str,
        approval_id: str | None = None,
        diff_text: str = "",
    ) -> AppliedPatch:
        """Write files onto a branch copy and record rollback + commit refs."""
        parent = self.rollback_ref()
        self.branch = branch
        for rel, content in files.items():
            self.write_file(rel, content)
        snap = self.snapshot(branch=branch)
        self.history.append(snap)
        self._apply_seq += 1
        patch = AppliedPatch(
            apply_id=f"apply-{self._apply_seq}",
            approval_id=approval_id,
            branch=branch,
            rollback_ref=parent,
            commit_sha=snap.ref,
            files_touched=sorted(files.keys()),
            diff_text=diff_text,
        )
        self.applied.append(patch)
        return patch

    def _resolve(self, rel_path: str) -> Path:
        cleaned = rel_path.replace("\\", "/").lstrip("/")
        if ".." in Path(cleaned).parts:
            raise ValueError(f"path_escape:{rel_path}")
        return self.root / cleaned

    def status(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "branch": self.branch,
            "clean": self.working_tree_clean(),
            "dirty_paths": self.dirty_paths(),
            "rollback_ref": self.rollback_ref(),
            "apply_count": len(self.applied),
            "history_len": len(self.history),
        }
