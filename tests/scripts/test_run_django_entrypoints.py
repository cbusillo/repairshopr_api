from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from repairshopr_api import run_django

MANAGE_SCRIPT = "/tmp/manage.py"


def _install_manage_runner(
    monkeypatch: pytest.MonkeyPatch,
    exit_codes: Mapping[str, int] | None = None,
) -> list[list[str]]:
    calls: list[list[str]] = []
    configured_exit_codes = exit_codes or {}

    def fake_run(argv: list[str]) -> subprocess.CompletedProcess[list[str]]:
        calls.append(list(argv))
        return subprocess.CompletedProcess(
            args=argv,
            returncode=configured_exit_codes.get(argv[2], 0),
        )

    monkeypatch.setattr(run_django.subprocess, "run", fake_run)
    monkeypatch.setattr(run_django, "_manage_script", lambda: MANAGE_SCRIPT)
    return calls


def _expected_calls(*commands: str) -> list[list[str]]:
    return [[run_django.sys.executable, MANAGE_SCRIPT, command] for command in commands]


@pytest.mark.scripts
@pytest.mark.parametrize(
    ("entrypoint", "command"),
    [
        pytest.param(run_django.makemigrations, "makemigrations", id="makemigrations"),
        pytest.param(run_django.migrate, "migrate", id="migrate"),
    ],
)
def test_direct_entrypoints_delegate_to_manage_script(
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: Callable[[], int],
    command: str,
) -> None:
    calls = _install_manage_runner(monkeypatch)

    assert entrypoint() == 0
    assert calls == _expected_calls(command)


@pytest.mark.scripts
@pytest.mark.parametrize(
    ("entrypoint", "exit_code"),
    [
        pytest.param(run_django.runserver, 2, id="runserver"),
        pytest.param(run_django.import_from_repairshopr, 4, id="import"),
    ],
)
def test_sequenced_entrypoints_stop_when_migrate_fails(
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: Callable[[], int],
    exit_code: int,
) -> None:
    calls = _install_manage_runner(monkeypatch, {"migrate": exit_code})

    assert entrypoint() == exit_code
    assert calls == _expected_calls("migrate")


@pytest.mark.scripts
@pytest.mark.parametrize(
    ("entrypoint", "terminal_command", "exit_code"),
    [
        pytest.param(run_django.runserver, "runserver", 0, id="runserver-success"),
        pytest.param(run_django.runserver, "runserver", 7, id="runserver-failure"),
        pytest.param(
            run_django.import_from_repairshopr,
            "import_from_repairshopr",
            0,
            id="import-success",
        ),
        pytest.param(
            run_django.import_from_repairshopr,
            "import_from_repairshopr",
            8,
            id="import-failure",
        ),
    ],
)
def test_sequenced_entrypoints_run_full_sequence_and_propagate_terminal_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: Callable[[], int],
    terminal_command: str,
    exit_code: int,
) -> None:
    calls = _install_manage_runner(monkeypatch, {terminal_command: exit_code})

    assert entrypoint() == exit_code
    assert calls == _expected_calls("migrate", terminal_command)


@pytest.mark.scripts
@pytest.mark.parametrize(
    "module_spec",
    [
        pytest.param(None, id="missing-spec"),
        pytest.param(SimpleNamespace(origin=None), id="missing-origin"),
    ],
)
def test_manage_script_requires_locatable_module(
    monkeypatch: pytest.MonkeyPatch,
    module_spec: object | None,
) -> None:
    monkeypatch.setattr("repairshopr_api.run_django.find_spec", lambda _module_name: module_spec)

    with pytest.raises(RuntimeError, match="Could not locate repairshopr_sync.manage"):
        run_django._manage_script()


@pytest.mark.scripts
def test_manage_script_resolves_spec_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manage_script = tmp_path / "manage.py"
    monkeypatch.setattr(
        "repairshopr_api.run_django.find_spec",
        lambda _module_name: SimpleNamespace(origin=str(manage_script)),
    )

    assert Path(run_django._manage_script()) == manage_script.resolve()
