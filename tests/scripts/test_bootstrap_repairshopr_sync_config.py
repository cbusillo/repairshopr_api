from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import toml

from repairshopr_api.config.base import AppSettings
from scripts import bootstrap_repairshopr_sync_config as bootstrap

RUNTIME_SECRETS = {
    "REPAIRSHOPR_TOKEN": "env-repairshopr-token",
    "SYNC_DB_PASSWORD": "env-sync-password",
    "DJANGO_SECRET_KEY": "env-django-secret",
}


@pytest.fixture
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPAIRSHOPR_CONFIG_FILE", str(tmp_path / "config.toml"))
    monkeypatch.setenv("REPAIRSHOPR_URL_STORE_NAME", "store-name")
    monkeypatch.setenv("SYNC_DB_HOST", "mysql")
    for name, value in RUNTIME_SECRETS.items():
        monkeypatch.setenv(name, value)


@pytest.mark.usefixtures("runtime_env")
def test_bootstrap_config_leaves_no_secret_in_config_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    checkpoint = datetime(2026, 10, 1, 12, tzinfo=UTC)
    previous_secrets = ("old-token", "old-django-secret", "old-db-password")
    config_file.write_text(
        toml.dumps(
            {
                "repairshopr": {"token": "old-token", "url_store_name": "store"},
                "django": {
                    "secret_key": "old-django-secret",
                    "db_password": "old-db-password",
                    "last_updated_at": checkpoint,
                },
            }
        )
    )

    assert bootstrap.bootstrap_config() == config_file

    config_text = config_file.read_text()
    for secret in (*RUNTIME_SECRETS.values(), *previous_secrets):
        assert secret not in config_text
    assert toml.loads(config_text)["django"]["last_updated_at"] == checkpoint


@pytest.mark.usefixtures("runtime_env")
def test_bootstrap_config_records_debug_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPAIRSHOPR_DEBUG", "true")

    bootstrap.bootstrap_config()

    assert toml.load(tmp_path / "config.toml")["debug"] is True


@pytest.mark.usefixtures("runtime_env")
@pytest.mark.parametrize("missing_var", bootstrap.REQUIRED_ENV_VARS)
def test_bootstrap_config_fails_closed_when_required_env_missing(monkeypatch: pytest.MonkeyPatch, missing_var: str) -> None:
    monkeypatch.delenv(missing_var)

    with pytest.raises(SystemExit, match=missing_var):
        bootstrap.bootstrap_config()


@pytest.mark.usefixtures("runtime_env")
@pytest.mark.parametrize(
    "path_env_vars",
    [
        ("REPAIRSHOPR_CONFIG_FILE",),
        ("CONFIG_FILE",),
        ("REPAIRSHOPR_CONFIG_FILE", "CONFIG_FILE"),
        (),
    ],
)
def test_bootstrap_config_cleans_the_file_app_settings_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path_env_vars: tuple[str, ...]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("REPAIRSHOPR_CONFIG_FILE")
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    for name in path_env_vars:
        monkeypatch.setenv(name, str(tmp_path / f"{name}.toml"))

    config_file = bootstrap.bootstrap_config()

    assert config_file == AppSettings().config_file_path
