---
name: personal-todos
description: "Add, list, complete, and deduplicate personal todos; sync with the Android companion projection API."
metadata: { "openclaw": { "requires": { "config": ["skills.entries.personal-todos.enabled"] } } }
---

# Personal todos

Canonical todo list owned by the Gateway; Android companion **projects** the same ids/titles/status.

## When to use

- User says “add todo …”, “buy oat milk”, or voice note with todo intent.
- User completes or lists open tasks.
- Diet/grocery flows add tagged todos (`grocery`, `diet`).

## Tools

| Tool | Tier | Harness module |
| --- | --- | --- |
| `todo_add` | Auto | `TodoService.create_from_utterance` |
| `todo_complete` | Auto | `TodoStore.complete` |
| `todo_read` | Auto | `TodoStore.list_open` / `list_all` |
| `todo_cancel` | Auto | `TodoStore.cancel` |

### `todo_add` payload

```json
{
  "title": "buy oat milk",
  "tags": ["grocery"],
  "created_from": "whatsapp",
  "recipient": "+15550001111"
}
```

### `todo_read` payload

```json
{
  "status": "open",
  "tag": "grocery"
}
```

## Dedup

Near-identical open titles collapse to one row (`todo_dedup` outbound). Normalization: `TodoStore.find_open_duplicate` / `normalize_title`.

## Android projection

Production: OpenClaw Android node mirrors `list_todos`, `get_todo`, `complete_todo` — see PROD-05 pairing docs.

Harness double: `channels.android.projection.AndroidTodoProjectionApi` must match store equality (E2E-03 gate).

## References

- `{baseDir}/references/harness-map.md`
- `agent-plan/capabilities/todos.md`
