from __future__ import annotations

from pathlib import Path

import pytest

from tests.compose_contract import (
    dependabot_directories,
    include_paths,
    service_environment,
    service_ports,
)


def test_compose_helpers_normalize_supported_yaml_shapes(tmp_path: Path) -> None:
    assert service_environment({"environment": ["FIRST=1", "EMPTY"]}) == {
        "FIRST": "1",
        "EMPTY": "",
    }
    assert service_ports({"ports": [{"published": 8000, "target": 8000}]}) == [
        "8000:8000"
    ]
    assert include_paths(
        {"include": [{"path": ["first.yml", "second.yml"]}]}, tmp_path
    ) == [
        (tmp_path / "first.yml").resolve(),
        (tmp_path / "second.yml").resolve(),
    ]
    assert dependabot_directories({"directory": "/single"}) == ["/single"]
    assert dependabot_directories({"directories": ["/first", "/second"]}) == [
        "/first",
        "/second",
    ]


def test_compose_helper_rejects_unquoted_short_form_ports() -> None:
    with pytest.raises(AssertionError, match="short-form compose ports must be quoted"):
        service_ports({"ports": [1342]})
