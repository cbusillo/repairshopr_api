from __future__ import annotations

from typing import Literal

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

    class BootstrapResult:
        returncode = 0

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
    monkeypatch.setattr(
        wrapper.subprocess,
        "run",
        lambda _command, *, check: BootstrapResult(),
    )
    monkeypatch.setattr(wrapper.subprocess, "Popen", FinishedProcess)

    assert wrapper.main() == 0
    assert processes == [["bash", str(wrapper.SYNC_ENTRYPOINT)]]


def test_wrapper_waits_for_health_before_launching_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    health_processes: list[list[str]] = []
    sync_processes: list[list[str]] = []
    popen_calls: list[list[str]] = []
    run_calls: list[list[str]] = []

    class HealthReadyProcess:
        returncode = 0

        def __init__(self, command: list[str]) -> None:
            health_processes.append(command)

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: int | None = None) -> int:
            _ = timeout
            return 0

        def kill(self) -> None:
            return None

    class SyncProcess:
        returncode = 0

        def __init__(self, command: list[str]) -> None:
            sync_processes.append(command)

        def poll(self) -> int | None:
            return 0

        def terminate(self) -> None:
            return None

        def wait(self, timeout: int | None = None) -> int:
            _ = timeout
            return 0

        def kill(self) -> None:
            return None

    connections: list[tuple[str, int]] = []

    class ReadySocket:
        def __enter__(self) -> "ReadySocket":
            return self

        def __exit__(self, exc_type, exc, tb) -> Literal[False]:
            _ = exc_type, exc, tb
            return False

    def fake_create_connection(address: tuple[str, int], timeout: float = 0.0):
        _ = timeout
        connections.append(address)
        if len(connections) == 1:
            raise OSError("not ready yet")
        return ReadySocket()

    def fake_popen(command: list[str]) -> object:
        popen_calls.append(command)
        if len(popen_calls) == 1:
            return HealthReadyProcess(command)
        return SyncProcess(command)

    class BootstrapResult:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> BootstrapResult:
        assert check is False
        assert not popen_calls
        run_calls.append(command)
        return BootstrapResult()

    monkeypatch.setenv("SYNC_HEALTH_BIND_ADDRESS", "127.0.0.1")
    monkeypatch.setenv("SYNC_HEALTH_PORT", "9080")
    monkeypatch.setattr(wrapper.socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(wrapper.subprocess, "run", fake_run)
    monkeypatch.setattr(wrapper.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(wrapper.time, "sleep", lambda _seconds: None)

    assert wrapper.main() == 0
    assert run_calls == [wrapper._bootstrap_config_command()]
    assert health_processes == [
        [
            str(wrapper.sys.executable),
            str(wrapper.MANAGE_PY),
            "serve_sync_health",
            "--host",
            "127.0.0.1",
            "--port",
            "9080",
            "--stale-threshold-seconds",
            "900",
        ]
    ]
    assert sync_processes == [["bash", str(wrapper.SYNC_ENTRYPOINT)]]
    assert connections == [("127.0.0.1", 9080), ("127.0.0.1", 9080)]


def test_wrapper_fails_before_sync_if_health_exits_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processes: list[list[str]] = []

    class BootstrapResult:
        returncode = 0

    class DeadHealthProcess:
        returncode = 2

        def __init__(self, command: list[str]) -> None:
            processes.append(command)

        def poll(self) -> int:
            return 2

        def terminate(self) -> None:
            return None

        def wait(self, timeout: int | None = None) -> int:
            _ = timeout
            return 2

        def kill(self) -> None:
            return None

    monkeypatch.setattr(
        wrapper.subprocess,
        "run",
        lambda _command, *, check: BootstrapResult(),
    )
    monkeypatch.setattr(wrapper.subprocess, "Popen", DeadHealthProcess)
    monkeypatch.setattr(
        wrapper.socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("refused")),
    )

    assert wrapper.main() == 2
    assert processes == [wrapper._health_command()]


def test_wrapper_fails_before_children_when_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BootstrapResult:
        returncode = 4

    popen_calls: list[list[str]] = []

    monkeypatch.setattr(
        wrapper.subprocess,
        "run",
        lambda _command, *, check: BootstrapResult(),
    )
    monkeypatch.setattr(
        wrapper.subprocess,
        "Popen",
        lambda command: popen_calls.append(command),
    )

    assert wrapper.main() == 4
    assert popen_calls == []


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [
        ("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", ""),
        ("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", "banana"),
        ("SYNC_STALE_HEARTBEAT_SECONDS", ""),
        ("SYNC_STALE_HEARTBEAT_SECONDS", "banana"),
    ],
)
def test_health_command_falls_back_for_malformed_threshold_env(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
) -> None:
    monkeypatch.delenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", raising=False)
    monkeypatch.delenv("SYNC_STALE_HEARTBEAT_SECONDS", raising=False)
    monkeypatch.setenv(env_name, env_value)

    command = wrapper._health_command()

    assert command[-1] == "900"
