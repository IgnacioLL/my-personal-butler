# Deploy: always-on OpenClaw Gateway on a cheap VPS

Production path for the personal agent: **OpenClaw Gateway** as the runtime (not a custom gateway). This repo ships compose, systemd, and operator scripts under [`deploy/`](../deploy/); harness CI continues to use mocks.

**Cheapest targets:** Oracle Cloud Always Free ARM (if available) → else Hetzner CX22-class (~€4–5/mo).

## What you get

| Component | Path / artifact |
| --- | --- |
| Docker Compose | [`deploy/docker-compose.yml`](../deploy/docker-compose.yml) |
| Env template | [`deploy/.env.example`](../deploy/.env.example) |
| Docker bootstrap | [`deploy/setup-docker.sh`](../deploy/setup-docker.sh) |
| Backup / restore | [`deploy/backup-openclaw.sh`](../deploy/backup-openclaw.sh) |
| systemd unit | [`deploy/openclaw-gateway.service`](../deploy/openclaw-gateway.service) |
| systemd install helper | [`deploy/install-systemd.sh`](../deploy/install-systemd.sh) |

Official OpenClaw references:

- Install: https://documentation.openclaw.ai/install
- Docker: https://documentation.openclaw.ai/install/docker
- Hetzner guide: https://documentation.openclaw.ai/install/hetzner
- Gateway / systemd: https://documentation.openclaw.ai/gateway
- Security: https://documentation.openclaw.ai/gateway/security

---

## Operator checklist: zero → Gateway up

Use this as the single path; pick **Docker** (recommended) or **systemd** in step 4.

### 0. Prerequisites

- [ ] VPS with public IPv4 (Oracle Free ARM or Hetzner CX22: 2 vCPU, 4 GB RAM, 40+ GB disk)
- [ ] SSH key access as `root` or sudo user
- [ ] Domain optional now; required later for Twilio HTTPS webhooks
- [ ] Codex / OpenAI auth ready for Luna (onboard step)
- [ ] Your WhatsApp number for allowlist (PROD-02)

### 1. Provision the VM

<details>
<summary><strong>Oracle Cloud Always Free ARM</strong></summary>

1. Create an **Ampere A1** instance (Ubuntu 22.04 or 24.04), shape `VM.Standard.A1.Flex` (e.g. 2 OCPU, 12 GB RAM — within free tier limits).
2. Attach a boot volume ≥ 50 GB; enable **VM.Standard.E2.1.Micro** only if ARM capacity is unavailable in your region.
3. **Networking:** create VCN + public subnet; assign a **reserved public IP**.
4. **Security list / NSG:** allow inbound **TCP 22** from your IP only. Do **not** expose 18789 publicly yet.
5. SSH: `ssh -i ~/.ssh/your_key ubuntu@YOUR_PUBLIC_IP` (Ubuntu images use `ubuntu`; adjust user).

Oracle-specific: if SSH fails, check NSG + security list + `iptables` on the instance (`sudo iptables -L`).

</details>

<details>
<summary><strong>Hetzner CX22 (or CX23)</strong></summary>

1. Create a server: **CX22** (2 vCPU, 4 GB RAM, 40 GB), location of choice, Ubuntu 24.04.
2. Add your SSH key at create time.
3. SSH: `ssh root@YOUR_SERVER_IP`
4. Optional: enable Hetzner **Firewall** — allow TCP 22 from your IP; deny all other inbound until TLS front-end is ready.

</details>

### 2. Base OS hardening (both providers)

```bash
apt-get update && apt-get upgrade -y
apt-get install -y git curl ca-certificates ufw fail2ban openssl
timedatectl set-timezone Europe/Madrid   # or your IANA zone
```

