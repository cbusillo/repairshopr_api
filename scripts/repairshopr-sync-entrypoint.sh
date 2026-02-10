#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2
}

if [[ -z "${REPAIRSHOPR_TOKEN:-}" ]]; then
  echo "Missing REPAIRSHOPR_TOKEN" >&2
  exit 1
fi

if [[ -z "${REPAIRSHOPR_URL_STORE_NAME:-}" ]]; then
  echo "Missing REPAIRSHOPR_URL_STORE_NAME" >&2
  exit 1
fi

if [[ -z "${SYNC_DB_HOST:-}" ]]; then
  echo "Missing SYNC_DB_HOST" >&2
  exit 1
fi

if [[ -z "${SYNC_DB_PASSWORD:-}" ]]; then
  echo "Missing SYNC_DB_PASSWORD" >&2
  exit 1
fi

if [[ -z "${DJANGO_SECRET_KEY:-}" ]]; then
  echo "Missing DJANGO_SECRET_KEY" >&2
  exit 1
fi

SYNC_DB_NAME="${SYNC_DB_NAME:-repairshopr}"
SYNC_DB_USER="${SYNC_DB_USER:-repairshopr_api}"
SYNC_INTERVAL_SECONDS="${SYNC_INTERVAL_SECONDS:-900}"
REPAIRSHOPR_DEBUG="${REPAIRSHOPR_DEBUG:-false}"
SYNC_DB_RESET="${SYNC_DB_RESET:-0}"

CONFIG_ROOT="${HOME:-/var/lib/repairshopr}/.config/repairshopr-api"
CONFIG_FILE="${CONFIG_ROOT}/config.toml"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANAGE_PY="${PROJECT_ROOT}/repairshopr_sync/manage.py"

export REPAIRSHOPR_DEBUG
export SYNC_DB_NAME
export SYNC_DB_USER
export CONFIG_FILE

mkdir -p "${CONFIG_ROOT}"

python - <<'PY'
import os
from pathlib import Path

import toml

config_file = Path(os.environ["CONFIG_FILE"])
config_file.parent.mkdir(parents=True, exist_ok=True)

data = {}
if config_file.exists():
    try:
        data = toml.load(config_file)
    except toml.TomlDecodeError:
        data = {}

data.setdefault("repairshopr", {})
data.setdefault("django", {})

data["debug"] = os.environ["REPAIRSHOPR_DEBUG"].lower() in {"1", "true", "yes", "on"}
data["repairshopr"]["token"] = os.environ["REPAIRSHOPR_TOKEN"]
data["repairshopr"]["url_store_name"] = os.environ["REPAIRSHOPR_URL_STORE_NAME"]
data["django"]["secret_key"] = os.environ["DJANGO_SECRET_KEY"]
data["django"]["db_engine"] = "mysql"
data["django"]["db_host"] = os.environ["SYNC_DB_HOST"]
data["django"]["db_name"] = os.environ["SYNC_DB_NAME"]
data["django"]["db_user"] = os.environ["SYNC_DB_USER"]
data["django"]["db_password"] = os.environ["SYNC_DB_PASSWORD"]

with config_file.open("w") as handle:
    toml.dump(data, handle)
PY

wait_for_db() {
  local retries="${SYNC_DB_WAIT_RETRIES:-60}"
  local delay="${SYNC_DB_WAIT_SECONDS:-2}"
  local attempt=1

  while [ "$attempt" -le "$retries" ]; do
    if python - <<'PY'
import os
import sys

import MySQLdb

try:
    MySQLdb.connect(
        host=os.environ["SYNC_DB_HOST"],
        user=os.environ["SYNC_DB_USER"],
        passwd=os.environ["SYNC_DB_PASSWORD"],
        db=os.environ["SYNC_DB_NAME"],
        connect_timeout=5,
    ).close()
except Exception:
    sys.exit(1)
sys.exit(0)
PY
    then
      echo "RepairShopr sync DB is ready."
      return 0
    fi
    echo "Waiting for RepairShopr sync DB... (${attempt}/${retries})"
    attempt=$((attempt + 1))
    sleep "${delay}"
  done

  echo "RepairShopr sync DB not reachable after ${retries} attempts." >&2
  return 1
}

wait_for_db

run_manage() {
  local label="$1"
  shift
  if ! python "${MANAGE_PY}" "$@"; then
    log "RepairShopr sync failed during ${label}."
    return 1
  fi
  return 0
}

SYNC_FAILURE_SLEEP_SECONDS="${SYNC_FAILURE_SLEEP_SECONDS:-60}"

if [[ "${SYNC_DB_RESET}" = "1" ]]; then
  log "Resetting RepairShopr sync DB via Django flush."
  if ! run_manage "flush" flush --noinput; then
    log "Sync DB reset failed; sleeping for ${SYNC_FAILURE_SLEEP_SECONDS}s before retry."
    sleep "${SYNC_FAILURE_SLEEP_SECONDS}"
  fi
fi

if ! run_manage "migrate" migrate --noinput; then
  log "Migration failed; sleeping for ${SYNC_FAILURE_SLEEP_SECONDS}s before retry."
  sleep "${SYNC_FAILURE_SLEEP_SECONDS}"
fi

while true; do
  cycle_started_epoch="$(date -u +%s)"
  log "SYNC_LOOP start cycle_started_epoch=${cycle_started_epoch}"
  if ! run_manage "import" import_from_repairshopr; then
    log "Import failed; sleeping for ${SYNC_FAILURE_SLEEP_SECONDS}s before next attempt."
    sleep "${SYNC_FAILURE_SLEEP_SECONDS}"
  else
    cycle_finished_epoch="$(date -u +%s)"
    cycle_elapsed_seconds="$((cycle_finished_epoch - cycle_started_epoch))"
    log "SYNC_LOOP done cycle_finished_epoch=${cycle_finished_epoch} elapsed_seconds=${cycle_elapsed_seconds}"
  fi
  sleep "${SYNC_INTERVAL_SECONDS}"
done
