from __future__ import annotations

import os
from pathlib import Path

import toml


REQUIRED_ENV_VARS = (
    "REPAIRSHOPR_TOKEN",
    "REPAIRSHOPR_URL_STORE_NAME",
    "SYNC_DB_HOST",
    "SYNC_DB_PASSWORD",
    "DJANGO_SECRET_KEY",
)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing {name}")
    return value


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def config_file_path() -> Path:
    configured_path = os.getenv("CONFIG_FILE", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    config_root = Path(os.getenv("HOME", "/var/lib/repairshopr")) / ".config" / "repairshopr-api"
    return config_root / "config.toml"


def bootstrap_config() -> Path:
    for env_var in REQUIRED_ENV_VARS:
        require_env(env_var)

    sync_db_name = os.getenv("SYNC_DB_NAME", "repairshopr")
    sync_db_user = os.getenv("SYNC_DB_USER", "repairshopr_api")
    config_file = config_file_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if config_file.exists():
        try:
            data = toml.load(config_file)
        except toml.TomlDecodeError:
            data = {}

    data.setdefault("repairshopr", {})
    data.setdefault("django", {})

    data["debug"] = truthy(os.getenv("REPAIRSHOPR_DEBUG", "false"))
    data["repairshopr"]["token"] = require_env("REPAIRSHOPR_TOKEN")
    data["repairshopr"]["url_store_name"] = require_env("REPAIRSHOPR_URL_STORE_NAME")
    data["django"]["secret_key"] = require_env("DJANGO_SECRET_KEY")
    data["django"]["db_engine"] = "mysql"
    data["django"]["db_host"] = require_env("SYNC_DB_HOST")
    data["django"]["db_name"] = sync_db_name
    data["django"]["db_user"] = sync_db_user
    data["django"]["db_password"] = require_env("SYNC_DB_PASSWORD")

    with config_file.open("w") as handle:
        toml.dump(data, handle)

    return config_file


def main() -> int:
    config_file = bootstrap_config()
    print(config_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
