from __future__ import annotations

import runpy
from pathlib import Path

import pytest

SYNC_SETTINGS = (
    Path(__file__).resolve().parents[2]
    / "repairshopr_sync"
    / "repairshopr_sync"
    / "settings.py"
)


def test_sync_settings_read_secrets_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", "env-secret")
    monkeypatch.setenv("SYNC_DB_PASSWORD", "env-password")
    monkeypatch.setenv("SYNC_DB_USER", "env-user")

    sync_settings = runpy.run_path(str(SYNC_SETTINGS))

    assert sync_settings["SECRET_KEY"] == "env-secret"
    assert sync_settings["DATABASES"]["default"]["PASSWORD"] == "env-password"
    assert sync_settings["DATABASES"]["default"]["USER"] == "env-user"


def test_sync_settings_require_django_secret_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

    with pytest.raises(KeyError, match="DJANGO_SECRET_KEY"):
        runpy.run_path(str(SYNC_SETTINGS))
