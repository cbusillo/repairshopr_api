from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import Mock

import pytest
import requests
from tenacity import stop_after_attempt, wait_none

from repairshopr_api.base.model import BaseModel
from repairshopr_api.client import Client, _preview_response_body, _request_error_context
from repairshopr_api.type_defs import JsonObject, JsonValue, is_json_object


@dataclass
class DummyModel(BaseModel):
    id: int

    @classmethod
    def from_dict(cls, data: dict[str, JsonValue]) -> "DummyModel":
        raw_id = data.get("id")
        return cls(id=raw_id if isinstance(raw_id, int) else 0)

    @classmethod
    def from_list(cls, data: list[JsonValue]) -> "DummyModel":
        raw_id = data[0] if data else 0
        return cls(id=raw_id if isinstance(raw_id, int) else 0)


def _make_client() -> Client:
    return Client(token="token", url_store_name="store")


def test_get_model_paginates_and_formats_since_updated_at() -> None:
    client = _make_client()
    calls: list[dict] = []

    def fake_fetch(model_name: str, params: dict | None = None):
        assert model_name == "dummy_model"
        params = dict(params or {})
        calls.append(params)
        page = params["page"]
        return [{"id": page}], {"total_pages": 3}

    client.fetch_from_api = fake_fetch  # type: ignore[method-assign]

    updated_at = datetime(2026, 2, 8, 10, 11, 12, 123456, tzinfo=timezone.utc)
    records = list(
        client.get_model(DummyModel, updated_at=updated_at, params={"status": "open"})
    )

    assert [record.id for record in records] == [1, 2, 3]
    assert calls[0]["since_updated_at"] == "2026-02-08T10:11:12.123456Z"


def test_get_model_num_last_pages_requests_last_window() -> None:
    client = _make_client()
    requested_pages: list[int] = []

    def fake_fetch(_model_name: str, params: dict | None = None):
        page = (params or {})["page"]
        requested_pages.append(page)
        return [{"id": page}], {"total_pages": 5}

    client.fetch_from_api = fake_fetch  # type: ignore[method-assign]

    records = list(client.get_model(DummyModel, num_last_pages=2))

    assert [record.id for record in records] == [1, 4, 5]
    assert requested_pages == [1, 4, 5]


def test_request_retries_429_and_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client()
    client._wait_for_rate_limit = lambda: None  # type: ignore[method-assign]
    client.time_api_call = lambda *args, **kwargs: nullcontext()  # type: ignore[method-assign]

    attempts = {"count": 0}

    def fake_request(_self: requests.Session, method: str, url: str, *_args, **_kwargs):
        assert method == "GET"
        assert url.endswith("/tickets")
        attempts["count"] += 1
        status_code = (
            HTTPStatus.OK if attempts["count"] >= 3 else HTTPStatus.TOO_MANY_REQUESTS
        )
        return SimpleNamespace(status_code=status_code, text="")

    monkeypatch.setattr(requests.Session, "request", fake_request)

    client.request.retry.stop = stop_after_attempt(3)  # type: ignore[attr-defined]
    client.request.retry.wait = wait_none()  # type: ignore[attr-defined]
    client.request.retry.sleep = lambda _seconds: None  # type: ignore[attr-defined]

    response = client.request("GET", f"{client.base_url}/tickets")

    assert response.status_code == HTTPStatus.OK
    assert attempts["count"] == 3


def test_request_raises_for_unexpected_status() -> None:
    client = _make_client()
    client._wait_for_rate_limit = lambda: None  # type: ignore[method-assign]
    client.time_api_call = lambda *args, **kwargs: nullcontext()  # type: ignore[method-assign]

    original_request = requests.Session.request
    requests.Session.request = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        text="boom",
    )
    try:
        with pytest.raises(requests.RequestException, match="unexpected status code"):
            Client.request.__wrapped__(client, "GET", f"{client.base_url}/tickets")
    finally:
        requests.Session.request = original_request  # type: ignore[method-assign]


def test_prefetch_line_items_skips_when_recent_updated_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client()
    client.updated_at = datetime.now() - timedelta(hours=2)

    called = {"value": False}

    def fake_get_model(*_args: object, **_kwargs: object) -> Iterator[object]:
        called["value"] = True
        return iter([])

    client.get_model = fake_get_model  # type: ignore[method-assign]
    client.prefetch_line_items()

    assert called["value"] is False
    assert client._has_line_item_in_cache is False


