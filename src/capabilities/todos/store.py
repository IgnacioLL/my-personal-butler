"""Todo store — canonical task list (Gateway owns state; Android projects)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


class TodoStatus(str, Enum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class TodoSource(str, Enum):
    WHATSAPP = "whatsapp"
    ANDROID = "android"
    AGENT = "agent"


def normalize_title(title: str) -> str:
    """Normalize for dedup: lowercase, collapse whitespace, strip punctuation."""
    t = title.strip().lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


@dataclass
class Todo:
    id: str
    title: str
    status: TodoStatus
    created_at: datetime
    notes: str = ""
    due: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)
    created_from: TodoSource = TodoSource.AGENT
    completed_at: Optional[datetime] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "notes": self.notes,
            "due": self.due.isoformat() if self.due else None,
            "tags": list(self.tags),
            "created_from": self.created_from.value,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Todo":
        due_raw = data.get("due")
        completed_raw = data.get("completed_at")
        created_raw = data.get("created_at")
        return cls(
            id=data["id"],
            title=data["title"],
            status=TodoStatus(data.get("status") or TodoStatus.OPEN.value),
            created_at=datetime.fromisoformat(created_raw) if created_raw else datetime.min,
            notes=data.get("notes") or "",
            due=datetime.fromisoformat(due_raw) if due_raw else None,
            tags=list(data.get("tags") or []),
            created_from=TodoSource(data.get("created_from") or TodoSource.AGENT.value),
            completed_at=datetime.fromisoformat(completed_raw) if completed_raw else None,
            meta=dict(data.get("meta") or {}),
        )


class TodoStore:
    """Create / list / complete todos with optional JSON persistence."""

    def __init__(self, persist_path: Path | str | None = None) -> None:
        self.persist_path = Path(persist_path) if persist_path else None
        self.todos: dict[str, Todo] = {}
        if self.persist_path and self.persist_path.is_file():
            self._load()

    def create(
        self,
        *,
        title: str,
        created_at: datetime,
        created_from: TodoSource | str = TodoSource.AGENT,
        notes: str = "",
        due: datetime | None = None,
        tags: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        todo_id: str | None = None,
    ) -> Todo:
        source = (
            created_from
            if isinstance(created_from, TodoSource)
            else TodoSource(created_from)
        )
        todo = Todo(
            id=todo_id or f"todo-{uuid4().hex[:12]}",
            title=title.strip(),
            status=TodoStatus.OPEN,
            created_at=created_at,
            notes=notes,
            due=due,
            tags=list(tags or []),
            created_from=source,
            meta=dict(meta or {}),
        )
        self.todos[todo.id] = todo
        self._save()
        return todo

    def get(self, todo_id: str) -> Optional[Todo]:
        return self.todos.get(todo_id)

    def list_all(self) -> list[Todo]:
        return sorted(self.todos.values(), key=lambda t: t.created_at)

    def list_open(self) -> list[Todo]:
        return [t for t in self.list_all() if t.status == TodoStatus.OPEN]

    def find_open_duplicate(self, title: str) -> Optional[Todo]:
        """Return an existing open todo with the same normalized title, if any."""
        norm = normalize_title(title)
        if not norm:
            return None
        for todo in self.list_open():
            if normalize_title(todo.title) == norm:
                return todo
        return None

    def complete(
        self,
        todo_id: str,
        *,
        completed_at: datetime,
        completed_from: TodoSource | str = TodoSource.ANDROID,
    ) -> Todo:
        todo = self.todos[todo_id]
        if todo.status == TodoStatus.CANCELLED:
            raise ValueError("cannot complete cancelled todo")
        todo.status = TodoStatus.DONE
        todo.completed_at = completed_at
        source = (
            completed_from
            if isinstance(completed_from, TodoSource)
            else TodoSource(completed_from)
        )
        todo.meta["completed_from"] = source.value
        self._save()
        return todo

    def cancel(self, todo_id: str) -> Todo:
        todo = self.todos[todo_id]
        todo.status = TodoStatus.CANCELLED
        self._save()
        return todo

    def to_dict(self) -> dict[str, Any]:
        return {"todos": [t.to_dict() for t in self.list_all()]}

    def _save(self) -> None:
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist_path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load(self) -> None:
        assert self.persist_path is not None
        data = json.loads(self.persist_path.read_text(encoding="utf-8"))
        self.todos = {t["id"]: Todo.from_dict(t) for t in data.get("todos", [])}
