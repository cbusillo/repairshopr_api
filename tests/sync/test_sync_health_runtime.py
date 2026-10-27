from __future__ import annotations

import pytest
from repairshopr_data.management.commands import serve_sync_health, sync_status
from repairshopr_data.sync_health import (
    DEFAULT_STALE_THRESHOLD_SECONDS,
    configured_stale_threshold_seconds,
    image_reference,
)


def test_image_reference_uses_deployed_docker_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_reference = "ghcr.io/example/repairshopr@sha256:abc123"
    monkeypatch.delenv("LAUNCHPLANE_IMAGE_REFERENCE", raising=False)
    monkeypatch.setenv("DOCKER_IMAGE_REFERENCE", expected_reference)
    monkeypatch.delenv("IMAGE_REFERENCE", raising=False)

    assert image_reference() == expected_reference


@pytest.fixture
def no_threshold_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", raising=False)
    monkeypatch.delenv("SYNC_STALE_HEARTBEAT_SECONDS", raising=False)


@pytest.mark.usefixtures("no_threshold_env")
def test_stale_threshold_prefers_health_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", "45")
    monkeypatch.setenv("SYNC_STALE_HEARTBEAT_SECONDS", "30")

    assert configured_stale_threshold_seconds() == 45


@pytest.mark.usefixtures("no_threshold_env")
@pytest.mark.parametrize("health_value", ["", "banana"])
def test_stale_threshold_skips_unusable_health_setting(monkeypatch: pytest.MonkeyPatch, health_value: str) -> None:
    monkeypatch.setenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", health_value)
    monkeypatch.setenv("SYNC_STALE_HEARTBEAT_SECONDS", "30")

    assert configured_stale_threshold_seconds() == 30


@pytest.mark.usefixtures("no_threshold_env")
@pytest.mark.parametrize("heartbeat_value", ["", "banana"])
def test_stale_threshold_falls_back_to_default(monkeypatch: pytest.MonkeyPatch, heartbeat_value: str) -> None:
    monkeypatch.setenv("SYNC_STALE_HEARTBEAT_SECONDS", heartbeat_value)

    assert configured_stale_threshold_seconds() == DEFAULT_STALE_THRESHOLD_SECONDS


@pytest.mark.usefixtures("no_threshold_env")
@pytest.mark.parametrize("command", [serve_sync_health.Command, sync_status.Command])
def test_health_commands_default_to_configured_threshold(monkeypatch: pytest.MonkeyPatch, command: type) -> None:
    monkeypatch.setenv("SYNC_STALE_HEARTBEAT_SECONDS", "45")

    parser = command().create_parser("manage.py", "health-command")

    assert parser.parse_args([]).stale_threshold_seconds == 45
