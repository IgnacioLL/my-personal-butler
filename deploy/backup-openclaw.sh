#!/usr/bin/env bash
# Backup / restore OpenClaw Gateway state (~/.openclaw style) on a VPS.
#
# Usage:
#   ./backup-openclaw.sh backup
#   ./backup-openclaw.sh restore /var/backups/openclaw/2026-08-09T120000Z
#
# See docs/deploy.md for remote copy (scp/rsync) and cron scheduling.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"
BACKUP_ROOT="${OPENCLAW_BACKUP_ROOT:-/var/backups/openclaw}"

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${ENV_FILE}"
    set +a
  fi
  OPENCLAW_CONFIG_DIR="${OPENCLAW_CONFIG_DIR:-${HOME}/.openclaw}"
  OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${OPENCLAW_CONFIG_DIR}/workspace}"
  OPENCLAW_AUTH_PROFILE_SECRET_DIR="${OPENCLAW_AUTH_PROFILE_SECRET_DIR:-${HOME}/.openclaw-auth-profile-secrets}"
  PERSONAL_AGENT_REPO="${PERSONAL_AGENT_REPO:-/opt/personal-agent}"
}

cmd="${1:-backup}"
load_env

timestamp() { date -u +%Y-%m-%dT%H%M%SZ; }

backup_tree() {
  local label="$1"
  local src="$2"
  local dest="$3"
  if [[ -e "${src}" ]]; then
    mkdir -p "${dest}"
    cp -a "${src}/." "${dest}/"
    echo "    copied ${label} from ${src}"
  else
    echo "    skip (missing) ${label}: ${src}"
  fi
}

case "${cmd}" in
  backup)
    DEST="${BACKUP_ROOT}/$(timestamp)"
    echo "==> OpenClaw backup → ${DEST}"
    mkdir -p "${DEST}"
    backup_tree "openclaw_state" "${OPENCLAW_CONFIG_DIR}" "${DEST}/openclaw"
    backup_tree "workspace" "${OPENCLAW_WORKSPACE_DIR}" "${DEST}/workspace"
    backup_tree "auth_secrets" "${OPENCLAW_AUTH_PROFILE_SECRET_DIR}" "${DEST}/auth-profile-secrets"
    # personal-agent durable paths (approvals, memory) when repo is on host.
    if [[ -d "${PERSONAL_AGENT_REPO}/data" ]]; then
      backup_tree "personal_agent_data" "${PERSONAL_AGENT_REPO}/data" "${DEST}/personal-agent/data"
    fi
    if [[ -f "${PERSONAL_AGENT_REPO}/config/gateway.local.yaml" ]]; then
      mkdir -p "${DEST}/personal-agent/config"
      cp -a "${PERSONAL_AGENT_REPO}/config/gateway.local.yaml" "${DEST}/personal-agent/config/"
      echo "    copied gateway.local.yaml"
    fi
    echo "==> backup complete: ${DEST}"
    ;;
  restore)
    SRC="${2:-}"
    if [[ -z "${SRC}" || ! -d "${SRC}" ]]; then
      echo "usage: $0 restore <backup-dir>" >&2
      exit 1
    fi
    echo "==> restore from ${SRC}"
    echo "    Stop Gateway first:  docker compose -f ${DEPLOY_DIR}/docker-compose.yml down"
    echo "          or:  sudo systemctl stop openclaw-gateway.service"
    read -r -p "Continue? [y/N] " confirm
    [[ "${confirm}" == [yY] ]] || exit 0
    backup_tree "openclaw_state" "${SRC}/openclaw" "${OPENCLAW_CONFIG_DIR}"
    backup_tree "workspace" "${SRC}/workspace" "${OPENCLAW_WORKSPACE_DIR}"
    backup_tree "auth_secrets" "${SRC}/auth-profile-secrets" "${OPENCLAW_AUTH_PROFILE_SECRET_DIR}"
    if [[ -d "${SRC}/personal-agent/data" ]]; then
      backup_tree "personal_agent_data" "${SRC}/personal-agent/data" "${PERSONAL_AGENT_REPO}/data"
    fi
    if [[ -f "${SRC}/personal-agent/config/gateway.local.yaml" ]]; then
      mkdir -p "${PERSONAL_AGENT_REPO}/config"
      cp -a "${SRC}/personal-agent/config/gateway.local.yaml" "${PERSONAL_AGENT_REPO}/config/"
    fi
    chown -R 1000:1000 "${OPENCLAW_CONFIG_DIR}" "${OPENCLAW_WORKSPACE_DIR}" "${OPENCLAW_AUTH_PROFILE_SECRET_DIR}" 2>/dev/null || true
    echo "==> restore complete — restart Gateway"
    ;;
  *)
    echo "usage: $0 {backup|restore <dir>}" >&2
    exit 1
    ;;
esac