def test_prefetch_line_items_builds_cache_for_old_updated_at() -> None:
    client = _make_client()
    client.updated_at = datetime.now(tz=timezone.utc) - timedelta(days=370)

    line_items = [
        SimpleNamespace(
            id=1,
            invoice_id=100,
            name="A",
            updated_at=datetime(2026, 2, 1, 1, 2, tzinfo=timezone.utc),
            _private="x",
        ),
        SimpleNamespace(
            id=2,
            invoice_id=100,
            name="B",
            updated_at=datetime(2026, 2, 1, 1, 3, tzinfo=timezone.utc),
            _private="y",
        ),
    ]

    client.get_model = lambda *_args, **_kwargs: iter(line_items)  # type: ignore[method-assign]
    client.prefetch_line_items()

    assert client._has_line_item_in_cache is True
    cached_entries = [
        value for key, value in client._cache.items() if key.startswith("line_item_list_")
    ]
    assert cached_entries
    first_page_rows, _meta = cached_entries[0]
    assert first_page_rows
    assert is_json_object(first_page_rows[0])
    assert first_page_rows[0]["updated_at"] == "2026-02-01T01:02:00+00:00"


def test_prefetch_line_items_aware_vs_naive_regression() -> None:
    client = _make_client()
    client.updated_at = datetime.now(tz=timezone.utc) - timedelta(days=800)
    client.get_model = lambda *_args, **_kwargs: iter([])  # type: ignore[method-assign]

    client.prefetch_line_items()

    assert client._has_line_item_in_cache is True


def test_prefetch_line_items_emits_progress_stages() -> None:
    client = _make_client()
    client.updated_at = datetime.now(tz=timezone.utc) - timedelta(days=800)
    line_items = [
        SimpleNamespace(id=1, invoice_id=100, name="A"),
        SimpleNamespace(id=2, invoice_id=200, name="B"),
    ]
    client.get_model = lambda *_args, **_kwargs: iter(line_items)  # type: ignore[method-assign]

    progress_stages: list[str | None] = []

    def progress_callback(
        _model_name: str,
        _page: int,
        _processed_rows: int,
        _processed_on_page: int,
        meta_data: JsonObject | None,
    ) -> None:
        progress_stages.append(
            meta_data.get("stage") if isinstance(meta_data, dict) else None
        )

    client.set_progress_callback(progress_callback)
    client.prefetch_line_items()

    assert "normalize_done" in progress_stages
    assert "cache" in progress_stages


def test_clear_cache_resets_memory_cache() -> None:
    client = _make_client()
    client._cache["k"] = {"value": "v"}
    client._has_line_item_in_cache = True

    client.clear_cache()

    assert client._cache == {}
    assert client._has_line_item_in_cache is False


def test_client_cache_and_rate_state_are_instance_scoped() -> None:
    first_client = _make_client()
    second_client = _make_client()

    assert first_client._cache is not second_client._cache
    assert first_client._request_timestamps is not second_client._request_timestamps


def test_wait_for_rate_limit_sleeps_when_limit_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client()
    client.REQUEST_LIMIT = 1
    client._request_timestamps.clear()

    now = datetime(2026, 2, 1, 12)
    client._request_timestamps.extend(
        [now - timedelta(seconds=10), now - timedelta(seconds=5)]
    )

    monkeypatch.setattr("repairshopr_api.client.datetime", Mock(now=lambda: now))
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "repairshopr_api.client.sleep", lambda seconds: sleep_calls.append(seconds)
    )

    client._wait_for_rate_limit()

    assert sleep_calls and sleep_calls[0] > 0
    assert client.api_sleep_time > 0
    assert len(client._request_timestamps) >= 1


def test_display_api_call_stats_runs_without_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _make_client()
    client.api_call_duration["tickets_bulk"] = [0.1, 0.2]
    client.api_call_counter["tickets_bulk"] = 2

    caplog.set_level("INFO")
    client.display_api_call_stats()

    assert "API Stats:" in caplog.text


def test_time_api_call_tracks_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client()
    monkeypatch.setattr(
        "repairshopr_api.client.logger.isEnabledFor", lambda _level: True
    )
    monkeypatch.setattr(client, "display_api_call_stats", lambda: None)

    with client.time_api_call(f"{client.base_url}/tickets"):
        pass

    assert client.api_call_counter["tickets_bulk"] == 1
    assert len(client.api_call_duration["tickets_bulk"]) == 1


