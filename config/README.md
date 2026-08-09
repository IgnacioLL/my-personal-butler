# Config

Placeholders for OpenClaw Gateway and harness profiles. **Do not commit secrets.**

| File / dir | Purpose |
| --- | --- |
| [`openclaw/`](./openclaw/) | **Production** OpenClaw templates — Codex/Luna, WhatsApp Baileys allowlist, STT media hooks (PROD-02). Not used by `test:ci`. |
| [`gateway.example.yaml`](./gateway.example.yaml) | Always-on Gateway template (VPS/home) — copy to `gateway.local.yaml` |
| [`gateway.harness.json`](./gateway.harness.json) | Harness/CI profile (stdlib JSON) — data paths + hosting flags |
| [`shopping.harness.json`](./shopping.harness.json) | Shopping dry-run + daily/weekly spend caps (TASK-21 / INV-PAY-*) |
| [`selfmod.harness.json`](./selfmod.harness.json) | Self-mod CI/fixture workspace (INV-SELF-*) |
| [`selfmod.production.json`](./selfmod.production.json) | Production self-mod flags + hard-approve / freeze / rollback (PROD-09) |
| [`selfmod.allowlist.production.json`](./selfmod.allowlist.production.json) | Real-repo path allowlist (skills/docs/config/plan/policy — not secrets) |
| [`backup.example.json`](./backup.example.json) | Backup/restore path manifest (config + memory + approvals) |
| [`harness.example.env`](./harness.example.env) | Virtual User / CI harness flags — copy to `harness.local.env` |

Production WhatsApp QR login + Codex auth: [`openclaw/README.md`](./openclaw/README.md).

## Hosting (always-on Gateway)

Per [`agent-plan/operations/hosting.md`](../agent-plan/operations/hosting.md):

- **VPS (recommended):** run Gateway as `openclaw-gateway.service`; stable HTTPS for voice webhooks.
- **Harness (CI):** `gateway.harness.json` + `GatewayHarness` in `src/harness/gateway_harness.py` — no live VPS.
- **WhatsApp reconnect:** documented in `gateway.example.yaml` (`whatsapp_reconnect: auto` on VPS).
- **Production channel config:** `openclaw/openclaw.production.json5` (Baileys + `allowFrom`); harness stays on mocks.

## Durability paths

| Data | Default path | Survives reboot |
| --- | --- | --- |
| Approvals | `data/approvals/items.json` | yes (TASK-05 / E2E-10) |
| Memory profile | `data/memory/profile.json` | yes (TASK-04) |
| Episodic log | `data/memory/episodes.jsonl` | yes (TASK-04) |
| Gateway config | `config/gateway.local.yaml` | yes (backup manifest) |

Backup placeholder script: [`../scripts/backup-restore-placeholder.sh`](../scripts/backup-restore-placeholder.sh).

## Self-modification (PROD-09)

| Mode | Allowlist | Workspace | Skill |
| --- | --- | --- | --- |
| CI / harness | `fixtures/selfmod/allowlist.json` | `fixtures/selfmod/sample-workspace` | N/A (Python service) |
| Production | `selfmod.allowlist.production.json` | this git checkout | [`src/skills/self-modification/SKILL.md`](../src/skills/self-modification/SKILL.md) |

Production apply is always **hard approve** with `rollback_ref` on `cursor/agent-self-*`. `freeze_self_mod` blocks apply. Policy-path edits use subtype `policy-change`. Local/secret paths (`*.local.*`, `.env`, `data/`, `secrets/`) are forbidden even under `config/**`.

Live hosting guidance: [`agent-plan/operations/hosting.md`](../agent-plan/operations/hosting.md).
