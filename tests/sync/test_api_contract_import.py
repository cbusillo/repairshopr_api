"""Current vendor API contracts exercised through HTTP and the Django importer."""

from collections.abc import Mapping
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytest
import requests

from repairshopr_api.base.model import BaseModel
from repairshopr_api.config import settings
from repairshopr_api.type_defs import JsonObject
from repairshopr_data.management.commands import import_from_repairshopr
from repairshopr_data.models import Estimate, SyncStatus, Ticket, TicketComment


@pytest.fixture
def command(monkeypatch: pytest.MonkeyPatch) -> import_from_repairshopr.Command:
    monkeypatch.setenv("REPAIRSHOPR_URL_STORE_NAME", "example-store")
    monkeypatch.setenv("REPAIRSHOPR_TOKEN", "test-token")
    monkeypatch.setattr(BaseModel, "rs_client", BaseModel.rs_client)
    monkeypatch.setattr(
        settings.django,
        "last_updated_at",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(settings, "save", lambda: None)
    return import_from_repairshopr.Command()


def response(payload: JsonObject) -> requests.Response:
    result = requests.Response()
    result.status_code = 200
    result.json = lambda: payload
    return result


@pytest.mark.django_db
def test_estimate_incremental_import_reads_every_filtered_page(
    monkeypatch: pytest.MonkeyPatch, command: import_from_repairshopr.Command
) -> None:
    requested_pages: list[int] = []

    def request(
        _session: requests.Session,
        method: str,
        url: str,
        params: Mapping[str, object] | None = None,
        **_kwargs: object,
    ) -> requests.Response:
        assert method.upper() == "GET"
        params = params or {}
        if urlparse(url).path.endswith("/estimates"):
            assert params.get("updated_after") == "2026-09-01T00:00:00.000000Z"
            assert "since_updated_at" not in params
            page = params["page"]
            assert isinstance(page, int)
            requested_pages.append(page)
            return response({"estimates": [{"id": page}], "meta": {"total_pages": 4}})
        assert urlparse(url).path.endswith("/line_items")
        return response({"line_items": [], "meta": {"total_pages": 1}})

    monkeypatch.setattr(requests.Session, "request", request)
    window, params = command.model_mapping["Estimate"]
    command.handle_model(
        "repairshopr_data.models.estimate.Estimate",
        "repairshopr_api.models.Estimate",
        window,
        params,
    )

    assert requested_pages == [1, 2, 3, 4]
    assert set(Estimate.objects.values_list("id", flat=True)) == {1, 2, 3, 4}


@pytest.mark.django_db
@pytest.mark.parametrize("fail_second_page", [False, True])
def test_ticket_import_fetches_full_comment_history_before_replacing_relations(
    monkeypatch: pytest.MonkeyPatch,
    command: import_from_repairshopr.Command,
    fail_second_page: bool,
) -> None:
    ticket = Ticket.objects.create(id=101)
    TicketComment.objects.create(id=202, ticket=ticket, body="Previously synced")
    requested_pages: list[int] = []
    checkpoint = settings.django.last_updated_at

    def request(
        _session: requests.Session,
        method: str,
        url: str,
        params: Mapping[str, object] | None = None,
        **_kwargs: object,
    ) -> requests.Response:
        assert method.upper() == "GET"
        params = params or {}
        path = urlparse(url).path
        if path.endswith("/tickets/settings"):
            return response({})
        if path.endswith("/line_items"):
            return response({"line_items": [], "meta": {"total_entries": 0}})
        if path.endswith("/tickets"):
            return response(
                {
                    "tickets": [{"id": 101, "comments": [{"id": 201}]}],
                    "meta": {"total_pages": 1},
                }
            )
        assert path.endswith("/tickets/101/comments")
        assert "since_updated_at" not in params
        assert "updated_after" not in params
        page = params["page"]
        assert isinstance(page, int)
        requested_pages.append(page)
        if fail_second_page and page == 2:
            raise ValueError("Comment page unavailable")
        return response(
            {
                "comments": [{"id": 200 + page, "body": f"Comment {page}"}],
                "meta": {"total_pages": 3},
            }
        )

    monkeypatch.setattr(requests.Session, "request", request)
    command.model_mapping = {"Ticket": command.model_mapping["Ticket"]}
    if fail_second_page:
        with pytest.raises(ValueError, match="Comment page unavailable"):
            command.handle()
        assert requested_pages == [1, 2]
        assert settings.django.last_updated_at == checkpoint
        assert SyncStatus.objects.get(id=1).status == "failed"
        assert list(ticket.comments.values_list("id", "body")) == [
            (202, "Previously synced")
        ]
    else:
        command.handle_model(
            "repairshopr_data.models.ticket.Ticket", "repairshopr_api.models.Ticket"
        )
        assert requested_pages == [1, 2, 3]
        assert set(ticket.comments.values_list("id", "body")) == {
            (201, "Comment 1"),
            (202, "Comment 2"),
            (203, "Comment 3"),
        }
