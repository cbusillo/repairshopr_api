from __future__ import annotations

from pathlib import Path

import pytest


def test_settings_never_use_the_home_config(home_config_dir: Path) -> None:
    from repairshopr_api.config import settings

    assert not settings.config_file_path.is_relative_to(home_config_dir)


def test_touching_the_home_config_fails_the_test(home_config_dir: Path) -> None:
    with pytest.raises(pytest.fail.Exception, match="home config"):
        (home_config_dir / "guard-probe.toml").open()
