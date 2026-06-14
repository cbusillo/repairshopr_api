from __future__ import annotations

import pytest

from scripts import repairshopr_sync_with_health as wrapper


def test_health_command_uses_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNC_HEALTH_BIND_ADDRESS", "127.0.0.1")
    monkeypatch.setenv("SYNC_HEALTH_PORT", "9080")
    monkeypatch.setenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", "45")

    command = wrapper._health_command()

    assert command[1:] == [
        str(wrapper.MANAGE_PY),
        "serve_sync_health",
        "--host",
        "127.0.0.1",
        "--port",
        "9080",
        "--stale-threshold-seconds",
        "45",
    ]


def test_wrapper_can_disable_health_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processes: list[list[str]] = []

    class FinishedProcess:
        returncode = 0

        def __init__(self, command: list[str]) -> None:
            processes.append(command)

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            return None

        def wait(self, timeout: int | None = None) -> int:
            _ = timeout
            return 0

        def kill(self) -> None:
            return None

    monkeypatch.setenv("SYNC_HEALTH_ENABLED", "0")
    monkeypatch.setattr(wrapper.subprocess, "Popen", FinishedProcess)

    assert wrapper.main() == 0
    assert processes == [["bash", str(wrapper.SYNC_ENTRYPOINT)]]
