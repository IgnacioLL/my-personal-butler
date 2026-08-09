#!/usr/bin/env bash
# Non-Docker OpenClaw Gateway install helper (operator-run on VPS).
#
# This script documents and optionally drives the official install path.
# Run as a user with sudo on Ubuntu/Debian (Oracle ARM or Hetzner CX22).
#
# Official docs:
#   https://documentation.openclaw.ai/install
#   https://documentation.openclaw.ai/gateway
set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }

echo "==> OpenClaw Gateway — systemd install (non-Docker)"
echo ""
echo "This script prints the official commands. Run each step manually or"
echo "uncomment the EXECUTE block at the bottom after reviewing."
echo ""

cat <<'EOF'
--- 1) Install OpenClaw CLI (official installer — provisions Node if needed) ---

  curl -fsSL https://openclaw.ai/install.sh | bash

Alternative (global npm, Node 22+ already installed):

  npm install -g openclaw@latest --allow-scripts openclaw

--- 2) Create dedicated user (recommended for system unit) ---

  sudo useradd -m -s /bin/bash openclaw
  sudo mkdir -p /etc/openclaw
  sudo chown openclaw:openclaw /etc/openclaw

--- 3) Gateway token (store in /etc/openclaw/gateway.env) ---

  sudo bash -c 'echo "OPENCLAW_GATEWAY_TOKEN=$(openssl rand -hex 32)" > /etc/openclaw/gateway.env'
  sudo chmod 600 /etc/openclaw/gateway.env
  sudo chown openclaw:openclaw /etc/openclaw/gateway.env

--- 4) Onboard + install user-level daemon (simplest) ---

  sudo -u openclaw -H bash -lc 'openclaw onboard --install-daemon'

  systemctl --user enable --now openclaw-gateway.service
  openclaw gateway status

For headless VPS without lingering user sessions, enable linger:

  sudo loginctl enable-linger openclaw

--- 5) OR: system-wide unit (always-on VPS) ---

  # After onboard as openclaw user:
  openclaw gateway install --force    # generates unit metadata
  sudo cp deploy/openclaw-gateway.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now openclaw-gateway.service
  sudo systemctl status openclaw-gateway.service

--- 6) Verify reboot survival ---

  sudo reboot
  # after reconnect:
  openclaw gateway status
  openclaw doctor

--- 7) Channels (WhatsApp QR) ---

  openclaw channels login

EOF

if [[ "${EXECUTE:-0}" == "1" ]]; then
  echo "==> EXECUTE=1 — running official installer (interactive onboard)"
  curl -fsSL https://openclaw.ai/install.sh | bash
else
  echo ""
  echo "To run the official installer from this script:"
  echo "  EXECUTE=1 ./install-systemd.sh"
  echo ""
  echo "See docs/deploy.md for Oracle Cloud + Hetzner paths and firewall rules."
fi
