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
CREDENTIAL_FIELDS = (
    ("repairshopr", "token"),
    ("django", "secret_key"),
    ("django", "db_password"),
)


def require_env(name: str) -> None:
    if not os.getenv(name, "").strip():
        raise SystemExit(f"Missing {name}")


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def config_file_path() -> Path:
    configured_path = os.getenv("REPAIRSHOPR_CONFIG_FILE") or os.getenv("CONFIG_FILE")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".config" / "repairshopr-api" / "config.toml"


def bootstrap_config() -> Path:
    for env_var in REQUIRED_ENV_VARS:
        require_env(env_var)

    config_file = config_file_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if config_file.exists():
        try:
            data = toml.load(config_file)
        except toml.TomlDecodeError:
            data = {}

    data["debug"] = truthy(os.getenv("REPAIRSHOPR_DEBUG", "false"))
    for section, key in CREDENTIAL_FIELDS:
        data.get(section, {}).pop(key, None)

    with config_file.open("w") as handle:
        toml.dump(data, handle)

    return config_file


def main() -> int:
    bootstrap_config()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
