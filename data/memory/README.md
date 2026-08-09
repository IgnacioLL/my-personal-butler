# Versioned personal memory

Durable memory for the butler lives **in this repository**:

| File | Role |
| --- | --- |
| `profile.json` | Hot profile (identity, preferences, goals, procedures) |
| `episodes.jsonl` | Episodic append-only log |

## Policy

- Accepted `memory_update` / episodic writes update these files and create a **local git commit** under `data/memory/**` (same repo as skills).
- Secrets never belong here (`INV-MEM-001`); use env / secret store.
- Self-mod allowlist includes `data/memory/**`; other `data/*` runtime stores (approvals, todos, secrets) stay out.
- CI uses `fixtures/memory/` and temp dirs with commit disabled / `record_only` doubles — do not put real personal facts in fixtures.

Fill `profile.json` over time via chat (“remember…”) or by editing and committing.
