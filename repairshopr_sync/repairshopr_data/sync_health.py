from __future__ import annotations

import json
import os
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from django.db import DatabaseError
from django.utils.timezone import now

from repairshopr_data.models import SyncStatus


SERVICE_NAME = "repairshopr-sync"
PACKAGE_NAME = "repairshopr-api"
DEFAULT_STALE_THRESHOLD_SECONDS = 900


def isoformat_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_sync_status_payload(
    stale_threshold_seconds: int,
    *,
    status_model: Any = SyncStatus,
    current_time: datetime | None = None,
) -> dict[str, Any]:
    status_row = status_model.objects.filter(id=1).first()
    current_time = current_time or now()
    threshold = max(0, int(stale_threshold_seconds))

    if status_row is None:
        return {
            "status": "unknown",
            "mode": None,
            "cycle_id": None,
            "current_model": None,
            "current_page": None,
            "records_processed": 0,
            "cycle_started_at": None,
            "cycle_finished_at": None,
            "last_heartbeat": None,
            "last_error": None,
            "cycle_age_seconds": None,
            "heartbeat_age_seconds": None,
            "is_stale": False,
            "freshness_status": "unknown",
            "stale_threshold_seconds": threshold,
            "updated_at": None,
        }

    cycle_age_seconds: int | None = None
    if status_row.cycle_started_at is not None:
        cycle_end = (
            current_time
            if status_row.status == "running"
            else (status_row.cycle_finished_at or current_time)
        )
        cycle_age_seconds = max(
            0, int((cycle_end - status_row.cycle_started_at).total_seconds())
        )

    heartbeat_age_seconds: int | None = None
    if status_row.last_heartbeat is not None:
        heartbeat_age_seconds = max(
            0, int((current_time - status_row.last_heartbeat).total_seconds())
        )

    is_stale = bool(
        status_row.status == "running"
        and heartbeat_age_seconds is not None
        and 0 < threshold < heartbeat_age_seconds
    )

    freshness_status = "stale" if is_stale else "fresh"
    if status_row.status == "failed":
        freshness_status = "failed"

    return {
        "status": status_row.status,
        "mode": status_row.mode,
        "cycle_id": status_row.cycle_id,
        "current_model": status_row.current_model,
        "current_page": status_row.current_page,
        "records_processed": status_row.records_processed,
        "cycle_started_at": isoformat_or_none(status_row.cycle_started_at),
        "cycle_finished_at": isoformat_or_none(status_row.cycle_finished_at),
        "last_heartbeat": isoformat_or_none(status_row.last_heartbeat),
        "last_error": status_row.last_error,
        "cycle_age_seconds": cycle_age_seconds,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "is_stale": is_stale,
        "freshness_status": freshness_status,
        "stale_threshold_seconds": threshold,
        "updated_at": isoformat_or_none(status_row.updated_at),
    }


def package_version() -> str | None:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return None


def runtime_identity_from_environment() -> tuple[dict[str, Any], str | None]:
    identity_json = os.getenv("LAUNCHPLANE_RUNTIME_IDENTITY_JSON")
    fallback_identity = {
        "schema_version": 1,
        "product": os.getenv("LAUNCHPLANE_PRODUCT") or SERVICE_NAME,
        "context": os.getenv("LAUNCHPLANE_CONTEXT"),
        "instance": os.getenv("LAUNCHPLANE_INSTANCE"),
        "environment_kind": os.getenv("LAUNCHPLANE_ENVIRONMENT_KIND"),
        "deployment_record_id": os.getenv("LAUNCHPLANE_DEPLOYMENT_RECORD_ID"),
        "artifact_id": os.getenv("LAUNCHPLANE_ARTIFACT_ID"),
        "source_git_ref": os.getenv("LAUNCHPLANE_SOURCE_GIT_REF"),
    }

    if not identity_json:
        return fallback_identity, None

    try:
        parsed = json.loads(identity_json)
    except json.JSONDecodeError:
        return fallback_identity, "malformed_runtime_identity"

    if not isinstance(parsed, dict):
        return fallback_identity, "malformed_runtime_identity"

    merged = {**fallback_identity, **parsed}
    merged.setdefault("schema_version", 1)
    merged.setdefault("product", SERVICE_NAME)
    return merged, None


def source_git_ref(runtime_identity: dict[str, Any]) -> str | None:
    value = runtime_identity.get("source_git_ref") or os.getenv("GITHUB_SHA")
    if isinstance(value, str) and value:
        return value
    return None


def image_reference() -> str | None:
    for env_name in ("LAUNCHPLANE_IMAGE_REFERENCE", "IMAGE_REFERENCE"):
        value = os.getenv(env_name)
        if value:
            return value
    return None


def build_health_payload(stale_threshold_seconds: int) -> tuple[dict[str, Any], int]:
    runtime_identity, runtime_identity_error = runtime_identity_from_environment()
    db_error: str | None = None

    try:
        sync_payload = build_sync_status_payload(stale_threshold_seconds)
    except DatabaseError:
        sync_payload = {
            "status": "unavailable",
            "mode": None,
            "cycle_id": None,
            "cycle_finished_at": None,
            "last_heartbeat": None,
            "heartbeat_age_seconds": None,
            "cycle_age_seconds": None,
            "is_stale": True,
            "freshness_status": "unavailable",
            "stale_threshold_seconds": max(0, int(stale_threshold_seconds)),
            "last_error": "sync_status_unavailable",
        }
        db_error = "sync_status_unavailable"

    not_ready_reasons: list[str] = []
    if sync_payload["status"] in {"unknown", "failed", "unavailable"}:
        not_ready_reasons.append(f"sync_{sync_payload['status']}")
    if sync_payload.get("is_stale"):
        not_ready_reasons.append("sync_stale")
    if runtime_identity_error is not None:
        not_ready_reasons.append(runtime_identity_error)
    if db_error is not None:
        not_ready_reasons.append(db_error)

    ready = not not_ready_reasons
    status = "ok" if ready else "not_ready"
    payload = {
        "schema_version": 1,
        "service": SERVICE_NAME,
        "status": status,
        "version": package_version(),
        "source_git_ref": source_git_ref(runtime_identity),
        "image_reference": image_reference(),
        "runtime_identity": runtime_identity,
        "sync": sync_payload,
        "components": {
            "repairshopr": {"status": "ok" if db_error is None else "error"},
            "sync_freshness": {"status": "ok" if ready else "error"},
        },
    }

    if not_ready_reasons:
        payload["not_ready_reasons"] = not_ready_reasons

    return payload, 200 if ready else 503