def test_request_raises_permission_error_for_unauthorized() -> None:
    client = _make_client()
    client._wait_for_rate_limit = lambda: None  # type: ignore[method-assign]
    client.time_api_call = lambda *args, **kwargs: nullcontext()  # type: ignore[method-assign]

    original_request = requests.Session.request
    requests.Session.request = lambda *_args, **_kwargs: SimpleNamespace(status_code=HTTPStatus.UNAUTHORIZED, text="bad")  # type: ignore[method-assign]
    try:
        with pytest.raises(PermissionError, match="Authorization failed"):
            Client.request.__wrapped__(client, "GET", f"{client.base_url}/tickets")
    finally:
        requests.Session.request = original_request  # type: ignore[method-assign]


def test_request_raises_value_error_for_not_found() -> None:
    client = _make_client()
    client._wait_for_rate_limit = lambda: None  # type: ignore[method-assign]
    client.time_api_call = lambda *args, **kwargs: nullcontext()  # type: ignore[method-assign]

    original_request = requests.Session.request
    requests.Session.request = lambda *_args, **_kwargs: SimpleNamespace(status_code=HTTPStatus.NOT_FOUND, text="missing")  # type: ignore[method-assign]
    try:
        with pytest.raises(ValueError, match="Received 404"):
            Client.request.__wrapped__(client, "GET", f"{client.base_url}/tickets")
    finally:
        requests.Session.request = original_request  # type: ignore[method-assign]


def test_fetch_ticket_settings_validates_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client()

    class FakeResponse:
        def __init__(self, payload: object) -> None:
            self._payload = payload

        @staticmethod
        def raise_for_status() -> None:
            return None

        def json(self) -> object:
            return self._payload

    monkeypatch.setattr(
        "repairshopr_api.client.requests.get",
        lambda *_args, **_kwargs: FakeResponse({"a": 1}),
    )
    assert client.fetch_ticket_settings() == {"a": 1}

    monkeypatch.setattr(
        "repairshopr_api.client.requests.get",
        lambda *_args, **_kwargs: FakeResponse([1, 2]),
    )
    with pytest.raises(
        ValueError, match="Unexpected RepairShopr ticket settings payload"
    ):
        client.fetch_ticket_settings()


def test_fetch_from_api_caches_result() -> None:
    client = _make_client()

    response_payload = {"dummy_models": [{"id": 1}], "meta": {"total_pages": 1}}
    client.get = lambda *_args, **_kwargs: SimpleNamespace(json=lambda: response_payload)  # type: ignore[method-assign]

    first = client.fetch_from_api("dummy_model", params={"page": 1})
    second = client.fetch_from_api("dummy_model", params={"page": 1})

    assert first == second
    assert first[0] == [{"id": 1}]


def test_fetch_from_api_rejects_invalid_collection_payload() -> None:
    client = _make_client()
    client.get = lambda *_args, **_kwargs: SimpleNamespace(json=lambda: {"unexpected": []})  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Missing or invalid 'dummy_models' list"):
        client.fetch_from_api("dummy_model")


def test_fetch_from_api_rejects_invalid_meta_payload() -> None:
    client = _make_client()
    client.get = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        json=lambda: {"dummy_models": [], "meta": "bad-meta"}
    )

    with pytest.raises(ValueError, match="Invalid 'meta' payload type"):
        client.fetch_from_api("dummy_model")


def test_fetch_from_api_rejects_non_dict_payload() -> None:
    client = _make_client()
    client.get = lambda *_args, **_kwargs: SimpleNamespace(json=lambda: [1, 2, 3])  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Unexpected payload type"):
        client.fetch_from_api("dummy_model")


def test_fetch_from_api_by_id_uses_cache() -> None:
    client = _make_client()
    response_payload = {"dummymodel": {"id": 3}}
    calls = {"count": 0}

    def fake_get(*_args: object, **_kwargs: object) -> SimpleNamespace:
        calls["count"] += 1
        return SimpleNamespace(json=lambda: response_payload)

    client.get = fake_get  # type: ignore[method-assign]

    data_one = client.fetch_from_api_by_id(DummyModel, 3)
    data_two = client.fetch_from_api_by_id(DummyModel, 3)

    assert data_one == {"id": 3}
    assert data_two == {"id": 3}
    assert calls["count"] == 1


