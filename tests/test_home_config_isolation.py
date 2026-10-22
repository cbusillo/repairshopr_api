from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

PathOperation = Callable[[Path], object]


def test_settings_never_use_the_home_config(home_config_dir: Path) -> None:
    from repairshopr_api.config import settings

    assert not settings.config_file_path.is_relative_to(home_config_dir)


@pytest.mark.parametrize("touch", [Path.open, Path.rmdir], ids=["open", "rmdir"])
def test_home_config_access_fails(home_config_dir: Path, touch: PathOperation) -> None:
    with pytest.raises(pytest.fail.Exception, match="home config"):
        touch(home_config_dir / "guard-probe")
