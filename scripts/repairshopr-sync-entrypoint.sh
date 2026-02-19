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
SYNC_WATCHDOG_ENABLED="${SYNC_WATCHDOG_ENABLED:-1}"
SYNC_WATCHDOG_POLL_SECONDS="${SYNC_WATCHDOG_POLL_SECONDS:-60}"
SYNC_WATCHDOG_STARTUP_GRACE_SECONDS="${SYNC_WATCHDOG_STARTUP_GRACE_SECONDS:-120}"
SYNC_STALE_HEARTBEAT_SECONDS="${SYNC_STALE_HEARTBEAT_SECONDS:-900}"
SYNC_WATCHDOG_STATUS_TIMEOUT_SECONDS="${SYNC_WATCHDOG_STATUS_TIMEOUT_SECONDS:-60}"
SYNC_WATCHDOG_TERM_GRACE_SECONDS="${SYNC_WATCHDOG_TERM_GRACE_SECONDS:-10}"
SYNC_WATCHDOG_MAX_STALE_COUNT="${SYNC_WATCHDOG_MAX_STALE_COUNT:-3}"

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
    if python - <<'PY'; then
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

WATCHDOG_STATUS_PID=""
WATCHDOG_STATUS_OUTPUT_FILE=""

terminate_process() {
  local pid="$1"
  local grace_seconds="$2"
  local elapsed=0

  kill "${pid}" 2>/dev/null || true

  while kill -0 "${pid}" 2>/dev/null; do
    if ((elapsed >= grace_seconds)); then
      log "SYNC_LOOP watchdog forcing SIGKILL pid=${pid} after ${grace_seconds}s grace."
      kill -9 "${pid}" 2>/dev/null || true
      break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
}

cleanup_watchdog_status_check() {
  if [[ -n "${WATCHDOG_STATUS_PID}" ]]; then
    terminate_process "${WATCHDOG_STATUS_PID}" 1
    wait "${WATCHDOG_STATUS_PID}" 2>/dev/null || true
    WATCHDOG_STATUS_PID=""
  fi

  if [[ -n "${WATCHDOG_STATUS_OUTPUT_FILE}" ]]; then
    rm -f "${WATCHDOG_STATUS_OUTPUT_FILE}"
    WATCHDOG_STATUS_OUTPUT_FILE=""
  fi
}

check_sync_status_stale() {
  local status_pid
  local status_exit_code
  local elapsed=0

  WATCHDOG_STATUS_OUTPUT_FILE="$(mktemp)"
  python "${MANAGE_PY}" sync_status \
    --stale-threshold-seconds "${SYNC_STALE_HEARTBEAT_SECONDS}" \
    --fail-on-stale \
    >"${WATCHDOG_STATUS_OUTPUT_FILE}" 2>&1 &
  status_pid=$!
  WATCHDOG_STATUS_PID="${status_pid}"

  while kill -0 "${status_pid}" 2>/dev/null; do
    if ((elapsed >= SYNC_WATCHDOG_STATUS_TIMEOUT_SECONDS)); then
      log "SYNC_LOOP watchdog status check timed out after ${SYNC_WATCHDOG_STATUS_TIMEOUT_SECONDS}s."
      cleanup_watchdog_status_check
      return 2
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  set +e
  wait "${status_pid}"
  status_exit_code=$?
  set -e

  if [[ "${status_exit_code}" -eq 2 ]]; then
    cleanup_watchdog_status_check
    return 1
  fi

  if [[ "${status_exit_code}" -ne 0 ]]; then
    log "SYNC_LOOP watchdog status check failed exit_code=${status_exit_code}."
    cleanup_watchdog_status_check
    return 2
  fi

  cleanup_watchdog_status_check

  return 0
}

run_import_with_watchdog() {
  if [[ "${SYNC_WATCHDOG_ENABLED}" != "1" ]]; then
    run_manage "import" import_from_repairshopr
    return $?
  fi

  local current_epoch
  local import_exit_code
  local import_pid
  local stale_count=0
  local status_exit_code
  local started_epoch
  local watchdog_pid

  started_epoch="$(date -u +%s)"
  python "${MANAGE_PY}" import_from_repairshopr &
  import_pid=$!

  (
    trap 'cleanup_watchdog_status_check' TERM INT EXIT

    while kill -0 "${import_pid}" 2>/dev/null; do
      sleep "${SYNC_WATCHDOG_POLL_SECONDS}"

      if ! kill -0 "${import_pid}" 2>/dev/null; then
        exit 0
      fi

      current_epoch="$(date -u +%s)"
      if ((current_epoch - started_epoch < SYNC_WATCHDOG_STARTUP_GRACE_SECONDS)); then
        continue
      fi

      if check_sync_status_stale; then
        stale_count=0
        continue
      else
        status_exit_code=$?
      fi

      if [[ "${status_exit_code}" -eq 2 ]]; then
        continue
      fi

      if [[ "${status_exit_code}" -eq 1 ]]; then
        stale_count=$((stale_count + 1))
        log "SYNC_LOOP watchdog detected stale sync status count=${stale_count}/${SYNC_WATCHDOG_MAX_STALE_COUNT}."
        if [[ "${stale_count}" -lt "${SYNC_WATCHDOG_MAX_STALE_COUNT}" ]]; then
          continue
        fi
        log "SYNC_LOOP watchdog terminating import pid=${import_pid} after ${stale_count} consecutive stale checks."
        terminate_process "${import_pid}" "${SYNC_WATCHDOG_TERM_GRACE_SECONDS}"
        exit 0
      fi
    done

    trap - TERM INT EXIT
  ) &
  watchdog_pid=$!

  set +e
  wait "${import_pid}"
  import_exit_code=$?
  set -e

  kill "${watchdog_pid}" 2>/dev/null || true
  wait "${watchdog_pid}" 2>/dev/null || true

  return "${import_exit_code}"
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
  if ! run_import_with_watchdog; then
    log "Import failed; sleeping for ${SYNC_FAILURE_SLEEP_SECONDS}s before next attempt."
    sleep "${SYNC_FAILURE_SLEEP_SECONDS}"
  else
    cycle_finished_epoch="$(date -u +%s)"
    cycle_elapsed_seconds="$((cycle_finished_epoch - cycle_started_epoch))"
    log "SYNC_LOOP done cycle_finished_epoch=${cycle_finished_epoch} elapsed_seconds=${cycle_elapsed_seconds}"
  fi
  sleep "${SYNC_INTERVAL_SECONDS}"
done
