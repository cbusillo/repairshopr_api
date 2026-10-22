from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYNC_ROOT = ROOT / "repairshopr_sync"

if str(SYNC_ROOT) not in sys.path:
    sys.path.insert(0, str(SYNC_ROOT))

HOME_CONFIG_DIR = Path.home() / ".config" / "repairshopr-api"
SESSION_CONFIG_DIR = Path(tempfile.mkdtemp(prefix="repairshopr-api-tests-"))
os.environ["REPAIRSHOPR_CONFIG_FILE"] = str(SESSION_CONFIG_DIR / "config.toml")

PATH_ARGUMENT_COUNTS_BY_AUDIT_EVENT = {
    "open": 1,
    "os.mkdir": 1,
    "os.remove": 1,
    "os.rename": 2,
    "os.rmdir": 1,
}


def _is_home_config_path(path: object) -> bool:
    if not isinstance(path, (str, bytes, os.PathLike)):
        return False
    return Path(os.path.abspath(os.fsdecode(path))).is_relative_to(HOME_CONFIG_DIR)


def _fail_on_home_config_access(event: str, arguments: tuple[object, ...]) -> None:
    path_count = PATH_ARGUMENT_COUNTS_BY_AUDIT_EVENT.get(event)
    if path_count is None:
        return
    if any(_is_home_config_path(path) for path in arguments[:path_count]):
        pytest.fail(
            f"Test touched the developer's home config: {event} under {HOME_CONFIG_DIR}"
        )


sys.addaudithook(_fail_on_home_config_access)


def pytest_unconfigure() -> None:
    shutil.rmtree(SESSION_CONFIG_DIR, ignore_errors=True)


@pytest.fixture
def home_config_dir() -> Path:
    return HOME_CONFIG_DIR
