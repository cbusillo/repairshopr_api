from __future__ import annotations

from datetime import datetime, timezone

import pytest
import toml

from scripts import bootstrap_repairshopr_sync_config as bootstrap

RUNTIME_SECRETS = {
    "REPAIRSHOPR_TOKEN": "env-repairshopr-token",
    "SYNC_DB_PASSWORD": "env-sync-password",
    "DJANGO_SECRET_KEY": "env-django-secret",
}


@pytest.fixture
def runtime_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", str(tmp_path / "config.toml"))
    monkeypatch.setenv("REPAIRSHOPR_URL_STORE_NAME", "store-name")
    monkeypatch.setenv("SYNC_DB_HOST", "mysql")
    for name, value in RUNTIME_SECRETS.items():
        monkeypatch.setenv(name, value)


@pytest.mark.usefixtures("runtime_env")
def test_bootstrap_config_leaves_no_secret_in_config_file(tmp_path) -> None:
    config_file = tmp_path / "config.toml"
    checkpoint = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
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
def test_bootstrap_config_records_debug_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REPAIRSHOPR_DEBUG", "true")

    bootstrap.bootstrap_config()

    assert toml.load(tmp_path / "config.toml")["debug"] is True


@pytest.mark.usefixtures("runtime_env")
@pytest.mark.parametrize("missing_var", bootstrap.REQUIRED_ENV_VARS)
def test_bootstrap_config_fails_closed_when_required_env_missing(
    monkeypatch, missing_var: str
) -> None:
    monkeypatch.delenv(missing_var)

    with pytest.raises(SystemExit, match=missing_var):
        bootstrap.bootstrap_config()
