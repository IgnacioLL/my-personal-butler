#!/usr/bin/env bash
# Placeholder backup/restore helper for always-on Gateway hosting.
# Document-only — no live VPS or cloud upload in CI. Stdlib/harness tests use
# tempfile dirs; production copies paths from config/backup.example.json.
#
# Usage (manual, on VPS):
#   ./scripts/backup-restore-placeholder.sh backup
#   ./scripts/backup-restore-placeholder.sh restore ./backups/2026-08-08/

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${ROOT}/config/backup.example.json"
DEST="${ROOT}/backups/$(date -u +%Y-%m-%dT%H%M%SZ)"

cmd="${1:-backup}"

case "$cmd" in
  backup)
    echo "==> backup placeholder (no cloud upload)"
    echo "    manifest: ${MANIFEST}"
    mkdir -p "${DEST}"
    # Copy durable state paths — extend when skill configs land.
    for rel in \
      "config/gateway.local.yaml" \
      "data/memory/profile.json" \
      "data/memory/episodes.jsonl" \
      "data/approvals/items.json"
    do
      src="${ROOT}/${rel}"
      if [[ -f "${src}" ]]; then
        mkdir -p "${DEST}/$(dirname "${rel}")"
        cp -a "${src}" "${DEST}/${rel}"
        echo "    copied ${rel}"
      else
        echo "    skip (missing) ${rel}"
      fi
    done
    echo "==> backup dir: ${DEST}"
    ;;
  restore)
    SRC="${2:-}"
    if [[ -z "${SRC}" || ! -d "${SRC}" ]]; then
      echo "usage: $0 restore <backup-dir>" >&2
      exit 1
    fi
    echo "==> restore placeholder from ${SRC}"
    echo "    Stop Gateway service first (see config/backup.example.json restore_checklist)"
    for rel in \
      "config/gateway.local.yaml" \
      "data/memory/profile.json" \
      "data/memory/episodes.jsonl" \
      "data/approvals/items.json"
    do
      src="${SRC}/${rel}"
      if [[ -f "${src}" ]]; then
        mkdir -p "${ROOT}/$(dirname "${rel}")"
        cp -a "${src}" "${ROOT}/${rel}"
        echo "    restored ${rel}"
      fi
    done
    ;;
  *)
    echo "usage: $0 {backup|restore <dir>}" >&2
    exit 1
    ;;
esac
