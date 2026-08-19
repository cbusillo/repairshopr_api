from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker" / "coolify" / "compose.yml"
ADDON_COMPOSE_PATH = ROOT / "addons" / "repairshopr-sync" / "compose.yml"
TESTS_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "tests.yml"
DEPENDABOT_PATH = ROOT / ".github" / "dependabot.yml"
GITHUB_CONFIG_PATH = ROOT / ".github" / "github.json"


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

    assert (
        'x-launchplane-image: &launchplane-image "${DOCKER_IMAGE_REFERENCE:?DOCKER_IMAGE_REFERENCE is required}"'
        in compose_text
    )
    assert "image: *launchplane-image" in compose_text
    assert "build:" not in compose_text
    assert "dockerfile: docker/Dockerfile.sync" not in compose_text


def test_database_integration_uses_product_mariadb_image() -> None:
    compose_text = ADDON_COMPOSE_PATH.read_text(encoding="utf-8")
    workflow_text = TESTS_WORKFLOW_PATH.read_text(encoding="utf-8")
    github_config = json.loads(GITHUB_CONFIG_PATH.read_text(encoding="utf-8"))

    assert "mysql-integration:" in workflow_text
    assert "image: mysql:" not in workflow_text
    assert re.search(r"^\s+image:\s+mariadb:\d", workflow_text, re.MULTILINE) is None
    assert "addons/repairshopr-sync/compose.yml" in workflow_text
    assert "jq -er '.services.db.image'" in workflow_text
    assert 'RUN_MARIADB_INTEGRATION: "1"' in workflow_text
    assert "image: mariadb:" in compose_text
    assert "mysql-integration" in github_config["requiredStatusChecks"]
    mariadb_gate = github_config["qualityGate"]["test"]["mariadbIntegration"]
    assert "RUN_MARIADB_INTEGRATION=1" in mariadb_gate


def test_dependabot_monitors_product_mariadb_compose() -> None:
    dependabot_text = DEPENDABOT_PATH.read_text(encoding="utf-8")

    required_block = """  - package-ecosystem: docker-compose
    directories:
      - "/addons/repairshopr-sync"
    schedule:
      interval: weekly
"""
    assert required_block in dependabot_text


def test_sync_compose_keeps_live_runtime_authority_out_of_repo() -> None:
    compose_text = ADDON_COMPOSE_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "LAUNCHPLANE_HEALTH_URL",
        "repairshopr-sync/prod",
        "192.168.",
        "https://",
    )
    for fragment in forbidden_fragments:
        assert fragment not in compose_text
