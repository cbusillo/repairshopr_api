from __future__ import annotations

from datetime import datetime, timezone

import pytest

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


def test_base_from_list_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        Properties.from_list([])
