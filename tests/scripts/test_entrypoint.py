from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "repairshopr-sync-entrypoint.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def stubbed_runtime(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    log_file = tmp_path / "events.log"
    db_attempt_file = tmp_path / "db-attempts.txt"
    sync_status_check_file = tmp_path / "sync-status-checks.txt"
    import_ready_fifo = tmp_path / "import-ready.fifo"
    import_release_fifo = tmp_path / "import-release.fifo"
    status_ready_fifo = tmp_path / "status-ready.fifo"
    os.mkfifo(import_ready_fifo)
    os.mkfifo(import_release_fifo)
    os.mkfifo(status_ready_fifo)

    python_stub = """#!/usr/bin/env bash
set -euo pipefail

REAL_PYTHON="${REAL_PYTHON:-python3}"
LOG_FILE="${MOCK_LOG_FILE:-/tmp/entrypoint-mock.log}"
DB_ATTEMPT_FILE="${DB_ATTEMPT_FILE:-/tmp/db-attempts.log}"
SYNC_STATUS_CHECK_FILE="${SYNC_STATUS_CHECK_FILE:-/tmp/sync-status-checks.log}"
DB_READY_AFTER="${DB_READY_AFTER:-1}"
IMPORT_FAIL="${MOCK_IMPORT_FAIL:-0}"
IMPORT_BLOCK="${MOCK_IMPORT_BLOCK:-0}"
IMPORT_IGNORE_TERM="${MOCK_IMPORT_IGNORE_TERM:-0}"
IMPORT_WAIT_FOR_STATUS="${MOCK_IMPORT_WAIT_FOR_STATUS:-0}"
IMPORT_READY_FIFO="${MOCK_IMPORT_READY_FIFO:-}"
IMPORT_RELEASE_FIFO="${MOCK_IMPORT_RELEASE_FIFO:-}"
SYNC_STATUS_STALE_AFTER="${MOCK_SYNC_STATUS_STALE_AFTER:-0}"
SYNC_STATUS_BLOCK="${MOCK_SYNC_STATUS_BLOCK:-0}"
SYNC_STATUS_READY_FIFO="${MOCK_SYNC_STATUS_READY_FIFO:-}"

if [[ "${1:-}" == *"repairshopr_sync/manage.py" ]]; then
  cmd="${2:-}"
  echo "manage:${cmd}" >> "${LOG_FILE}"
  if [[ "${cmd}" == "sync_status" ]]; then
    check_count=0
    if [[ -f "${SYNC_STATUS_CHECK_FILE}" ]]; then
      check_count="$(cat "${SYNC_STATUS_CHECK_FILE}")"
    fi
    check_count="$((check_count + 1))"
    echo "${check_count}" > "${SYNC_STATUS_CHECK_FILE}"

    if [[ "${SYNC_STATUS_BLOCK}" == "1" ]]; then
      : "${SYNC_STATUS_READY_FIFO:?MOCK_SYNC_STATUS_READY_FIFO is required}"
      : "${IMPORT_RELEASE_FIFO:?MOCK_IMPORT_RELEASE_FIFO is required}"
      exec "${REAL_PYTHON}" - "${SYNC_STATUS_READY_FIFO}" "${IMPORT_RELEASE_FIFO}" <<'PY'
import signal
import sys

with open(sys.argv[2], "wb", buffering=0):
    with open(sys.argv[1], "wb", buffering=0) as ready_fifo:
        ready_fifo.write(b"1")
    signal.pause()
PY
    fi

    if [[ "${SYNC_STATUS_STALE_AFTER}" -gt "0" && "${check_count}" -ge "${SYNC_STATUS_STALE_AFTER}" ]]; then
      echo '{"is_stale":true}'
      if [[ " $* " == *" --fail-on-stale "* ]]; then
        exit 2
      fi
      exit 0
    fi

    echo '{"is_stale":false}'
    exit 0
  fi

  if [[ "${cmd}" == "import_from_repairshopr" && "${IMPORT_BLOCK}" == "1" ]]; then
    : "${IMPORT_READY_FIFO:?MOCK_IMPORT_READY_FIFO is required}"
    exec "${REAL_PYTHON}" - "${IMPORT_READY_FIFO}" "${IMPORT_IGNORE_TERM}" <<'PY'
import signal
import sys

if sys.argv[2] == "1":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

with open(sys.argv[1], "wb", buffering=0) as ready_fifo:
    ready_fifo.write(b"1")
signal.pause()
PY
  fi

  if [[ "${cmd}" == "import_from_repairshopr" && "${IMPORT_WAIT_FOR_STATUS}" == "1" ]]; then
    : "${IMPORT_RELEASE_FIFO:?MOCK_IMPORT_RELEASE_FIFO is required}"
    exec "${REAL_PYTHON}" - "${IMPORT_RELEASE_FIFO}" <<'PY'
import sys

with open(sys.argv[1], "rb", buffering=0) as release_fifo:
    release_fifo.read()
PY
  fi

  if [[ "${cmd}" == "import_from_repairshopr" && "${IMPORT_FAIL}" == "1" ]]; then
    exit 1
  fi
  exit 0
fi

if [[ "${1:-}" == "-" ]]; then
  script_contents="$(cat)"
  if [[ "${script_contents}" == *"MySQLdb.connect"* ]]; then
    attempt=0
    if [[ -f "${DB_ATTEMPT_FILE}" ]]; then
      attempt="$(cat "${DB_ATTEMPT_FILE}")"
    fi
    attempt="$((attempt + 1))"
    echo "${attempt}" > "${DB_ATTEMPT_FILE}"
    echo "db-check:${attempt}" >> "${LOG_FILE}"
    if [[ "${attempt}" -ge "${DB_READY_AFTER}" ]]; then
      exit 0
    fi
    exit 1
  fi
  printf "%s" "${script_contents}" | "${REAL_PYTHON}" -
  exit $?
fi

exec "${REAL_PYTHON}" "$@"
"""

    sleep_stub = """#!/usr/bin/env bash
set -euo pipefail

arg="${1:-}"
echo "sleep:${arg}" >> "${MOCK_LOG_FILE:-/tmp/entrypoint-mock.log}"

if [[ "${STOP_ON_SLEEP_ARG:-}" == "${arg}" ]]; then
  exit "${STOP_EXIT_CODE:-77}"
fi

if [[ "${MOCK_SLEEP_WAIT_ARG:-}" == "${arg}" && ! -e "${MOCK_SLEEP_WAIT_CONSUMED_FILE:-}" ]]; then
  : "${MOCK_SLEEP_WAIT_FIFO:?MOCK_SLEEP_WAIT_FIFO is required}"
  : "${MOCK_SLEEP_WAIT_CONSUMED_FILE:?MOCK_SLEEP_WAIT_CONSUMED_FILE is required}"
  IFS= read -r -n 1 ready < "${MOCK_SLEEP_WAIT_FIFO}"
  : > "${MOCK_SLEEP_WAIT_CONSUMED_FILE}"
fi

exit 0
"""

    _write_executable(bin_dir / "python", python_stub)
    _write_executable(bin_dir / "sleep", sleep_stub)

    base_env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "REAL_PYTHON": sys.executable,
        "MOCK_LOG_FILE": str(log_file),
        "DB_ATTEMPT_FILE": str(db_attempt_file),
        "SYNC_STATUS_CHECK_FILE": str(sync_status_check_file),
        "MOCK_IMPORT_READY_FIFO": str(import_ready_fifo),
        "MOCK_IMPORT_RELEASE_FIFO": str(import_release_fifo),
        "MOCK_SYNC_STATUS_READY_FIFO": str(status_ready_fifo),
        "MOCK_SLEEP_WAIT_CONSUMED_FILE": str(tmp_path / "sleep-wait-consumed"),
        "REPAIRSHOPR_TOKEN": "token",
        "REPAIRSHOPR_URL_STORE_NAME": "store",
        "SYNC_DB_HOST": "db",
        "SYNC_DB_PASSWORD": "pw",
        "DJANGO_SECRET_KEY": "secret",
    }
    return base_env


