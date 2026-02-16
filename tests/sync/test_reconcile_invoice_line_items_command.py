from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from repairshopr_data.management.commands import (
    reconcile_invoice_line_items as command_module,
)


class _FilterResult:
    def __init__(self, *, ids: set[int] | None = None, count_value: int | None = None) -> None:
        self._ids = ids or set()
        self._count_value = count_value

    def values_list(self, field_name: str, *, flat: bool = False) -> list[int]:
        assert field_name == "id"
        assert flat is True
        return sorted(self._ids)

    def count(self) -> int:
        assert self._count_value is not None
        return self._count_value


def _build_invoice_line_item_manager(
    db_line_item_ids: set[int], *, include_values_list: bool = False
) -> object:
    def filter_fn(**kwargs: object) -> _FilterResult:
        id_in = kwargs.get("id__in")
        if isinstance(id_in, (list, set)):
            return _FilterResult(ids={item for item in id_in if item in db_line_item_ids})

        if kwargs.get("parent_invoice_id__isnull"):
            return _FilterResult(count_value=0)

        raise AssertionError(f"unexpected filter kwargs: {kwargs}")

    def count_fn() -> int:
        return len(db_line_item_ids)

    manager_fields: dict[str, object] = {
        "filter": filter_fn,
        "count": count_fn,
    }
    if include_values_list:

        def values_list_fn(field_name: str, *, flat: bool = False) -> list[int]:
            assert field_name == "id"
            assert flat is True
            return sorted(db_line_item_ids)

        manager_fields["values_list"] = values_list_fn

    return SimpleNamespace(**manager_fields)


def _build_invoice_manager() -> object:
    def filter_fn(**kwargs: object) -> _FilterResult:
        id_in = kwargs.get("id__in")
        assert isinstance(id_in, set)
        return _FilterResult(ids={invoice_id for invoice_id in id_in if invoice_id == 30})

    return SimpleNamespace(filter=filter_fn)


def test_reconcile_scan_reports_duplicates_and_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_line_item_ids = {1, 2, 4}
    fetched_pages: list[int] = []

    class FakeClient:
        @staticmethod
        def fetch_from_api(model_name: str, params: dict[str, object] | None = None):
            assert model_name == "line_item"
            page = (params or {}).get("page", 1)
            assert isinstance(page, int)
            fetched_pages.append(page)
            if page == 1:
                return [
                    {"id": 1, "invoice_id": 10},
                    {"id": 2, "invoice_id": 20},
                ], {"total_pages": 2, "total_entries": 4}
            if page == 2:
                return [
                    {"id": 2, "invoice_id": 20},
                    {"id": 3, "invoice_id": 30},
                ], {"total_pages": 2, "total_entries": 4}
            raise AssertionError(f"unexpected page: {page}")

    monkeypatch.setattr(command_module, "Client", lambda: FakeClient())
    monkeypatch.setattr(
        command_module,
        "InvoiceLineItem",
        SimpleNamespace(objects=_build_invoice_line_item_manager(db_line_item_ids)),
    )
    monkeypatch.setattr(
        command_module,
        "Invoice",
        SimpleNamespace(objects=_build_invoice_manager()),
    )

    command = command_module.Command()
    command.handle(
        page_start=1,
        page_end=0,
        progress_every=1,
        compute_db_not_in_api=False,
    )

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    parsed_lines = [json.loads(line) for line in lines]
    summary = json.loads(lines[-1])

    assert summary["event"] == "forensic_summary"
    assert summary["api_duplicate_rows"] == 1
    assert summary["api_unique_not_in_db"] == 1
    assert summary["missing_invoice_ids_count"] == 1
    assert summary["missing_invoice_ids_without_parent_invoice_row"] == 0
    assert not any(line["event"] == "repair_summary" for line in parsed_lines)
    assert fetched_pages == [1, 2]


def test_reconcile_compute_db_not_in_api_unique(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_line_item_ids = {1, 2, 9}

    class FakeClient:
        @staticmethod
        def fetch_from_api(model_name: str, params: dict[str, object] | None = None):
            assert model_name == "line_item"
            assert params is not None
            page = params.get("page", 1)
            if page == 1:
                return [{"id": 1, "invoice_id": 10}], {"total_pages": 2, "total_entries": 3}
            if page == 2:
                return [{"id": 3, "invoice_id": 30}], {"total_pages": 2, "total_entries": 3}
            raise AssertionError(f"unexpected page: {page}")

    monkeypatch.setattr(command_module, "Client", lambda: FakeClient())
    monkeypatch.setattr(
        command_module,
        "InvoiceLineItem",
        SimpleNamespace(
            objects=_build_invoice_line_item_manager(
                db_line_item_ids, include_values_list=True
            )
        ),
    )
    monkeypatch.setattr(
        command_module,
        "Invoice",
        SimpleNamespace(objects=_build_invoice_manager()),
    )

    command = command_module.Command()
    command.handle(
        page_start=1,
        page_end=0,
        progress_every=10,
        compute_db_not_in_api=True,
    )

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    summary = json.loads(lines[-1])

    assert summary["event"] == "forensic_summary"
    assert summary["db_not_in_api_unique"] == 2
