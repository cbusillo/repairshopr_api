from __future__ import annotations

from pathlib import Path

ADDON_COMPOSE_PATH = (
    Path(__file__).resolve().parents[1] / "addons" / "repairshopr-sync" / "compose.yml"
)


def test_sync_compose_propagates_launchplane_runtime_identity() -> None:
    compose_text = ADDON_COMPOSE_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "DOCKER_IMAGE_REFERENCE: ${DOCKER_IMAGE_REFERENCE}",
        "LAUNCHPLANE_ARTIFACT_ID: ${LAUNCHPLANE_ARTIFACT_ID:-}",
        "LAUNCHPLANE_DEPLOYMENT_RECORD_ID: ${LAUNCHPLANE_DEPLOYMENT_RECORD_ID:-}",
        "LAUNCHPLANE_RUNTIME_IDENTITY_JSON: ${LAUNCHPLANE_RUNTIME_IDENTITY_JSON:-}",
        "LAUNCHPLANE_SOURCE_GIT_REF: ${LAUNCHPLANE_SOURCE_GIT_REF:-}",
    )
    for fragment in required_fragments:
        assert fragment in compose_text
