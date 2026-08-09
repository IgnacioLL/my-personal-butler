# OpenClaw skills — PROD-04 pack

Production skill manifests for **memory**, **reminders/habits**, **todos**, and **heartbeat / weekly review**. Each folder is an [AgentSkills](https://agentskills.io)-compatible skill (`SKILL.md` + optional `references/`).

Harness CI exercises the same behavior via `src/capabilities/*`, `src/intelligence/memory/*`, and `src/operations/heartbeat.py` through `ActionGateway` — skills teach Luna in production; adapters stay green in CI.

## Pack contents

| Skill | Directory | Tools |
| --- | --- | --- |
| Personal memory | [`personal-memory/`](./personal-memory/) | `memory_read`, `memory_update` |
| Reminders & habits | [`reminders-habits/`](./reminders-habits/) | `reminder_create`, `habit_create`, `reminder_list`, `reminder_snooze`, `reminder_cancel` |
| Todos | [`personal-todos/`](./personal-todos/) | `todo_add`, `todo_complete`, `todo_read`, `todo_cancel` |
| Heartbeat | [`heartbeat-ops/`](./heartbeat-ops/) | `heartbeat_morning_brief`, `heartbeat_weekly_review` |

Tool JSON schemas: [`../tools/schemas.json`](../tools/schemas.json). Registry: [`../tools/registry.py`](../tools/registry.py).

## Enable in OpenClaw

### 1. Point Gateway at this repo’s skills

Merge [`config/openclaw/skills-production.json5`](../../config/openclaw/skills-production.json5) into `~/.openclaw/openclaw.json`:

```json5
{
  skills: {
    load: {
      extraDirs: ["/path/to/my-personal-butler/src/skills"],
      watch: true,
    },
    entries: {
      "personal-memory": { enabled: true },
      "reminders-habits": { enabled: true },
      "personal-todos": { enabled: true },
      "heartbeat-ops": { enabled: true },
    },
  },
  agents: {
    defaults: {
      skills: [
        "personal-memory",
        "reminders-habits",
        "personal-todos",
        "heartbeat-ops",
      ],
    },
  },
  cron: {
    heartbeat_enabled: true,
  },
}
```

Use an absolute path to `extraDirs` on the VPS. Workspace skills (`<workspace>/skills`) take precedence over `extraDirs` if you copy skills there instead.

### 2. Register tools on the Gateway

Register tools from `src/tools/schemas.json` in your OpenClaw plugin or Gateway tool manifest so Luna can invoke them. Each `name` maps to an `action_type` handled by `ActionGateway` (see harness-map in each skill’s `references/`).

For a thin Python dispatch layer in custom plugins, use [`../tools/bridge.py`](../tools/bridge.py) (`SkillToolBridge`).

### 3. Persist memory and approvals

Ensure data paths match hosting profile:

- `data/memory/profile.json` + `episodes.jsonl`
- `data/approvals/items.json`

Seed profile: `fixtures/memory/seed-profile.json`. Backup manifest: `config/backup.example.json`.

### 4. Restart or new session

OpenClaw snapshots skills at **session start**. After editing `SKILL.md` or config, start a new agent session (or rely on `skills.load.watch` for mid-session refresh).

### 5. Verify load

```bash
openclaw skills list
# expect: personal-memory, reminders-habits, personal-todos, heartbeat-ops
```

## Approval tiers (production)

| Tier | Tools |
| --- | --- |
| Auto | `memory_read`, `todo_*`, `reminder_*`, `habit_create`, heartbeat tools |
| Soft confirm | `memory_update` (propose → Accept → execute) |

## Harness mapping

| Layer | Location |
| --- | --- |
| Memory store | `src/intelligence/memory/store.py` |
| Reminders | `src/capabilities/reminders/` |
| Todos | `src/capabilities/todos/` |
| Heartbeat | `src/operations/heartbeat.py` |
| Gateway gates | `src/policy/action_gateway.py` |
| CI checks | `scripts/run_test_ci.py` (`integration.memory.*`, `unit.reminder.*`, …) |

## Install into workspace (alternative)

```bash
openclaw skills install ./src/skills/personal-memory --as personal-memory
openclaw skills install ./src/skills/reminders-habits --as reminders-habits
openclaw skills install ./src/skills/personal-todos --as personal-todos
openclaw skills install ./src/skills/heartbeat-ops --as heartbeat-ops
```

Then set `skills.entries.<name>.enabled: true` for each.
