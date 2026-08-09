#!/usr/bin/env bash
# Bootstrap OpenClaw Gateway via Docker Compose (operator-run on VPS).
#
# Prerequisites (operator installs on host — not run by CI agents):
#   - Docker Engine + Compose v2
#   - curl, openssl
#
# Official reference: https://documentation.openclaw.ai/install/docker
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DEPLOY_DIR}"

fail() { echo "ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing dependency: $1"
}

require_cmd docker

# Docker Compose v2 may be installed as either the Docker CLI plugin
# (`docker compose`) or the standalone binary (`docker-compose`).
COMPOSE_CMD=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
  command -v docker-compose >/dev/null 2>&1 || fail "Docker Compose v2 required (docker compose or docker-compose)"
  docker-compose version >/dev/null 2>&1 || fail "Docker Compose v2 required (docker compose or docker-compose)"
  COMPOSE_CMD=(docker-compose)
fi

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "==> created .env from .env.example — edit OPENCLAW_GATEWAY_TOKEN and paths"
  else
    fail "Missing .env — copy .env.example to .env first"
  fi
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

OPENCLAW_CONFIG_DIR="${OPENCLAW_CONFIG_DIR:-${HOME}/.openclaw}"
OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${OPENCLAW_CONFIG_DIR}/workspace}"
OPENCLAW_AUTH_PROFILE_SECRET_DIR="${OPENCLAW_AUTH_PROFILE_SECRET_DIR:-${HOME}/.openclaw-auth-profile-secrets}"

if [[ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    OPENCLAW_GATEWAY_TOKEN="$(openssl rand -hex 32)"
    echo "OPENCLAW_GATEWAY_TOKEN=${OPENCLAW_GATEWAY_TOKEN}" >> .env
    echo "==> generated OPENCLAW_GATEWAY_TOKEN in .env"
  else
    fail "Set OPENCLAW_GATEWAY_TOKEN in .env (openssl rand -hex 32)"
  fi
fi

echo "==> creating persistent directories"
mkdir -p "${OPENCLAW_CONFIG_DIR}" "${OPENCLAW_WORKSPACE_DIR}" "${OPENCLAW_AUTH_PROFILE_SECRET_DIR}"
# OpenClaw container runs as uid 1000 (node user).
chown -R 1000:1000 "${OPENCLAW_CONFIG_DIR}" "${OPENCLAW_WORKSPACE_DIR}" "${OPENCLAW_AUTH_PROFILE_SECRET_DIR}" 2>/dev/null || \
  echo "    (skip chown — run as root or adjust ownership to uid 1000 manually)"

IMAGE="${OPENCLAW_IMAGE:-ghcr.io/openclaw/openclaw:latest}"
echo "==> pulling image ${IMAGE}"
docker pull "${IMAGE}"

echo "==> onboarding (official OpenClaw flow via gateway container)"
# Mirrors openclaw/openclaw scripts/docker/setup.sh pre-start onboarding.
"${COMPOSE_CMD[@]}" run --rm --no-deps --entrypoint node openclaw-gateway \
  dist/index.js onboard --mode local --no-install-daemon || {
    echo "==> onboard may have partially completed; continuing"
  }

echo "==> applying gateway mode and bind"
"${COMPOSE_CMD[@]}" run --rm --no-deps --entrypoint node openclaw-gateway \
  dist/index.js config set gateway.mode local || true
"${COMPOSE_CMD[@]}" run --rm --no-deps --entrypoint node openclaw-gateway \
  dist/index.js config set gateway.bind lan || true
# Control UI allowedOrigins: set during onboard or via docs/deploy.md if SSH tunnel fails CORS.

echo "==> starting gateway (restart: unless-stopped)"
"${COMPOSE_CMD[@]}" up -d openclaw-gateway

echo ""
echo "==> Gateway starting. Next steps:"
echo "    1. SSH tunnel from laptop (see docs/deploy.md for port-forward syntax)"
echo "    2. Open Control UI via tunnel and paste token from deploy/.env"
echo "    3. WhatsApp QR:  docker compose run --rm openclaw-cli channels login"
echo "    4. Full runbook:  ../docs/deploy.md"
