import json
from typing import Any

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from repairshopr_data.models import SyncStatus
from repairshopr_data.sync_health import build_sync_status_payload, isoformat_or_none


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
    def _isoformat(value: Any) -> str | None:
        return isoformat_or_none(value)

    def _build_payload(self, stale_threshold_seconds: int) -> dict[str, Any]:
        return build_sync_status_payload(
            stale_threshold_seconds,
            status_model=SyncStatus,
            current_time=now(),
        )

    def handle(self, *args, **options) -> None:
        _ = args
        stale_threshold_seconds = max(0, int(options["stale_threshold_seconds"]))
        fail_on_stale = bool(options["fail_on_stale"])

        payload = self._build_payload(stale_threshold_seconds)
        self.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))

        if fail_on_stale and payload.get("is_stale"):
            raise SystemExit(2)
