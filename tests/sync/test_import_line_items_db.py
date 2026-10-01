"""End-to-end import tests against real Django models with only HTTP faked."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
import requests

from repairshopr_api.base.model import BaseModel
from repairshopr_api.config import settings
from repairshopr_api.type_defs import JsonObject, JsonValue
from repairshopr_data.management.commands import (
    import_from_repairshopr as command_module,
)
from repairshopr_data.models import Invoice, InvoiceLineItem, SyncStatus

API_PREFIX = "/api/v1/"
NON_FILTER_PARAMS = frozenset({"page", "sort", "since_updated_at"})
NOT_NULL_SUFFIX = "_not_null"


@dataclass
class FakeResponse:
    payload: JsonObject
    status_code: int = 200

    def json(self) -> JsonObject:
        return self.payload

    def raise_for_status(self) -> None:
        return None


@dataclass
class ServedRequest:
    collection: str
    params: dict[str, object]


class FakeRepairShoprApi:
    """Serves paginated RepairShopr list endpoints from in-memory rows."""

    def __init__(self, collections: dict[str, list[JsonObject]], per_page: int) -> None:
        self.collections = collections
        self.per_page = per_page
        self.served: list[ServedRequest] = []
        self.before_serving: Callable[[ServedRequest], None] | None = None

    @staticmethod
    def _matches(row: JsonObject, params: Mapping[str, object]) -> bool:
        for key, value in params.items():
            if key in NON_FILTER_PARAMS:
                continue
            if key.endswith(NOT_NULL_SUFFIX):
                if row.get(key.removesuffix(NOT_NULL_SUFFIX)) is None:
                    return False
            elif str(row.get(key)) != str(value):
                return False
        return True

    def respond(self, path: str, params: Mapping[str, object]) -> JsonObject:
        if path == "tickets/settings":
            return {}

        served = ServedRequest(collection=path, params=dict(params))
        if self.before_serving is not None:
            self.before_serving(served)
        self.served.append(served)

        rows = [
            row for row in self.collections.get(path, []) if self._matches(row, params)
        ]
        page_value = params.get("page", 1)
        page = page_value if isinstance(page_value, int) else int(str(page_value))
        total_pages = max(1, -(-len(rows) // self.per_page))
        start = (page - 1) * self.per_page
        page_rows: list[JsonValue] = [*rows[start : start + self.per_page]]
        return {
            path: page_rows,
            "meta": {
                "page": page,
                "per_page": self.per_page,
                "total_entries": len(rows),
                "total_pages": total_pages,
            },
        }

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_session_request(
            _session: requests.Session,
            method: str,
            url: str,
            params: Mapping[str, object] | None = None,
            **_kwargs: object,
        ) -> FakeResponse:
            assert method.upper() == "GET"
            path = urlparse(url).path.removeprefix(API_PREFIX)
            return FakeResponse(self.respond(path, params or {}))

        monkeypatch.setattr(requests.Session, "request", fake_session_request)


def build_command(monkeypatch: pytest.MonkeyPatch) -> command_module.Command:
    monkeypatch.setenv("REPAIRSHOPR_URL_STORE_NAME", "example-store")
    monkeypatch.setenv("REPAIRSHOPR_TOKEN", "test-token")
    monkeypatch.setattr(BaseModel, "rs_client", BaseModel.rs_client)
    return command_module.Command()


def served_line_item_pages(api: FakeRepairShoprApi, filter_key: str) -> set[object]:
    return {
        request.params.get("page", 1)
        for request in api.served
        if request.collection == "line_items" and filter_key in request.params
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("last_updated_at", "line_item_filter_key"),
    [
        pytest.param(None, "invoice_id_not_null", id="full-sync-prefetch"),
        pytest.param(
            datetime.now(timezone.utc) - timedelta(days=1),
            "invoice_id",
            id="incremental-per-invoice",
        ),
    ],
)
def test_invoice_line_items_spanning_two_pages_are_imported(
    monkeypatch: pytest.MonkeyPatch,
    last_updated_at: datetime | None,
    line_item_filter_key: str,
) -> None:
    per_page = 100
    invoice_id = 4242
    line_item_ids = [
        90_000 + position for position in range(1, per_page + per_page // 2 + 1)
    ]
    line_items: list[JsonObject] = [
        {
            "id": line_item_id,
            "invoice_id": invoice_id,
            "name": f"Part {position}",
            "price": 10.0,
            "quantity": 1.0,
            "position": position,
        }
        for position, line_item_id in enumerate(line_item_ids, start=1)
    ]
    api = FakeRepairShoprApi(
        {
            "invoices": [{"id": invoice_id, "number": "INV-1"}],
            "line_items": line_items,
        },
        per_page=per_page,
    )
    api.install(monkeypatch)
    monkeypatch.setattr(settings.django, "last_updated_at", last_updated_at)

    cmd = build_command(monkeypatch)
    cmd.handle_model(
        "repairshopr_data.models.invoice.Invoice", "repairshopr_api.models.Invoice"
    )

    assert served_line_item_pages(api, line_item_filter_key) == {1, 2}
    invoice = Invoice.objects.get(id=invoice_id)
    imported_ids = set(
        InvoiceLineItem.objects.filter(parent_invoice=invoice).values_list(
            "id", flat=True
        )
    )
    assert imported_ids == set(line_item_ids)
    assert InvoiceLineItem.objects.count() == len(line_items)


@pytest.mark.django_db
def test_sync_heartbeat_advances_during_multi_page_invoice_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    per_page = 2
    page_count = 3
    invoices: list[JsonObject] = [
        {"id": invoice_id, "number": f"INV-{invoice_id}"}
        for invoice_id in range(1, per_page * page_count + 1)
    ]
    api = FakeRepairShoprApi({"invoices": invoices}, per_page=per_page)
    api.install(monkeypatch)

    clock = [datetime(2026, 3, 1, tzinfo=timezone.utc)]

    def advancing_now() -> datetime:
        # Every heartbeat check sees a full time interval elapse, as in a slow import.
        clock[0] += timedelta(seconds=command_module.HEARTBEAT_SECONDS_INTERVAL)
        return clock[0]

    monkeypatch.setattr(command_module, "now", advancing_now)
    monkeypatch.setattr(settings.django, "last_updated_at", None)
    monkeypatch.setattr(settings, "save", lambda: None)

    status_before_invoice_page: dict[object, SyncStatus] = {}

    def snapshot_status(request: ServedRequest) -> None:
        if request.collection == "invoices":
            status_before_invoice_page[request.params["page"]] = SyncStatus.objects.get(
                id=1
            )

    api.before_serving = snapshot_status

    build_command(monkeypatch).handle()

    status = status_before_invoice_page[page_count]
    completed_pages = page_count - 1
    assert status.current_model == "invoice"
    assert status.current_page == completed_pages
    assert status.records_processed == completed_pages * per_page
    first_page_status = status_before_invoice_page[1]
    assert status.last_heartbeat is not None
    assert first_page_status.last_heartbeat is not None
    assert status.last_heartbeat > first_page_status.last_heartbeat
    assert SyncStatus.objects.get(id=1).status == "success"
