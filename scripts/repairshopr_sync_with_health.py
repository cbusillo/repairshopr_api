from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANAGE_PY = PROJECT_ROOT / "repairshopr_sync" / "manage.py"
SYNC_ENTRYPOINT = PROJECT_ROOT / "scripts" / "repairshopr-sync-entrypoint.sh"


def _health_command() -> list[str]:
    stale_threshold_seconds = os.getenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS")
    if stale_threshold_seconds is None:
        stale_threshold_seconds = os.getenv("SYNC_STALE_HEARTBEAT_SECONDS", "900")

    return [
        sys.executable,
        str(MANAGE_PY),
        "serve_sync_health",
        "--host",
        os.getenv("SYNC_HEALTH_BIND_ADDRESS", "0.0.0.0"),
        "--port",
        os.getenv("SYNC_HEALTH_PORT", "8000"),
        "--stale-threshold-seconds",
        stale_threshold_seconds,
    ]


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
    health_process: subprocess.Popen[bytes] | None = None
    if os.getenv("SYNC_HEALTH_ENABLED", "1") == "1":
        health_process = subprocess.Popen(_health_command())

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
