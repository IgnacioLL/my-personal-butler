# Harness map — reminders-habits

| Tool | Action type | Primary code |
| --- | --- | --- |
| `reminder_create` | `reminder_create` | `capabilities.reminders.service.ReminderService` |
| `habit_create` | `habit_create` | same + `ReminderStore.create_habit` |
| `reminder_list` | `reminder_list` | `ReminderStore.list_active` |
| `reminder_snooze` | `reminder_snooze` | `ReminderStore.snooze` |
| `reminder_cancel` | `reminder_cancel` | `ReminderStore.cancel` |

Gateway wiring: `ActionGateway.propose("reminder_create", …)` auto-executes via `_create_reminder`.

E2E coverage:

- E2E-01 voice reminder (`run_e2e_01`)
- E2E-02 habit escalation ladder (`run_e2e_02`)

Unit/integration IDs: `unit.reminder.*`, `integration.reminder.*`, `integration.habit.*` in `run_test_ci.py`.
