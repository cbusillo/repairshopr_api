from __future__ import annotations

import os

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from repairshopr_data.sync_health import (
    DEFAULT_STALE_THRESHOLD_SECONDS,
    build_health_payload,
)


def _readiness_threshold_seconds() -> int:
    value = os.getenv("SYNC_HEALTH_STALE_THRESHOLD_SECONDS")
    if value is None:
        value = os.getenv("SYNC_STALE_HEARTBEAT_SECONDS")
    if value is None:
        return DEFAULT_STALE_THRESHOLD_SECONDS
    try:
        return max(0, int(value))
    except ValueError:
        return DEFAULT_STALE_THRESHOLD_SECONDS


@require_GET
def health(request):  # type: ignore[no-untyped-def]
    _ = request
    payload, status_code = build_health_payload(_readiness_threshold_seconds())
    return JsonResponse(payload, status=status_code)