def _run_entrypoint(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        ["bash", str(SCRIPT_PATH)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=10)
    except subprocess.TimeoutExpired as error:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            process.args,
            error.timeout,
            output=stdout,
            stderr=stderr,
        ) from error
    return subprocess.CompletedProcess(
        process.args,
        process.returncode,
        stdout,
        stderr,
    )


@pytest.mark.scripts
@pytest.mark.parametrize(
    "missing_var, message",
    [
        ("REPAIRSHOPR_TOKEN", "Missing REPAIRSHOPR_TOKEN"),
        ("REPAIRSHOPR_URL_STORE_NAME", "Missing REPAIRSHOPR_URL_STORE_NAME"),
        ("SYNC_DB_HOST", "Missing SYNC_DB_HOST"),
        ("SYNC_DB_PASSWORD", "Missing SYNC_DB_PASSWORD"),
        ("DJANGO_SECRET_KEY", "Missing DJANGO_SECRET_KEY"),
    ],
)
def test_entrypoint_validates_required_env(
    stubbed_runtime: dict[str, str],
    missing_var: str,
    message: str,
) -> None:
    env = dict(stubbed_runtime)
    env.pop(missing_var)

    result = _run_entrypoint(env)

    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.scripts
def test_entrypoint_waits_for_db_then_runs_sync_cycle(
    stubbed_runtime: dict[str, str],
) -> None:
    env = dict(stubbed_runtime)
    env.update(
        {
            "DB_READY_AFTER": "3",
            "SYNC_DB_WAIT_RETRIES": "5",
            "SYNC_DB_WAIT_SECONDS": "4",
            "SYNC_INTERVAL_SECONDS": "30",
            "STOP_ON_SLEEP_ARG": "30",
            "STOP_EXIT_CODE": "77",
        }
    )

    result = _run_entrypoint(env)
    combined_output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 77
    assert "Waiting for RepairShopr sync DB... (1/5)" in combined_output
    assert "Waiting for RepairShopr sync DB... (2/5)" in combined_output
    assert "RepairShopr sync DB is ready." in combined_output
    assert "SYNC_LOOP start" in result.stderr
    assert "SYNC_LOOP done" in result.stderr
    assert "elapsed_seconds=" in result.stderr

    event_log = Path(env["MOCK_LOG_FILE"]).read_text()
    assert "manage:migrate" in event_log
    assert "manage:import_from_repairshopr" in event_log
    assert "sleep:4" in event_log


