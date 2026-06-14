from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from repairshopr_data.models import SyncStatus
from repairshopr_data.views import health


@pytest.fixture(autouse=True)
def health_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in (
        "GITHUB_SHA",
        "IMAGE_REFERENCE",
        "LAUNCHPLANE_ARTIFACT_ID",
        "LAUNCHPLANE_CONTEXT",
        "LAUNCHPLANE_DEPLOYMENT_RECORD_ID",
        "LAUNCHPLANE_ENVIRONMENT_KIND",
        "LAUNCHPLANE_IMAGE_REFERENCE",
        "LAUNCHPLANE_INSTANCE",
        "LAUNCHPLANE_PRODUCT",
        "LAUNCHPLANE_RUNTIME_IDENTITY_JSON",
        "LAUNCHPLANE_SOURCE_GIT_REF",
        "SYNC_HEALTH_STALE_THRESHOLD_SECONDS",
        "SYNC_STALE_HEARTBEAT_SECONDS",
    ):
        monkeypatch.delenv(env_name, raising=False)


def _payload(response) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return json.loads(response.content.decode())


@pytest.mark.django_db
def test_health_ready_payload_includes_sync_and_runtime_identity(
    rf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    current_time = datetime(2026, 2, 12, 18, tzinfo=timezone.utc)
    monkeypatch.setenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", "60")
    monkeypatch.setenv(
        "LAUNCHPLANE_RUNTIME_IDENTITY_JSON",
        json.dumps(
            {
                "schema_version": 1,
                "product": "repairshopr-sync",
                "context": "stable",
                "instance": "sync-1",
                "environment_kind": "stable",
                "deployment_record_id": "deploy-123",
                "artifact_id": "artifact-123",
                "source_git_ref": "abc123",
            }
        ),
    )
    monkeypatch.setattr("repairshopr_data.sync_health.now", lambda: current_time)
    SyncStatus.objects.create(
        id=1,
        status="success",
        mode="incremental",
        cycle_id="cycle-123",
        current_model="invoice",
        current_page=1,
        records_processed=20,
        cycle_started_at=current_time - timedelta(minutes=2),
        cycle_finished_at=current_time - timedelta(seconds=10),
        last_heartbeat=current_time - timedelta(seconds=10),
        last_error=None,
    )

    response = health(rf.get("/readyz"))

    assert response.status_code == 200
    payload = _payload(response)
    assert payload["service"] == "repairshopr-sync"
    assert payload["status"] == "ok"
    assert payload["source_git_ref"] == "abc123"
    assert payload["runtime_identity"] == {
        "schema_version": 1,
        "product": "repairshopr-sync",
        "context": "stable",
        "instance": "sync-1",
        "environment_kind": "stable",
        "deployment_record_id": "deploy-123",
        "artifact_id": "artifact-123",
        "source_git_ref": "abc123",
    }
    sync = payload["sync"]
    assert isinstance(sync, dict)
    assert sync["status"] == "success"
    assert sync["freshness_status"] == "fresh"
    assert sync["heartbeat_age_seconds"] == 10


@pytest.mark.django_db
def test_health_not_ready_when_running_sync_is_stale(
    rf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    current_time = datetime(2026, 2, 12, 18, tzinfo=timezone.utc)
    monkeypatch.setenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS", "30")
    monkeypatch.setattr("repairshopr_data.sync_health.now", lambda: current_time)
    SyncStatus.objects.create(
        id=1,
        status="running",
        mode="incremental",
        cycle_id="cycle-123",
        current_model="ticket",
        current_page=2,
        records_processed=30,
        cycle_started_at=current_time - timedelta(minutes=5),
        cycle_finished_at=None,
        last_heartbeat=current_time - timedelta(minutes=2),
        last_error=None,
    )

    response = health(rf.get("/readyz"))

    assert response.status_code == 503
    payload = _payload(response)
    assert payload["status"] == "not_ready"
    assert "sync_stale" in payload["not_ready_reasons"]
    sync = payload["sync"]
    assert isinstance(sync, dict)
    assert sync["is_stale"] is True
    assert sync["freshness_status"] == "stale"


@pytest.mark.django_db
def test_health_not_ready_when_last_cycle_failed(
    rf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    current_time = datetime(2026, 2, 12, 18, tzinfo=timezone.utc)
    monkeypatch.setattr("repairshopr_data.sync_health.now", lambda: current_time)
    SyncStatus.objects.create(
        id=1,
        status="failed",
        mode="incremental",
        cycle_id="cycle-123",
        current_model="ticket",
        current_page=2,
        records_processed=30,
        cycle_started_at=current_time - timedelta(minutes=5),
        cycle_finished_at=current_time - timedelta(minutes=4),
        last_heartbeat=current_time - timedelta(minutes=4),
        last_error="boom",
    )

    response = health(rf.get("/readyz"))

    assert response.status_code == 503
    payload = _payload(response)
    assert "sync_failed" in payload["not_ready_reasons"]
    sync = payload["sync"]
    assert isinstance(sync, dict)
    assert sync["freshness_status"] == "failed"
    assert sync["last_error"] == "boom"


@pytest.mark.django_db
def test_health_not_ready_when_sync_status_row_missing(rf) -> None:  # type: ignore[no-untyped-def]
    response = health(rf.get("/readyz"))

    assert response.status_code == 503
    payload = _payload(response)
    assert "sync_unknown" in payload["not_ready_reasons"]
    sync = payload["sync"]
    assert isinstance(sync, dict)
    assert sync["status"] == "unknown"
    assert sync["freshness_status"] == "unknown"


@pytest.mark.django_db
def test_health_not_ready_for_malformed_runtime_identity(
    rf,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    current_time = datetime(2026, 2, 12, 18, tzinfo=timezone.utc)
    monkeypatch.setenv("LAUNCHPLANE_RUNTIME_IDENTITY_JSON", "not-json")
    monkeypatch.setenv("LAUNCHPLANE_DEPLOYMENT_RECORD_ID", "deploy-fallback")
    monkeypatch.setattr("repairshopr_data.sync_health.now", lambda: current_time)
    SyncStatus.objects.create(
        id=1,
        status="success",
        mode="incremental",
        cycle_id="cycle-123",
        current_model="ticket",
        current_page=2,
        records_processed=30,
        cycle_started_at=current_time - timedelta(minutes=5),
        cycle_finished_at=current_time - timedelta(minutes=4),
        last_heartbeat=current_time - timedelta(minutes=4),
        last_error=None,
    )

    response = health(rf.get("/readyz"))

    assert response.status_code == 503
    payload = _payload(response)
    assert "malformed_runtime_identity" in payload["not_ready_reasons"]
    runtime_identity = payload["runtime_identity"]
    assert isinstance(runtime_identity, dict)
    assert runtime_identity["deployment_record_id"] == "deploy-fallback"