**UFW (recommended):**

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow from YOUR_HOME_IP to any port 22 proto tcp
# Later, for Twilio webhooks:
# ufw allow 443/tcp
ufw enable
ufw status
```

### 3. Clone this repo on the VPS

```bash
git clone https://github.com/IgnacioLL/my-personal-butler.git /opt/personal-agent
cd /opt/personal-agent
git checkout cursor/status-and-delegate-c450   # or your release branch
```

### 4a. Path A — Docker Compose (recommended)

**Install Docker** (operator — official convenience script):

```bash
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version
```

**Configure and start:**

```bash
cd /opt/personal-agent/deploy
cp .env.example .env
# Edit .env: OPENCLAW_GATEWAY_TOKEN, OPENCLAW_TZ, paths
chmod +x setup-docker.sh backup-openclaw.sh
./setup-docker.sh
```

`setup-docker.sh` pulls `ghcr.io/openclaw/openclaw:latest`, runs official `onboard`, and starts the gateway with `restart: unless-stopped`.

**Access Control UI (SSH tunnel — default):**

```bash
# On your laptop:
ssh -N -L 18789:127.0.0.1:18789 root@YOUR_VPS_IP
```

Open http://127.0.0.1:18789/ and paste `OPENCLAW_GATEWAY_TOKEN` from `deploy/.env`.

**WhatsApp (official CLI container):**

```bash
cd /opt/personal-agent/deploy
docker compose run --rm openclaw-cli channels login
```

### 4b. Path B — systemd (no Docker)

```bash
cd /opt/personal-agent/deploy
chmod +x install-systemd.sh
./install-systemd.sh          # prints official commands
# or:
EXECUTE=1 ./install-systemd.sh   # runs openclaw.ai/install.sh (interactive)
```

Official one-liner alternative:

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
openclaw onboard --install-daemon
openclaw gateway status
```

For always-on **system** service, use [`deploy/openclaw-gateway.service`](../deploy/openclaw-gateway.service) and `loginctl enable-linger` — see script output.

### 5. Verify reboot survival

```bash
sudo reboot
# after reconnect:
cd /opt/personal-agent/deploy && docker compose ps    # Docker path
# or:
openclaw gateway status                               # systemd path
```

Expected: gateway **active**, WhatsApp session reconnects (`whatsapp_reconnect: auto` in production config).

### 6. Post-deploy (next PROD tasks)

- [ ] Copy production config from PROD-02 (`config/openclaw/` or `config/production/`)
- [ ] Pair Android node (PROD-05)
- [ ] Configure STT/TTS providers (PROD-03)
- [ ] Schedule backups (below)

---

## Persistence: what lives where

| Data | Host path (default) | Survives reboot |
| --- | --- | --- |
| OpenClaw config + credentials | `~/.openclaw/` (`openclaw.json`, auth profiles, channel sessions) | yes |
| Workspace / skills | `~/.openclaw/workspace/` | yes |
| Auth profile secrets | `~/.openclaw-auth-profile-secrets/` | yes |
| personal-agent approvals | `/opt/personal-agent/data/approvals/` | yes |
| personal-agent memory | `/opt/personal-agent/data/memory/` | yes |

Compose bind-mounts the host `OPENCLAW_CONFIG_DIR` into `/home/node/.openclaw` inside the container. **Do not** store state only inside the container filesystem.

Ownership: OpenClaw image runs as uid **1000**. After creating dirs:

```bash
chown -R 1000:1000 /root/.openclaw /root/.openclaw-auth-profile-secrets
```

---

## Backup and restore

### Docker path

```bash
cd /opt/personal-agent/deploy
./backup-openclaw.sh backup
# Archives land in /var/backups/openclaw/<timestamp>/
```

Copy off-site:

```bash
rsync -avz /var/backups/openclaw/ user@backup-host:backups/openclaw/
```

**Restore:**

```bash
docker compose down
./backup-openclaw.sh restore /var/backups/openclaw/2026-08-09T120000Z
docker compose up -d
```

### systemd path

Same script if `deploy/.env` paths match; or tarball manually:

```bash
tar -czf openclaw-backup.tgz -C /home/openclaw .openclaw .config/openclaw
```

### Cron (daily 03:00 UTC)

```cron
0 3 * * * /opt/personal-agent/deploy/backup-openclaw.sh backup >> /var/log/openclaw-backup.log 2>&1
```

Aligns with `gateway.example.yaml` `backup.schedule_cron`.

### Restore checklist

1. Stop Gateway (`docker compose down` or `systemctl stop openclaw-gateway`)
2. Restore `~/.openclaw`, workspace, auth secrets, and `data/` paths
3. Fix ownership (uid 1000 for Docker)
4. Start Gateway; confirm `openclaw doctor`
5. Verify pending approvals in Android inbox
6. Confirm WhatsApp reconnect

