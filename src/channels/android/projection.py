"""Android projection API double — list/get/complete todos for paired node.

Gateway owns canonical state; this API reflects the same ids/titles/statuses
that WhatsApp-created todos produce. Used by integration tests and E2E-03 prep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from capabilities.todos.store import Todo, TodoSource, TodoStatus, TodoStore
from harness.clock import FakeClock
from policy.action_gateway import ActionGateway


@dataclass(frozen=True)
class TodoProjection:
    """Android-facing todo shape (v1: id, title, status)."""

    id: str
    title: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title, "status": self.status}


def _project(todo: Todo) -> TodoProjection:
    return TodoProjection(id=todo.id, title=todo.title, status=todo.status.value)


class AndroidProjectionApi:
    """API-level Android node simulation for todo sync."""

    def __init__(
        self,
        store: TodoStore,
        clock: FakeClock,
        *,
        gateway: ActionGateway | None = None,
    ) -> None:
        self.store = store
        self.clock = clock
        self.gateway = gateway
        if self.gateway is not None:
            self.gateway.todos = self.store

    def list_todos(self, *, status: str | None = None) -> list[TodoProjection]:
        todos = self.store.list_all()
        if status is not None:
            todos = [t for t in todos if t.status.value == status]
        return [_project(t) for t in todos]

    def get_todo(self, todo_id: str) -> Optional[TodoProjection]:
        todo = self.store.get(todo_id)
        return _project(todo) if todo else None

    def complete_todo(self, todo_id: str) -> TodoProjection:
        """Mark todo done — reflects in canonical agent store."""
        if self.gateway is not None:
            result = self.gateway.propose(
                "todo_complete",
                f"Complete todo {todo_id}",
                {"todo_id": todo_id, "completed_from": TodoSource.ANDROID.value},
            )
            if not result.ok or not result.executed:
                raise ValueError(result.reason)
            todo = self.store.get(todo_id)
            if todo is None:
                raise ValueError("todo_not_found_after_complete")
            return _project(todo)

        todo = self.store.complete(
            todo_id,
            completed_at=self.clock.now(),
            completed_from=TodoSource.ANDROID,
        )
        return _project(todo)

    def snapshot(self) -> dict[str, Any]:
        return {
            "todos": [p.to_dict() for p in self.list_todos()],
            "open_count": len(self.store.list_open()),
        }
