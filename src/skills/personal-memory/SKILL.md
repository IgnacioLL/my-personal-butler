---
name: personal-memory
description: "Read hot profile facts, append episodic notes, and soft-confirm durable memory updates — never store secrets."
metadata: { "openclaw": { "requires": { "config": ["skills.entries.personal-memory.enabled"] }, "homepage": "https://docs.openclaw.ai/tools/skills" } }
---

# Personal memory

Curated **hot profile** (identity, preferences, goals) plus **episodic** log on disk. Maps to `intelligence/memory/store.py` in this repo.

## When to use

- User asks what you know about diet, household, rituals, or goals.
- User says **remember …** or a stable preference repeats twice.
- Planning needs allergies, quiet hours, or booking rituals.
- Weekly review asks to prune stale prefs (read episodic, propose updates).

## Tools (Gateway action types)

| Tool | Tier | Harness module | Notes |
| --- | --- | --- | --- |
| `memory_read` | Auto | `MemoryStore.load_hot_profile`, `read_episodes` | Default `mode=hot`; `mode=episodes` for search |
| `memory_update` | Soft confirm | `MemoryStore.remember` | Propose → Accept → execute; never auto-write sensitive facts |

### `memory_read` payload

```json
{
  "mode": "hot",
  "section": "preferences",
  "key": "allergies",
  "limit": 50,
  "tag": "diet"
}
```

- `mode`: `hot` (default) | `episodes` | `section`
- `section` + optional `key`: read one bucket from full profile
- `limit` / `tag`: episodic filters

### `memory_update` payload (soft confirm)

```json
{
  "section": "preferences",
  "key": "food_dislikes",
  "value": ["cilantro"],
  "explicit": true
}
```

Show a one-line confirm before proposing when the fact is sensitive.

## Storage paths (production)

From `config/openclaw/skills-production.json5` / `gateway.example.yaml`:

- Profile: `data/memory/profile.json`
- Episodes: `data/memory/episodes.jsonl`

Seed from `{baseDir}/../../fixtures/memory/seed-profile.json` on first boot.

## Safety

- **INV-MEM-001**: reject `token:`, `sk-`, AWS keys, GitHub PAT patterns — never write to disk.
- Secrets live in env / secret store, not profile files.
- Do not dump full episodic history into every Luna turn; use hot lines + on-demand recall.

## References

- Tool schemas: `{baseDir}/../../tools/schemas.json`
- Harness mapping: `{baseDir}/references/harness-map.md`
