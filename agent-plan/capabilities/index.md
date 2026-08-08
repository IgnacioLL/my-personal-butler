# Capabilities

Things the agent can **do**. Each capability is a thin vertical slice with tools, UX, and approval rules.

## Priority map

| Capability | v1? | Approval level | Doc |
| --- | --- | --- | --- |
| Reminders & habits | Yes | Auto / soft | [reminders-and-habits.md](./reminders-and-habits.md) |
| Todos | Yes | Auto | [todos.md](./todos.md) |
| Calendar | Yes | Soft for writes | [calendar.md](./calendar.md) |
| Diet & planning | Yes (basic) | Auto drafts | [diet-and-planning.md](./diet-and-planning.md) |
| Bookings (Booksy etc.) | v1.5 | Hard | [bookings.md](./bookings.md) |
| Shopping | v2 | Hard + caps | [shopping.md](./shopping.md) |

## Shared capability pattern

Every capability should define:

1. User intents it handles
2. Tools/systems touched
3. Happy-path flow
4. Approval tier
5. Failure behavior
6. Acceptance criteria

## Dependency order

```text
Memory + WhatsApp
  → Reminders/Habits
  → Todos + Android
  → Calendar
  → Diet planning
  → Bookings
  → Shopping
```
