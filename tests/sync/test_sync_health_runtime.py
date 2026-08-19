from __future__ import annotations

import pytest

from repairshopr_data.sync_health import image_reference


def test_image_reference_uses_deployed_docker_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_reference = "ghcr.io/example/repairshopr@sha256:abc123"
    monkeypatch.delenv("LAUNCHPLANE_IMAGE_REFERENCE", raising=False)
    monkeypatch.setenv("DOCKER_IMAGE_REFERENCE", expected_reference)
    monkeypatch.delenv("IMAGE_REFERENCE", raising=False)

    assert image_reference() == expected_reference