---

## Firewall and exposure

| Port | Purpose | Default policy |
| --- | --- | --- |
| 22/tcp | SSH | allow from your IP only |
| 18789 | Gateway Control UI / WS | **loopback only** — use SSH tunnel |
| 443/tcp | HTTPS reverse proxy | open when Twilio webhooks go live |
| 3978 | MS Teams (if used) | closed unless channel enabled |

**Never** expose 18789 to `0.0.0.0/0` without token auth **and** TLS. Prefer SSH tunnel or VPN for admin UI.

Docker `DOCKER-USER` chain: see [OpenClaw security hardening](https://documentation.openclaw.ai/gateway/security).

---

## HTTPS and Twilio webhooks (later)

Voice-call plugin (Twilio/Telnyx) needs a **stable public HTTPS URL**. Plan:

1. Point DNS `gateway.example.com` → VPS public IP.
2. Install Caddy or nginx on the host (not inside the gateway container).
3. Terminate TLS on 443; reverse-proxy to `127.0.0.1:18789` or the voice webhook path OpenClaw documents.
4. Open UFW **443** only; keep 18789 on loopback.
5. Set `public_url` in production gateway config (PROD-02).

**Tunnel alternative (no open ports):** Cloudflare Tunnel or Tailscale Funnel — useful for home-lab; for production VPS, native TLS + UFW is simpler.

Example Caddy snippet (operator adds on host):

```caddy
gateway.example.com {
    reverse_proxy 127.0.0.1:18789
}
```

Twilio console: set voice webhook URL to `https://gateway.example.com/...` per OpenClaw voice-call plugin docs.

---

## Updates

**Docker:**

```bash
cd /opt/personal-agent/deploy
docker pull ghcr.io/openclaw/openclaw:latest
docker compose up -d
```

Pin a release tag in `.env` for reproducibility (`ghcr.io/openclaw/openclaw:2026.2.26`).

**systemd:**

```bash
openclaw update --channel stable
openclaw gateway restart
openclaw doctor
```

If upgrade fails, official recovery:

```bash
docker run --rm -v /root/.openclaw:/home/node/.openclaw ghcr.io/openclaw/openclaw:latest \
  node dist/index.js doctor --fix
```

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `EACCES` on `/Users/...` in container | Ensure compose pins `OPENCLAW_STATE_DIR` (already in our compose) |
| Gateway exits on boot | `docker compose logs -f openclaw-gateway` or `journalctl -u openclaw-gateway` |
| `systemctl --user` unavailable | `loginctl enable-linger $USER`; set `XDG_RUNTIME_DIR` |
| WhatsApp disconnect after reboot | `docker compose run --rm openclaw-cli channels login` |
| OOM on 1 GB VM | Use ≥ 2 GB RAM; Oracle A1 or Hetzner CX22 |
| Port 18789 in use | Change `OPENCLAW_GATEWAY_PORT` in `.env` |

Official: `openclaw doctor`, `openclaw gateway status --deep`, https://documentation.openclaw.ai/gateway/troubleshooting

---

## Official install commands (reference)

Agents cannot run these in CI; the operator runs them on the VPS.

```bash
# Docker image (pre-built)
export OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:latest"
docker pull "$OPENCLAW_IMAGE"

# Or full upstream setup (clone openclaw/openclaw)
git clone https://github.com/openclaw/openclaw.git
cd openclaw
export OPENCLAW_IMAGE="ghcr.io/openclaw/openclaw:latest"
./scripts/docker/setup.sh

# Native CLI
curl -fsSL https://openclaw.ai/install.sh | bash
openclaw onboard --install-daemon

# npm (Node 22+)
npm install -g openclaw@latest --allow-scripts openclaw
openclaw onboard --install-daemon
```

This repo’s [`deploy/setup-docker.sh`](../deploy/setup-docker.sh) mirrors the onboarding portion without cloning the full OpenClaw source tree.

---

## Related

- [`agent-plan/operations/hosting.md`](../agent-plan/operations/hosting.md) — product hosting goals
- [`config/gateway.example.yaml`](../config/gateway.example.yaml) — gateway profile template
- [`config/backup.example.json`](../config/backup.example.json) — harness backup manifest
- [`status.md`](../status.md) — PROD-01 tracker
