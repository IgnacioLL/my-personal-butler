# Todos

## Purpose

Canonical task list for actionable items that are not pure time alarms.

Examples:

- “Buy protein powder”
- “Ask dentist about appointment”
- “Pack for trip”

## Source of truth

Gateway/task store is canonical. Android renders and completes. WhatsApp creates/updates via natural language.

## Fields (v1)

- title
- notes (optional)
- due (optional)
- status (open/done/cancelled)
- tags (diet, travel, errands…)
- created_from (whatsapp/android/agent)

## Agent behaviors

- Turn vague chat into a todo when action is deferred
- Suggest due dates when calendar is busy
- Avoid duplicating an existing open todo
- After booking/purchase approval, auto-complete related todos

## Acceptance criteria

- [ ] “Add a todo…” from WhatsApp appears on Android
- [ ] Completing on Android is visible to the agent
- [ ] Agent doesn’t recreate duplicates aggressively
