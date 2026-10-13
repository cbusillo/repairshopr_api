"""Recovery uses explicit parents, complete HTTP pages and real ORM writes."""

import json
from io import StringIO
from urllib.parse import urlparse

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError

from repairshopr_api.base.model import BaseModel
from repairshopr_api.config import settings
from repairshopr_data.management.commands import refresh_related
from repairshopr_data.models import Invoice, InvoiceLineItem, Ticket, TicketComment


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("REPAIRSHOPR_URL_STORE_NAME", "example-store")
    monkeypatch.setenv("REPAIRSHOPR_TOKEN", "test-token")
    monkeypatch.setattr(BaseModel, "rs_client", BaseModel.rs_client)
    state = {"fail_page": None, "wrong_parent": False}

    def request(_session, method, url, params=None, **_kwargs):
        assert method == "GET"
        page = params.get("page", 1)
        if state["fail_page"] == page:
            raise ValueError("page failed")
        ticket = urlparse(url).path.endswith("/comments")
        parent_key = "ticket_id" if ticket else "invoice_id"
        rows = [
            {
                "id": page,
                parent_key: 99 if state["wrong_parent"] else 42,
                "body": f"comment {page}",
                "name": f"line {page}",
            }
        ]
        response = requests.Response()
        response.status_code = 200
        response.json = lambda: {
            "comments" if ticket else "line_items": rows,
            "meta": {"total_pages": 2},
        }
        return response

    monkeypatch.setattr(requests.Session, "request", request)
    return state


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["invoice", "ticket"])
def test_refresh_dry_run_then_apply_is_complete_and_idempotent(api, kind):
    parent, child, relation = (
        (Invoice, InvoiceLineItem, "parent_invoice")
        if kind == "invoice"
        else (Ticket, TicketComment, "ticket")
    )
    parent.objects.create(id=42)
    child.objects.create(id=1, **{f"{relation}_id": 42})
    child.objects.create(id=3, **{f"{relation}_id": 42})  # Retain a local-only child.
    checkpoint = settings.django.last_updated_at
    output = StringIO()
    call_command("refresh_related", kind=kind, ids=[42], stdout=output)
    assert json.loads(output.getvalue())["missing_before"] == 1
    assert set(child.objects.values_list("id", flat=True)) == {1, 3}
    for _ in range(2):
        call_command(
            "refresh_related", kind=kind, ids=[42], apply=True, stdout=StringIO()
        )
    assert set(
        child.objects.filter(**{f"{relation}_id": 42}).values_list("id", flat=True)
    ) == {1, 2, 3}
    assert settings.django.last_updated_at == checkpoint


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["invoice", "ticket"])
def test_failed_or_misrouted_page_never_partially_writes(api, kind):
    parent, child = (
        (Invoice, InvoiceLineItem) if kind == "invoice" else (Ticket, TicketComment)
    )
    parent.objects.create(id=42)
    api["fail_page"] = 2
    with pytest.raises(ValueError, match="page failed"):
        call_command("refresh_related", kind=kind, ids=[42], apply=True)
    assert child.objects.count() == 0
    api.update(fail_page=None, wrong_parent=True)
    with pytest.raises(CommandError, match="different parent"):
        call_command("refresh_related", kind=kind, ids=[42], apply=True)
    assert child.objects.count() == 0


@pytest.mark.django_db
def test_import_error_rolls_back_parent_and_replay_recovers(api, monkeypatch):
    Invoice.objects.create(id=42)
    original_create = refresh_related.create_or_update_django_instance

    def create(model, row, extra):
        if row["id"] == 2:
            raise ValueError("write failed")
        return original_create(model, row, extra)

    monkeypatch.setattr(refresh_related, "create_or_update_django_instance", create)
    with pytest.raises(ValueError, match="write failed"):
        call_command("refresh_related", kind="invoice", ids=[42], apply=True)
    assert InvoiceLineItem.objects.count() == 0
    monkeypatch.setattr(
        refresh_related, "create_or_update_django_instance", original_create
    )
    call_command(
        "refresh_related", kind="invoice", ids=[42], apply=True, stdout=StringIO()
    )
    assert InvoiceLineItem.objects.count() == 2


@pytest.mark.django_db
def test_unknown_parent_is_rejected_before_api(api):
    with pytest.raises(CommandError, match="already exist"):
        call_command("refresh_related", kind="invoice", ids=[42], apply=True)