def test_fetch_from_api_by_id_accepts_snake_case_model_key() -> None:
    client = _make_client()
    client.get = lambda *_args, **_kwargs: SimpleNamespace(json=lambda: {"dummy_model": {"id": 8}})  # type: ignore[method-assign]

    data = client.fetch_from_api_by_id(DummyModel, 8)

    assert data == {"id": 8}


def test_fetch_from_api_by_id_rejects_unknown_payload_shape() -> None:
    client = _make_client()
    client.get = lambda *_args, **_kwargs: SimpleNamespace(json=lambda: {"wrong": {"id": 9}})  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Could not locate model payload"):
        client.fetch_from_api_by_id(DummyModel, 9)


def test_fetch_from_api_by_id_rejects_non_dict_payload() -> None:
    client = _make_client()
    client.get = lambda *_args, **_kwargs: SimpleNamespace(json=lambda: [1, 2])  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Unexpected payload type"):
        client.fetch_from_api_by_id(DummyModel, 9)


def test_get_model_by_id_builds_model_instance() -> None:
    client = _make_client()
    client.fetch_from_api_by_id = lambda *_args, **_kwargs: {"id": 44}  # type: ignore[method-assign]

    record = client.get_model_by_id(DummyModel, 44)

    assert isinstance(record, DummyModel)
    assert record.id == 44


def test_preview_response_body_and_error_context_helpers() -> None:
    long_text = "x" * 400
    preview = _preview_response_body(long_text)
    assert preview.endswith("...")
    assert len(preview) == 303

    response = requests.Response()
    response.status_code = 500
    response._content = b"error text"
    context = _request_error_context("https://store.repairshopr.com/api/v1/invoices", response)
    assert "url=/api/v1/invoices" in context
    assert "content_type=unknown" in context


def test_client_init_raises_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPAIRSHOPR_URL_STORE_NAME", "")
    monkeypatch.setenv("REPAIRSHOPR_TOKEN", "")
    monkeypatch.setattr("repairshopr_api.client.settings.repairshopr.url_store_name", "")
    monkeypatch.setattr("repairshopr_api.client.settings.repairshopr.token", "")

    with pytest.raises(ValueError, match="must be provided"):
        Client()


def test_prefetch_line_items_returns_when_already_cached() -> None:
    client = _make_client()
    client._has_line_item_in_cache = True

    called = {"value": False}

    def fake_get_model(*_args: object, **_kwargs: object) -> Iterator[object]:
        called["value"] = True
        return iter([])

    client.get_model = fake_get_model  # type: ignore[method-assign]
    client.prefetch_line_items()

    assert called["value"] is False


def test_fetch_from_api_rejects_invalid_row_item_payload() -> None:
    client = _make_client()
    client.get = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        json=lambda: {"dummy_models": ["bad"], "meta": {"total_pages": 1}}
    )

    with pytest.raises(ValueError, match="Invalid item payload type"):
        client.fetch_from_api("dummy_model")


def test_fetch_from_api_by_id_rejects_bad_cached_and_empty_payloads() -> None:
    client = _make_client()
    client._cache["dummymodel_1"] = ([], {"total_pages": 1})

    with pytest.raises(TypeError, match="Unexpected cache payload type"):
        client.fetch_from_api_by_id(DummyModel, 1)

    client = _make_client()
    client.get = lambda *_args, **_kwargs: SimpleNamespace(json=lambda: {"dummymodel": {}})  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="Could not find DummyModel"):
        client.fetch_from_api_by_id(DummyModel, 2)


def test_get_model_handles_row_arrays_and_progress_callback() -> None:
    client = _make_client()
    progress_calls: list[tuple[str, int, int, int, JsonObject | None]] = []
    client.set_progress_callback(
        lambda model_name, page, processed_rows, processed_on_page, meta: progress_calls.append(
            (model_name, page, processed_rows, processed_on_page, meta)
        )
    )

    class ListModel(BaseModel):
        @classmethod
        def from_dict(cls, data: dict[str, JsonValue]) -> "ListModel":
            return cls(id=int(data["id"]))

        @classmethod
        def from_list(cls, data: list[JsonValue]) -> list[BaseModel]:
            return [cls(id=int(data[0])), cls(id=int(data[0]) + 100)]

    client.fetch_from_api = lambda *_args, **_kwargs: (  # type: ignore[method-assign]
        [[1]],
        {"total_pages": 1},
    )

    results = list(client.get_model(ListModel))

    assert [item.id for item in results] == [1, 101]
    assert progress_calls == [("list_model", 1, 2, 2, {"total_pages": 1})]