@pytest.mark.scripts
def test_entrypoint_failure_path_logs_and_uses_failure_sleep(
    stubbed_runtime: dict[str, str],
) -> None:
    env = dict(stubbed_runtime)
    env.update(
        {
            "MOCK_IMPORT_FAIL": "1",
            "SYNC_FAILURE_SLEEP_SECONDS": "7",
            "SYNC_INTERVAL_SECONDS": "30",
            "STOP_ON_SLEEP_ARG": "7",
            "STOP_EXIT_CODE": "77",
        }
    )

    result = _run_entrypoint(env)

    assert result.returncode == 77
    assert "Import failed; sleeping for 7s before next attempt." in result.stderr

    event_log = Path(env["MOCK_LOG_FILE"]).read_text()
    assert "manage:import_from_repairshopr" in event_log
    assert "sleep:7" in event_log


@pytest.mark.scripts
def test_entrypoint_watchdog_detects_stale_sync_and_restarts_cycle(
    stubbed_runtime: dict[str, str],
) -> None:
    env = dict(stubbed_runtime)
    env.update(
        {
            "SYNC_WATCHDOG_ENABLED": "1",
            "SYNC_WATCHDOG_POLL_SECONDS": "0",
            "SYNC_WATCHDOG_STARTUP_GRACE_SECONDS": "0",
            "SYNC_WATCHDOG_MAX_STALE_COUNT": "1",
            "SYNC_STALE_HEARTBEAT_SECONDS": "30",
            "MOCK_IMPORT_BLOCK": "1",
            "MOCK_SLEEP_WAIT_ARG": "0",
            "MOCK_SLEEP_WAIT_FIFO": stubbed_runtime["MOCK_IMPORT_READY_FIFO"],
            "MOCK_SYNC_STATUS_STALE_AFTER": "2",
            "SYNC_FAILURE_SLEEP_SECONDS": "7",
            "STOP_ON_SLEEP_ARG": "7",
            "STOP_EXIT_CODE": "77",
        }
    )

    result = _run_entrypoint(env)

    assert result.returncode == 77
    assert "watchdog detected stale sync status" in result.stderr
    assert "Import failed; sleeping for 7s before next attempt." in result.stderr

    event_log = Path(env["MOCK_LOG_FILE"]).read_text()
    assert "manage:import_from_repairshopr" in event_log
    assert "manage:sync_status" in event_log
    assert "sleep:7" in event_log


