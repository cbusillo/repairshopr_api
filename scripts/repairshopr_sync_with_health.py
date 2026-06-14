from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANAGE_PY = PROJECT_ROOT / "repairshopr_sync" / "manage.py"
SYNC_ENTRYPOINT = PROJECT_ROOT / "scripts" / "repairshopr-sync-entrypoint.sh"
BOOTSTRAP_CONFIG_PY = PROJECT_ROOT / "scripts" / "bootstrap_repairshopr_sync_config.py"
DEFAULT_STALE_THRESHOLD_SECONDS = 900
DEFAULT_HEALTH_PORT = 8000


def _stale_threshold_seconds() -> int:
    for env_name in (
        "SYNC_HEALTH_STALE_THRESHOLD_SECONDS",
        "SYNC_STALE_HEARTBEAT_SECONDS",
    ):
        value = os.getenv(env_name)
        if value is None or not value.strip():
            continue
        try:
            return max(0, int(value))
        except ValueError:
            continue

    return DEFAULT_STALE_THRESHOLD_SECONDS


def _health_port() -> int:
    value = os.getenv("SYNC_HEALTH_PORT")
    if value is None or not value.strip():
        return DEFAULT_HEALTH_PORT
    try:
        return int(value)
    except ValueError:
        return DEFAULT_HEALTH_PORT


def _health_probe_host(bind_address: str) -> str:
    if bind_address == "0.0.0.0":
        return "127.0.0.1"
    if bind_address == "::":
        return "::1"
    return bind_address


def _health_command() -> list[str]:
    return [
        sys.executable,
        str(MANAGE_PY),
        "serve_sync_health",
        "--host",
        os.getenv("SYNC_HEALTH_BIND_ADDRESS", "0.0.0.0"),
        "--port",
        str(_health_port()),
        "--stale-threshold-seconds",
        str(_stale_threshold_seconds()),
    ]


def _bootstrap_config_command() -> list[str]:
    return [sys.executable, str(BOOTSTRAP_CONFIG_PY)]


def _wait_for_health_server(
    process: subprocess.Popen[bytes],
    host: str,
    port: int,
    timeout_seconds: float = 10.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    probe_host = _health_probe_host(host)

    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection((probe_host, port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.1)

    return False


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    bootstrap_result = subprocess.run(_bootstrap_config_command(), check=False)
    if bootstrap_result.returncode != 0:
        return bootstrap_result.returncode

    health_process: subprocess.Popen[bytes] | None = None
    if os.getenv("SYNC_HEALTH_ENABLED", "1") == "1":
        health_process = subprocess.Popen(_health_command())
        health_host = os.getenv("SYNC_HEALTH_BIND_ADDRESS", "0.0.0.0")
        if not _wait_for_health_server(health_process, health_host, _health_port()):
            _stop_process(health_process)
            return health_process.returncode or 1

    sync_process = subprocess.Popen(["bash", str(SYNC_ENTRYPOINT)])

    def stop_children(_signum: int, _frame: object) -> None:
        if health_process is not None:
            _stop_process(health_process)
        _stop_process(sync_process)

    signal.signal(signal.SIGTERM, stop_children)
    signal.signal(signal.SIGINT, stop_children)

    try:
        while True:
            sync_exit = sync_process.poll()
            if sync_exit is not None:
                return sync_exit
            if health_process is not None and health_process.poll() is not None:
                _stop_process(sync_process)
                return health_process.returncode or 1
            time.sleep(1)
    finally:
        if health_process is not None:
            _stop_process(health_process)
        _stop_process(sync_process)


if __name__ == "__main__":
    raise SystemExit(main())
