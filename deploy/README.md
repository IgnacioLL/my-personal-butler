# deploy/

Always-on **OpenClaw Gateway** deployment assets for VPS hosting. Not used by CI harness.

| File | Purpose |
| --- | --- |
| [`docker-compose.yml`](./docker-compose.yml) | Official OpenClaw image + `~/.openclaw` persistent volumes |
| [`.env.example`](./.env.example) | Operator env template (copy to `.env`) |
| [`setup-docker.sh`](./setup-docker.sh) | Pull image, onboard, start gateway |
| [`backup-openclaw.sh`](./backup-openclaw.sh) | Backup/restore `~/.openclaw` + repo `data/` |
| [`openclaw-gateway.service`](./openclaw-gateway.service) | systemd unit for non-Docker hosts |
| [`install-systemd.sh`](./install-systemd.sh) | Official native install command reference |

**Full runbook:** [`docs/deploy.md`](../docs/deploy.md) (Oracle Cloud ARM + Hetzner CX22, firewall, reboot, HTTPS/Twilio notes, zero→up checklist).
