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


def test_reconcile_scan_reports_duplicates_and_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_line_item_ids = {1, 2, 4}

    class InvoiceLineItemManager:
        @staticmethod
        def filter(**kwargs: object) -> _FilterResult:
            id_in = kwargs.get("id__in")
            if isinstance(id_in, (list, set)):
                return _FilterResult(ids={item for item in id_in if item in db_line_item_ids})

            if kwargs.get("parent_invoice_id__isnull") is True:
                return _FilterResult(count_value=0)

            raise AssertionError(f"unexpected filter kwargs: {kwargs}")

        @staticmethod
        def count() -> int:
            return len(db_line_item_ids)

    class InvoiceManager:
        @staticmethod
        def filter(**kwargs: object) -> _FilterResult:
            id_in = kwargs.get("id__in")
            assert isinstance(id_in, set)
            return _FilterResult(ids={invoice_id for invoice_id in id_in if invoice_id == 30})

    class FakeClient:
        def fetch_from_api(self, model_name: str, params: dict[str, object] | None = None):
            assert model_name == "line_item"
            page = (params or {}).get("page", 1)
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
        SimpleNamespace(objects=InvoiceLineItemManager()),
    )
    monkeypatch.setattr(
        command_module,
        "Invoice",
        SimpleNamespace(objects=InvoiceManager()),
    )

    command = command_module.Command()
    command.handle(
        apply=False,
        page_start=1,
        page_end=0,
        progress_every=1,
        max_repair_invoices=0,
        compute_db_not_in_api=False,
    )

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    summary = json.loads(lines[-1])

    assert summary["event"] == "forensic_summary"
    assert summary["api_duplicate_rows"] == 1
    assert summary["api_unique_not_in_db"] == 1
    assert summary["missing_invoice_ids_count"] == 1
    assert summary["missing_invoice_ids_without_parent_invoice_row"] == 0


def test_reconcile_apply_repairs_existing_missing_invoices(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_line_item_ids = {1, 2}

    class InvoiceLineItemManager:
        @staticmethod
        def filter(**kwargs: object) -> _FilterResult:
            id_in = kwargs.get("id__in")
            if isinstance(id_in, (list, set)):
                return _FilterResult(ids={item for item in id_in if item in db_line_item_ids})

            if kwargs.get("parent_invoice_id__isnull") is True:
                return _FilterResult(count_value=0)

            raise AssertionError(f"unexpected filter kwargs: {kwargs}")

        @staticmethod
        def count() -> int:
            return len(db_line_item_ids)

    class InvoiceManager:
        @staticmethod
        def filter(**kwargs: object) -> _FilterResult:
            id_in = kwargs.get("id__in")
            assert isinstance(id_in, set)
            return _FilterResult(ids={invoice_id for invoice_id in id_in if invoice_id == 30})

    class FakeClient:
        def fetch_from_api(self, model_name: str, params: dict[str, object] | None = None):
            assert model_name == "line_item"
            assert params is not None

            if "invoice_id" in params:
                invoice_id = params["invoice_id"]
                page = params.get("page", 1)
                if invoice_id == 30 and page == 1:
                    return [{"id": 3, "invoice_id": 30}], {"total_pages": 1}
                return [], {"total_pages": 1}

            page = params.get("page", 1)
            if page == 1:
                return [{"id": 1, "invoice_id": 10}], {"total_pages": 2, "total_entries": 3}
            if page == 2:
                return [{"id": 3, "invoice_id": 30}], {"total_pages": 2, "total_entries": 3}
            raise AssertionError(f"unexpected page: {page}")

    def fake_create_or_update(_model, api_instance, extra_fields=None):
        _ = extra_fields
        identifier = api_instance.get("id")
        assert isinstance(identifier, int)
        db_line_item_ids.add(identifier)
        return SimpleNamespace(id=identifier)

    monkeypatch.setattr(command_module, "Client", lambda: FakeClient())
    monkeypatch.setattr(
        command_module,
        "create_or_update_django_instance",
        fake_create_or_update,
    )
    monkeypatch.setattr(
        command_module,
        "InvoiceLineItem",
        SimpleNamespace(objects=InvoiceLineItemManager()),
    )
    monkeypatch.setattr(
        command_module,
        "Invoice",
        SimpleNamespace(objects=InvoiceManager()),
    )

    command = command_module.Command()
    command.handle(
        apply=True,
        page_start=1,
        page_end=0,
        progress_every=10,
        max_repair_invoices=0,
        compute_db_not_in_api=False,
    )

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    summary = json.loads(lines[-1])

    assert summary["event"] == "repair_summary"
    assert summary["invoice_repairs_attempted"] == 1
    assert summary["rows_upserted"] == 1
    assert summary["remaining_missing_from_scanned_set"] == 0
