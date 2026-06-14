from __future__ import annotations

import toml

from scripts import bootstrap_repairshopr_sync_config as bootstrap


def test_bootstrap_config_writes_runtime_env_values(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.setenv("REPAIRSHOPR_TOKEN", "repairshopr-token")
    monkeypatch.setenv("REPAIRSHOPR_URL_STORE_NAME", "store-name")
    monkeypatch.setenv("SYNC_DB_HOST", "mysql")
    monkeypatch.setenv("SYNC_DB_PASSWORD", "sync-password")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "django-secret")
    monkeypatch.setenv("SYNC_DB_NAME", "sync-db")
    monkeypatch.setenv("SYNC_DB_USER", "sync-user")
    monkeypatch.setenv("REPAIRSHOPR_DEBUG", "true")

    assert bootstrap.bootstrap_config() == config_file

    data = toml.load(config_file)
    assert data["debug"] is True
    assert data["repairshopr"] == {
        "token": "repairshopr-token",
        "url_store_name": "store-name",
    }
    assert data["django"] == {
        "secret_key": "django-secret",
        "db_engine": "mysql",
        "db_host": "mysql",
        "db_name": "sync-db",
        "db_user": "sync-user",
        "db_password": "sync-password",
    }


def test_bootstrap_config_fails_closed_when_required_env_missing(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CONFIG_FILE", str(tmp_path / "config.toml"))
    monkeypatch.setenv("REPAIRSHOPR_TOKEN", "repairshopr-token")
    monkeypatch.setenv("REPAIRSHOPR_URL_STORE_NAME", "store-name")
    monkeypatch.setenv("SYNC_DB_HOST", "mysql")
    monkeypatch.setenv("SYNC_DB_PASSWORD", "sync-password")
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

    try:
        bootstrap.bootstrap_config()
    except SystemExit as error:
        assert str(error) == "Missing DJANGO_SECRET_KEY"
    else:
        raise AssertionError("bootstrap_config should fail when required env is missing")
