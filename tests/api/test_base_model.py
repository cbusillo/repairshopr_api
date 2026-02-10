from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

import pytest

from repairshopr_api.base.model import BaseModel
from repairshopr_api.client import Client
from repairshopr_api.type_defs import QueryParams
from repairshopr_api.models.invoice import Invoice
from repairshopr_api.models.ticket import Comment, Properties, Ticket


def test_from_dict_parses_datetime_strings() -> None:
    invoice = Invoice.from_dict(
        {
            "id": 10,
            "created_at": "2026-01-10T10:20:30Z",
            "updated_at": "2026-01-10T12:20:30+02:00",
        }
    )

    assert isinstance(invoice.created_at, datetime)
    assert invoice.created_at == datetime(2026, 1, 10, 10, 20, 30, tzinfo=timezone.utc)
    assert isinstance(invoice.updated_at, datetime)
    assert invoice.updated_at.utcoffset() is not None


def test_from_dict_keeps_malformed_datetime_string() -> None:
    invoice = Invoice.from_dict({"id": 22, "created_at": "not-a-datetime"})

    assert invoice.created_at == "not-a-datetime"


def test_from_dict_preserves_falsey_values() -> None:
    invoice = Invoice.from_dict(
        {
            "id": 23,
            "is_paid": False,
            "subtotal": 0,
            "note": "",
        }
    )

    assert invoice.is_paid is False
    assert invoice.subtotal == 0
    assert invoice.note == ""


def test_from_dict_maps_nested_models_and_cleans_keys() -> None:
    ticket = Ticket.from_dict(
        {
            "id": 3,
            "Customer Business Then Name": "Acme Repair",
            "comments": [
                {"id": 7, "body": "First comment"},
                {"id": 8, "body": "Second comment"},
            ],
            "properties": {
                "Tag #": "TAG-1",
                "drop off/location": "Front Desk",
                "-": "Courier",
            },
        }
    )

    assert ticket.customer_business_then_name == "Acme Repair"
    assert len(ticket.comments) == 2
    assert all(isinstance(comment, Comment) for comment in ticket.comments)

    assert isinstance(ticket.properties, Properties)
    assert ticket.properties.tag_num == "TAG-1"
    assert ticket.properties.drop_off_location == "Front Desk"
    assert ticket.properties.transport == "Courier"


def test_clean_key_variants() -> None:
    assert Ticket.clean_key("Tag #") == "tag_num"
    assert Ticket.clean_key("drop off/location") == "drop_off_location"
    assert Ticket.clean_key("-") == "transport"
    assert Ticket.clean_key("po_") == "po_2"


def test_get_field_names_requires_client() -> None:
    original_client = Ticket.rs_client
    Ticket.rs_client = None
    try:
        with pytest.raises(AttributeError, match="rs_client"):
            Ticket._get_field_names()
    finally:
        Ticket.rs_client = original_client


def test_get_field_names_and_properties_fields() -> None:
    original_client = Ticket.rs_client

    ticket_one = Ticket.from_dict(
        {
            "id": 1,
            "subject": "A",
            "properties": {
                "tag #": "X",
                "drop off/location": "Front",
            },
        }
    )
    ticket_two = Ticket.from_dict(
        {
            "id": 2,
            "subject": "B",
            "properties": {
                "call #": "42",
            },
        }
    )

    class StubClient(Client):
        def __init__(self) -> None:
            super().__init__(token="token", url_store_name="store")
            self._tickets = [ticket_one, ticket_two]

        def get_model(
            self,
            _model: type[BaseModel],
            updated_at: datetime | None = None,
            num_last_pages: int | None = None,
            params: QueryParams | None = None,
        ) -> Generator[Ticket, None, None]:
            _ = updated_at, num_last_pages, params
            for ticket in self._tickets:
                yield ticket

    Ticket.rs_client = StubClient()
    try:
        names = set(Ticket.get_fields())
        properties = set(Ticket.get_properties_fields())
    finally:
        Ticket.rs_client = original_client

    assert "subject" in names
    assert "id" in names
    assert "tag_num" in properties
    assert "call_num" in properties


def test_base_from_list_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        Properties.from_list([])
