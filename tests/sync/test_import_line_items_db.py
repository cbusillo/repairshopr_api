from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import pytest
import requests
from django.db import models
from repairshopr_data.management.commands import (
    import_from_repairshopr as command_module,
)
from repairshopr_data.models import (
    Customer,
    CustomerProperties,
    Invoice,
    InvoiceLineItem,
    SyncStatus,
    Ticket,
    TicketProperties,
)

from repairshopr_api.base.model import BaseModel
from repairshopr_api.config import settings
from repairshopr_api.type_defs import JsonObject, JsonValue

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

        rows = [row for row in self.collections.get(path, []) if self._matches(row, params)]
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
        pytest.param(None, "invoice_id", id="full-sync-per-invoice"),
        pytest.param(
            datetime.now(UTC) - timedelta(days=1),
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
    line_item_ids = [90_000 + position for position in range(1, per_page + per_page // 2 + 1)]
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
    cmd.handle_model(*cmd.model_mapping["Invoice"])

    assert served_line_item_pages(api, line_item_filter_key) == {1, 2}
    invoice = Invoice.objects.get(id=invoice_id)
    imported_ids = set(InvoiceLineItem.objects.filter(parent_invoice=invoice).values_list("id", flat=True))
    assert imported_ids == set(line_item_ids)
    assert InvoiceLineItem.objects.count() == len(line_items)


@pytest.mark.django_db
def test_sync_heartbeat_advances_during_multi_page_invoice_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    per_page = 2
    page_count = 3
    invoices: list[JsonObject] = [
        {"id": invoice_id, "number": f"INV-{invoice_id}"} for invoice_id in range(1, per_page * page_count + 1)
    ]
    api = FakeRepairShoprApi({"invoices": invoices}, per_page=per_page)
    api.install(monkeypatch)

    clock = [datetime(2026, 3, 1, tzinfo=UTC)]

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
            status_before_invoice_page[request.params["page"]] = SyncStatus.objects.get(id=1)

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


@pytest.mark.django_db
def test_partial_bulk_feed_does_not_hide_invoice_children(monkeypatch: pytest.MonkeyPatch) -> None:
    invoice_id = 42
    rows = [{"id": i, "invoice_id": invoice_id} for i in range(1, 5)]
    api = FakeRepairShoprApi({"invoices": [{"id": invoice_id}], "line_items": rows}, 2)
    original_respond = api.respond

    def respond(path: str, params: Mapping[str, object]) -> JsonObject:
        payload = original_respond(path, params)
        if path == "line_items" and "invoice_id_not_null" in params:
            # Real defect: a bulk feed has some rows for a parent, so the old
            # prefetch manufactured complete per-invoice cache metadata.
            return {
                "line_items": rows[:1],
                "meta": {"total_pages": 1, "total_entries": 1},
            }
        return payload

    monkeypatch.setattr(api, "respond", respond)
    api.install(monkeypatch)
    monkeypatch.setattr(settings.django, "last_updated_at", None)
    cmd = build_command(monkeypatch)
    cmd.client.prefetch_line_items()  # Even an explicitly populated partial cache is unsafe.
    cmd.handle_model(*cmd.model_mapping["Invoice"])
    assert set(InvoiceLineItem.objects.values_list("id", flat=True)) == {row["id"] for row in rows}


@pytest.mark.django_db
def test_sample_reads_fresh_ids_and_preserves_checkpoint_on_missing_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = datetime(2026, 9, 1, tzinfo=UTC)
    api = FakeRepairShoprApi({"invoices": [{"id": 42}], "line_items": [{"id": 1, "invoice_id": 42}]}, 100)
    reads = 0

    def change_child_ids(request: ServedRequest) -> None:
        nonlocal reads
        if request.collection == "line_items" and "invoice_id" in request.params:
            reads += 1
            if reads > 1:
                # Same count, different ID: a count-only or cached check passes.
                api.collections["line_items"] = [{"id": 2, "invoice_id": 42}]

    api.before_serving = change_child_ids
    api.install(monkeypatch)
    monkeypatch.setattr(settings.django, "last_updated_at", checkpoint)
    saved = []
    monkeypatch.setattr(settings, "save", lambda: saved.append(True))
    cmd = build_command(monkeypatch)
    cmd.model_mapping = {"Invoice": cmd.model_mapping["Invoice"]}
    with pytest.raises(command_module.CommandError):
        cmd.handle()
    assert settings.django.last_updated_at == checkpoint
    assert not saved
    assert SyncStatus.objects.get(id=1).status == "failed"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("parent_model", "properties_model", "field_name"),
    [(Customer, CustomerProperties, "title"), (Ticket, TicketProperties, "case")],
)
def test_embedded_properties_reuse_the_parent_row(
    parent_model: type[models.Model], properties_model: type[models.Model], field_name: str
) -> None:
    create = command_module.create_or_update_django_instance
    first = create(parent_model, {"id": 1, "properties": {field_name: "before"}})
    property_id = first.properties_id
    create(parent_model, {"id": 1, "properties": {field_name: "after"}})
    create(parent_model, {"id": 2, "properties": {field_name: "other parent"}})
    first.refresh_from_db()
    assert first.properties_id == property_id
    assert getattr(first.properties, field_name) == "after"
    assert properties_model.objects.count() == parent_model.objects.count()
    assert parent_model.objects.get(id=2).properties_id != property_id


@pytest.mark.django_db
def test_invoice_payment_summary_is_retained(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"id": 42, "amount_paid": 15.0, "balance_due": 3.5, "is_recurring": True}
    api = FakeRepairShoprApi({"invoices": [row]}, 100)
    api.install(monkeypatch)
    monkeypatch.setattr(settings.django, "last_updated_at", None)
    cmd = build_command(monkeypatch)
    cmd.handle_model(*cmd.model_mapping["Invoice"])
    invoice = Invoice.objects.get(id=row["id"])
    for name in ("amount_paid", "balance_due", "is_recurring"):
        assert getattr(invoice, name) == row[name]
