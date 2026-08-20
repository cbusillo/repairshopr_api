from __future__ import annotations

from tests.compose_contract import (
    ADDON_COMPOSE_PATH,
    compose_service,
    load_yaml_mapping,
    service_environment,
)


def test_sync_compose_propagates_launchplane_runtime_identity() -> None:
    sync_environment = service_environment(
        compose_service(load_yaml_mapping(ADDON_COMPOSE_PATH), "sync")
    )

    expected_values = {
        "DOCKER_IMAGE_REFERENCE": "${DOCKER_IMAGE_REFERENCE}",
        "LAUNCHPLANE_ARTIFACT_ID": "${LAUNCHPLANE_ARTIFACT_ID:-}",
        "LAUNCHPLANE_DEPLOYMENT_RECORD_ID": "${LAUNCHPLANE_DEPLOYMENT_RECORD_ID:-}",
        "LAUNCHPLANE_RUNTIME_IDENTITY_JSON": "${LAUNCHPLANE_RUNTIME_IDENTITY_JSON:-}",
        "LAUNCHPLANE_SOURCE_GIT_REF": "${LAUNCHPLANE_SOURCE_GIT_REF:-}",
    }
    for key, expected_value in expected_values.items():
        assert sync_environment[key] == expected_value
