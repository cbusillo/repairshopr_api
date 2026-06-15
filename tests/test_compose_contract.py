from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker" / "coolify" / "compose.yml"
GITHUB_JSON_PATH = ROOT / ".github" / "github.json"


def test_sync_compose_declares_internal_health_port_without_host_publish() -> None:
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "SYNC_HEALTH_BIND_ADDRESS: ${SYNC_HEALTH_BIND_ADDRESS:-0.0.0.0}" in compose_text
    assert "SYNC_HEALTH_PORT: ${SYNC_HEALTH_PORT:-8000}" in compose_text
    assert 'expose:\n      - "${SYNC_HEALTH_PORT:-8000}"' in compose_text
    assert '"${SYNC_HEALTH_PORT:-8000}:${SYNC_HEALTH_PORT:-8000}"' not in compose_text
    assert "traefik." not in compose_text
    assert "caddy." not in compose_text
    assert "nginx." not in compose_text


def test_launchplane_metadata_does_not_store_live_health_urls() -> None:
    github_json_text = GITHUB_JSON_PATH.read_text(encoding="utf-8")

    assert '"healthUrls": []' in github_json_text
