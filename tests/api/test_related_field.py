from __future__ import annotations

from datetime import datetime, timezone

from repairshopr_api.models.estimate import Estimate
from repairshopr_api.models.invoice import Invoice


class FakeClient:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, int]] = {}
        self.fetch_calls: list[tuple[str, dict[str, int | None]]] = []
        self.fetch_by_id_calls: list[int] = []
        self.prefetch_calls = 0

    def fetch_from_api(
        self, model_name: str, params: dict[str, int | None] | None = None
    ) -> tuple[list[dict[str, object]], dict[str, int]]:
        normalized_params = dict(params or {})
        self.fetch_calls.append((model_name, normalized_params))

        if normalized_params == {"estimate_id": 42}:
            return [{"id": 1001}, {"id": 1002}], {"total_pages": 2}
        if normalized_params == {"estimate_id": 42, "page": 2}:
            return [{"id": 1003}], {"total_pages": 2}
        if normalized_params == {"invoice_id": 77}:
            return (
                [
                    {
                        "id": 2001,
                        "invoice_id": 77,
                        "updated_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
                    }
                ],
                {"total_pages": 1},
            )

        raise AssertionError(f"Unexpected params: {normalized_params}")

    def fetch_from_api_by_id(self, _model: type, instance_id: int) -> dict[str, int]:
        self.fetch_by_id_calls.append(instance_id)
        return {"id": instance_id}

    def prefetch_line_items(self) -> None:
        self.prefetch_calls += 1


def test_related_field_fetches_all_pages_for_parent_relation() -> None:
    fake_client = FakeClient()
    Estimate.set_client(fake_client)  # type: ignore[arg-type]

    estimate = Estimate(id=42)
    line_items = estimate.line_items

    assert [line_item["id"] for line_item in line_items] == [1001, 1002, 1003]
    assert fake_client.fetch_calls == [
        ("line_item", {"estimate_id": 42}),
        ("line_item", {"estimate_id": 42, "page": 2}),
    ]
    assert fake_client.fetch_by_id_calls == []
    assert set(fake_client._cache.keys()) == {
        "lineitem_1001",
        "lineitem_1002",
        "lineitem_1003",
    }


def test_related_field_prefetches_invoice_line_items_before_parent_lookup() -> None:
    fake_client = FakeClient()
    Invoice.set_client(fake_client)  # type: ignore[arg-type]

    invoice = Invoice(id=77)
    line_items = invoice.line_items

    assert [line_item["id"] for line_item in line_items] == [2001]
    assert line_items[0]["updated_at"] == "2026-02-01T00:00:00+00:00"
    assert fake_client.prefetch_calls == 1
    assert fake_client.fetch_calls == [("line_item", {"invoice_id": 77})]
    assert fake_client.fetch_by_id_calls == []