@pytest.mark.scripts
def test_entrypoint_watchdog_status_timeout_does_not_block_import(
    stubbed_runtime: dict[str, str],
) -> None:
    env = dict(stubbed_runtime)
    env.update(
        {
            "SYNC_WATCHDOG_ENABLED": "1",
            "SYNC_WATCHDOG_POLL_SECONDS": "0",
            "SYNC_WATCHDOG_STARTUP_GRACE_SECONDS": "0",
            "SYNC_WATCHDOG_STATUS_TIMEOUT_SECONDS": "1",
            "MOCK_IMPORT_WAIT_FOR_STATUS": "1",
            "MOCK_SYNC_STATUS_BLOCK": "1",
            "MOCK_SLEEP_WAIT_ARG": "1",
            "MOCK_SLEEP_WAIT_FIFO": stubbed_runtime["MOCK_SYNC_STATUS_READY_FIFO"],
            "SYNC_INTERVAL_SECONDS": "30",
            "STOP_ON_SLEEP_ARG": "30",
            "STOP_EXIT_CODE": "77",
        }
    )

    result = _run_entrypoint(env)

    assert result.returncode == 77
    assert "watchdog status check timed out" in result.stderr
    assert "SYNC_LOOP done" in result.stderr


@pytest.mark.scripts
def test_entrypoint_watchdog_logs_consecutive_stale_counts_before_termination(
    stubbed_runtime: dict[str, str],
) -> None:
    env = dict(stubbed_runtime)
    env.update(
        {
            "SYNC_WATCHDOG_ENABLED": "1",
            "SYNC_WATCHDOG_POLL_SECONDS": "0",
            "SYNC_WATCHDOG_STARTUP_GRACE_SECONDS": "0",
            "SYNC_WATCHDOG_MAX_STALE_COUNT": "3",
            "MOCK_SYNC_STATUS_STALE_AFTER": "1",
            "MOCK_IMPORT_BLOCK": "1",
            "MOCK_SLEEP_WAIT_ARG": "0",
            "MOCK_SLEEP_WAIT_FIFO": stubbed_runtime["MOCK_IMPORT_READY_FIFO"],
            "SYNC_INTERVAL_SECONDS": "30",
            "STOP_ON_SLEEP_ARG": "30",
            "STOP_EXIT_CODE": "77",
        }
    )

    result = _run_entrypoint(env)

    assert result.returncode == 77
    assert "count=1/3" in result.stderr
    assert "count=2/3" in result.stderr
    assert "after 3 consecutive stale checks" in result.stderr


@pytest.mark.scripts
def test_entrypoint_watchdog_escalates_to_sigkill_for_stuck_import(
    stubbed_runtime: dict[str, str],
) -> None:
    env = dict(stubbed_runtime)
    env.update(
        {
            "SYNC_WATCHDOG_ENABLED": "1",
            "SYNC_WATCHDOG_POLL_SECONDS": "0",
            "SYNC_WATCHDOG_STARTUP_GRACE_SECONDS": "0",
            "SYNC_WATCHDOG_MAX_STALE_COUNT": "1",
            "SYNC_WATCHDOG_TERM_GRACE_SECONDS": "1",
            "MOCK_IMPORT_BLOCK": "1",
            "MOCK_IMPORT_IGNORE_TERM": "1",
            "MOCK_SLEEP_WAIT_ARG": "0",
            "MOCK_SLEEP_WAIT_FIFO": stubbed_runtime["MOCK_IMPORT_READY_FIFO"],
            "MOCK_SYNC_STATUS_STALE_AFTER": "1",
            "SYNC_FAILURE_SLEEP_SECONDS": "7",
            "STOP_ON_SLEEP_ARG": "7",
            "STOP_EXIT_CODE": "77",
        }
    )

    result = _run_entrypoint(env)

    assert result.returncode == 77
    assert "watchdog detected stale sync status" in result.stderr
    assert "forcing SIGKILL" in result.stderr
    assert "Import failed; sleeping for 7s before next attempt." in result.stderr
