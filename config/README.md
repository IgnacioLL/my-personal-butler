# Config

Placeholders for OpenClaw Gateway and harness profiles. **Do not commit secrets.**

| File | Purpose |
| --- | --- |
| [`gateway.example.yaml`](./gateway.example.yaml) | Always-on Gateway template (VPS/home) — copy to `gateway.local.yaml` |
| [`gateway.harness.json`](./gateway.harness.json) | Harness/CI profile (stdlib JSON) — data paths + hosting flags |
| [`bookings.harness.json`](./bookings.harness.json) | Bookings stub portal (TASK-19 / INV-BOOK-*); CI-only |
| [`shopping.harness.json`](./shopping.harness.json) | Shopping dry-run + daily/weekly spend caps (TASK-21 / INV-PAY-*) |
| [`selfmod.harness.json`](./selfmod.harness.json) | Self-mod fixture workspace (TASK-23 / INV-SELF-*) |
| [`production/bookings.json`](./production/bookings.json) | Production Booksy-class browser skill (hard approve; dry-run default; `BOOKINGS_LIVE`) |
| [`production/shopping.json`](./production/shopping.json) | Production merchant adapters (hard approve; caps; freeze; dry-run default; `SHOPPING_LIVE`) |
| [`production/openclaw.skills.snippet.json`](./production/openclaw.skills.snippet.json) | Merge into OpenClaw `skills` — bookings + shopping entries |
| [`backup.example.json`](./backup.example.json) | Backup/restore path manifest (config + memory + approvals) |
| [`harness.example.env`](./harness.example.env) | Virtual User / CI harness flags — copy to `harness.local.env` |

## Hosting (always-on Gateway)

Per [`agent-plan/operations/hosting.md`](../agent-plan/operations/hosting.md):

- **VPS (recommended):** run Gateway as `openclaw-gateway.service`; stable HTTPS for voice webhooks.
- **Harness (CI):** `gateway.harness.json` + `GatewayHarness` in `src/harness/gateway_harness.py` — no live VPS.
- **WhatsApp reconnect:** documented in `gateway.example.yaml` (`whatsapp_reconnect: auto` on VPS).

## Bookings + shopping

| Path | Live money / Booksy? | Notes |
| --- | --- | --- |
| Harness JSON + fixtures | No | `make test-ci` / E2E-06/07 |
| `production/*.json` | Only if `mode=live` **and** `*_LIVE=1` | See [`docs/bookings-shopping-production.md`](../docs/bookings-shopping-production.md) |
| `src/skills/{bookings,shopping}/` | OpenClaw skill docs | Hard approve mandatory |

## Durability paths

| Data | Default path | Survives reboot |
| --- | --- | --- |
| Approvals | `data/approvals/items.json` | yes (TASK-05 / E2E-10) |
| Memory profile | `data/memory/profile.json` | yes (TASK-04) |
| Episodic log | `data/memory/episodes.jsonl` | yes (TASK-04) |
| Gateway config | `config/gateway.local.yaml` | yes (backup manifest) |

Backup placeholder script: [`../scripts/backup-restore-placeholder.sh`](../scripts/backup-restore-placeholder.sh).

Live hosting guidance: [`agent-plan/operations/hosting.md`](../agent-plan/operations/hosting.md).
