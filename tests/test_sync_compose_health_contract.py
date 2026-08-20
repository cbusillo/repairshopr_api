from __future__ import annotations

import json
import re
from pathlib import Path

from tests.compose_contract import (
    ADDON_COMPOSE_PATH,
    COOLIFY_COMPOSE_PATH,
    DEPENDABOT_PATH,
    LAUNCHPLANE_IMAGE_REFERENCE,
    compose_service,
    compose_services,
    dependabot_directories,
    include_paths,
    iter_scalar_texts,
    load_yaml_mapping,
    service_environment,
    service_ports,
)

ROOT = Path(__file__).resolve().parents[1]
TESTS_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "tests.yml"
GITHUB_CONFIG_PATH = ROOT / ".github" / "github.json"


def test_coolify_compose_entrypoint_loads_product_addon_contract() -> None:
    document = load_yaml_mapping(COOLIFY_COMPOSE_PATH)

    assert document.get("name") == "repairshopr-sync"
    assert ADDON_COMPOSE_PATH.resolve() in include_paths(
        document, COOLIFY_COMPOSE_PATH.parent
    )


def test_sync_compose_exposes_health_port_for_launchplane() -> None:
    sync_service = compose_service(load_yaml_mapping(ADDON_COMPOSE_PATH), "sync")
    environment = service_environment(sync_service)

    assert (
        environment["SYNC_HEALTH_BIND_ADDRESS"]
        == "${SYNC_HEALTH_BIND_ADDRESS:-0.0.0.0}"
    )
    assert environment["SYNC_HEALTH_PORT"] == "${SYNC_HEALTH_PORT:-8000}"
    assert "${SYNC_HEALTH_HOST_PORT:-8000}:${SYNC_HEALTH_PORT:-8000}" in service_ports(
        sync_service
    )

    healthcheck = sync_service.get("healthcheck")
    assert isinstance(healthcheck, dict)
    assert healthcheck.get("disable") is not True
    healthcheck_test = healthcheck.get("test")
    assert isinstance(healthcheck_test, list)
    assert healthcheck_test[0] == "CMD"
    assert any(
        "http://127.0.0.1:${SYNC_HEALTH_PORT:-8000}/health" in str(part)
        for part in healthcheck_test
    )


def test_sync_compose_consumes_launchplane_image_reference() -> None:
    document = load_yaml_mapping(ADDON_COMPOSE_PATH)
    sync_service = compose_service(document, "sync")

    assert document.get("x-launchplane-image") == LAUNCHPLANE_IMAGE_REFERENCE
    assert sync_service.get("image") == LAUNCHPLANE_IMAGE_REFERENCE
    for service_name, service in compose_services(document).items():
        assert isinstance(service, dict), f"service {service_name!r} must be a mapping"
        assert "build" not in service, service_name


def test_database_integration_uses_product_mariadb_image() -> None:
    database_service = compose_service(load_yaml_mapping(ADDON_COMPOSE_PATH), "db")
    workflow_text = TESTS_WORKFLOW_PATH.read_text(encoding="utf-8")
    github_config = json.loads(GITHUB_CONFIG_PATH.read_text(encoding="utf-8"))

    assert "mysql-integration:" in workflow_text
    assert "image: mysql:" not in workflow_text
    assert re.search(r"^\s+image:\s+mariadb:\d", workflow_text, re.MULTILINE) is None
    assert "addons/repairshopr-sync/compose.yml" in workflow_text
    assert "jq -er '.services.db.image'" in workflow_text
    assert 'RUN_MARIADB_INTEGRATION: "1"' in workflow_text
    database_image = database_service.get("image")
    assert isinstance(database_image, str)
    assert database_image.startswith("mariadb:")
    assert "mysql-integration" in github_config["requiredStatusChecks"]
    mariadb_gate = github_config["qualityGate"]["test"]["mariadbIntegration"]
    assert "RUN_MARIADB_INTEGRATION=1" in mariadb_gate


def test_dependabot_monitors_product_mariadb_compose() -> None:
    dependabot = load_yaml_mapping(DEPENDABOT_PATH)
    updates = dependabot.get("updates")
    assert isinstance(updates, list)
    compose_updates = [
        update
        for update in updates
        if isinstance(update, dict)
        and update.get("package-ecosystem") == "docker-compose"
    ]

    assert len(compose_updates) == 1
    compose_update = compose_updates[0]
    assert dependabot_directories(compose_update) == ["/addons/repairshopr-sync"]
    schedule = compose_update.get("schedule")
    assert isinstance(schedule, dict)
    assert schedule.get("interval") == "weekly"


def test_sync_compose_keeps_live_runtime_authority_out_of_repo() -> None:
    scalar_texts = tuple(iter_scalar_texts(load_yaml_mapping(ADDON_COMPOSE_PATH)))

    forbidden_fragments = (
        "LAUNCHPLANE_HEALTH_URL",
        "repairshopr-sync/prod",
        "192.168.",
        "https://",
    )
    for fragment in forbidden_fragments:
        assert not any(fragment in text for text in scalar_texts), fragment
