from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker" / "coolify" / "compose.yml"
ADDON_COMPOSE_PATH = ROOT / "addons" / "repairshopr-sync" / "compose.yml"


def test_coolify_compose_entrypoint_loads_product_addon_contract() -> None:
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "name: repairshopr-sync" in compose_text
    assert "../../addons/repairshopr-sync/compose.yml" in compose_text


def test_sync_compose_exposes_health_port_for_launchplane() -> None:
    compose_text = ADDON_COMPOSE_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "SYNC_HEALTH_BIND_ADDRESS: ${SYNC_HEALTH_BIND_ADDRESS:-0.0.0.0}",
        "SYNC_HEALTH_PORT: ${SYNC_HEALTH_PORT:-8000}",
        '"${SYNC_HEALTH_HOST_PORT:-8000}:${SYNC_HEALTH_PORT:-8000}"',
        "http://127.0.0.1:${SYNC_HEALTH_PORT:-8000}/health",
    )
    for fragment in required_fragments:
        assert fragment in compose_text


def test_sync_compose_consumes_launchplane_image_reference() -> None:
    compose_text = ADDON_COMPOSE_PATH.read_text(encoding="utf-8")

    assert "image: ${DOCKER_IMAGE_REFERENCE:?DOCKER_IMAGE_REFERENCE is required}" in compose_text
    assert "build:" not in compose_text
    assert "dockerfile: docker/Dockerfile.sync" not in compose_text


def test_sync_compose_keeps_live_runtime_authority_out_of_repo() -> None:
    compose_text = ADDON_COMPOSE_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "LAUNCHPLANE_HEALTH_URL",
        "repairshopr-sync/prod",
        "192.168.",
        "http://192.",
        "https://",
    )
    for fragment in forbidden_fragments:
        assert fragment not in compose_text
