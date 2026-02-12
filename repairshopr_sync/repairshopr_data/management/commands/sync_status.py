import json
from datetime import datetime
from typing import Any

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from repairshopr_data.models import SyncStatus


class Command(BaseCommand):
    help = "Emit RepairShopr sync status as single-line JSON"

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--stale-threshold-seconds",
            type=int,
            default=0,
            help="Mark running sync stale when last heartbeat is older than this threshold.",
        )
        parser.add_argument(
            "--fail-on-stale",
            action="store_true",
            help="Exit with status code 2 when the running sync is stale.",
        )

    @staticmethod
    def _isoformat(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def _build_payload(self, stale_threshold_seconds: int) -> dict[str, Any]:
        status_row = SyncStatus.objects.filter(id=1).first()
        current_time = now()
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
            and 0 < stale_threshold_seconds < heartbeat_age_seconds
        )

        return {
            "status": status_row.status,
            "mode": status_row.mode,
            "cycle_id": status_row.cycle_id,
            "current_model": status_row.current_model,
            "current_page": status_row.current_page,
            "records_processed": status_row.records_processed,
            "cycle_started_at": self._isoformat(status_row.cycle_started_at),
            "cycle_finished_at": self._isoformat(status_row.cycle_finished_at),
            "last_heartbeat": self._isoformat(status_row.last_heartbeat),
            "last_error": status_row.last_error,
            "cycle_age_seconds": cycle_age_seconds,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "is_stale": is_stale,
            "updated_at": self._isoformat(status_row.updated_at),
        }

    def handle(self, *args, **options) -> None:
        _ = args
        stale_threshold_seconds = max(0, int(options["stale_threshold_seconds"]))
        fail_on_stale = bool(options["fail_on_stale"])

        payload = self._build_payload(stale_threshold_seconds)
        self.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))

        if fail_on_stale and payload.get("is_stale"):
            raise SystemExit(2)
