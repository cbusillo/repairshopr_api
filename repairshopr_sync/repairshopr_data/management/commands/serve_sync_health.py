from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from django.core.management.base import BaseCommand

from repairshopr_data.sync_health import (
    DEFAULT_STALE_THRESHOLD_SECONDS,
    build_health_payload,
)


class HealthHandler(BaseHTTPRequestHandler):
    stale_threshold_seconds = DEFAULT_STALE_THRESHOLD_SECONDS

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] not in {"/health", "/readyz"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        payload, status_code = build_health_payload(self.stale_threshold_seconds)
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


class Command(BaseCommand):
    help = "Serve RepairShopr sync health JSON"

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument(
            "--stale-threshold-seconds",
            type=int,
            default=DEFAULT_STALE_THRESHOLD_SECONDS,
        )

    def handle(self, *args, **options) -> None:
        _ = args
        HealthHandler.stale_threshold_seconds = max(
            0,
            int(options["stale_threshold_seconds"]),
        )
        server = ThreadingHTTPServer((options["host"], options["port"]), HealthHandler)
        self.stdout.write(
            f"Serving RepairShopr sync health on {options['host']}:{options['port']}"
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()
