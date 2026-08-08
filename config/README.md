# Config

Placeholders for OpenClaw Gateway and harness profiles. **Do not commit secrets.**

| File | Purpose |
| --- | --- |
| [`gateway.example.yaml`](./gateway.example.yaml) | Always-on Gateway template (VPS/home) — copy to `gateway.local.yaml` |
| [`gateway.harness.json`](./gateway.harness.json) | Harness/CI profile (stdlib JSON) — data paths + hosting flags |
| [`shopping.harness.json`](./shopping.harness.json) | Shopping dry-run + daily/weekly spend caps (TASK-21 / INV-PAY-*) |
| [`backup.example.json`](./backup.example.json) | Backup/restore path manifest (config + memory + approvals) |
| [`harness.example.env`](./harness.example.env) | Virtual User / CI harness flags — copy to `harness.local.env` |

## Hosting (always-on Gateway)

Per [`agent-plan/operations/hosting.md`](../agent-plan/operations/hosting.md):

- **VPS (recommended):** run Gateway as `openclaw-gateway.service`; stable HTTPS for voice webhooks.
- **Harness (CI):** `gateway.harness.json` + `GatewayHarness` in `src/harness/gateway_harness.py` — no live VPS.
- **WhatsApp reconnect:** documented in `gateway.example.yaml` (`whatsapp_reconnect: auto` on VPS).

## Durability paths

| Data | Default path | Survives reboot |
| --- | --- | --- |
| Approvals | `data/approvals/items.json` | yes (TASK-05 / E2E-10) |
| Memory profile | `data/memory/profile.json` | yes (TASK-04) |
| Episodic log | `data/memory/episodes.jsonl` | yes (TASK-04) |
| Gateway config | `config/gateway.local.yaml` | yes (backup manifest) |

Backup placeholder script: [`../scripts/backup-restore-placeholder.sh`](../scripts/backup-restore-placeholder.sh).

Live hosting guidance: [`agent-plan/operations/hosting.md`](../agent-plan/operations/hosting.md).
