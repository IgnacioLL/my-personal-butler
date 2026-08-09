# Harness map — personal-todos

| Tool | Action type | Primary code |
| --- | --- | --- |
| `todo_add` | `todo_add` | `capabilities.todos.service.TodoService` |
| `todo_complete` | `todo_complete` | `TodoStore.complete` |
| `todo_read` | `todo_read` | `TodoStore.list_open` |
| `todo_cancel` | `todo_cancel` | `TodoStore.cancel` |

Gateway: `ActionGateway._add_todo`, `_complete_todo`, `_todo_read`.

E2E-03 gate: WhatsApp add → Android projection equality → complete sync.

Integration IDs: `integration.todo.*` in `run_test_ci.py`.

Call-mode: `todo_read` allowed; `todo_add` / `todo_complete` not on voice allowlist.
