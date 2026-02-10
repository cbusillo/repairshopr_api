from __future__ import annotations

import subprocess

import pytest

from repairshopr_api import run_django


@pytest.mark.scripts
def test_runserver_propagates_manage_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    manage_script = "/tmp/manage.py"

    def fake_run(argv: list[str]) -> subprocess.CompletedProcess[list[str]]:
        calls.append(list(argv))
        command = argv[-1]
        returncode = 0
        if command == "migrate":
            returncode = 2
        return subprocess.CompletedProcess(args=argv, returncode=returncode)

    monkeypatch.setattr(run_django.subprocess, "run", fake_run)
    monkeypatch.setattr(run_django, "_manage_script", lambda: manage_script)

    exit_code = run_django.runserver()

    assert exit_code == 2
    assert calls == [
        [run_django.sys.executable, manage_script, "makemigrations"],
        [run_django.sys.executable, manage_script, "migrate"],
    ]


@pytest.mark.scripts
def test_import_propagates_manage_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    manage_script = "/tmp/manage.py"

    def fake_run(argv: list[str]) -> subprocess.CompletedProcess[list[str]]:
        calls.append(list(argv))
        command = argv[-1]
        returncode = 0
        if command == "makemigrations":
            returncode = 3
        return subprocess.CompletedProcess(args=argv, returncode=returncode)

    monkeypatch.setattr(run_django.subprocess, "run", fake_run)
    monkeypatch.setattr(run_django, "_manage_script", lambda: manage_script)

    exit_code = run_django.import_from_repairshopr()

    assert exit_code == 3
    assert calls == [
        [run_django.sys.executable, manage_script, "makemigrations"],
    ]
