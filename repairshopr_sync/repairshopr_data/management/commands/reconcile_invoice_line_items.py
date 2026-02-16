import json
from typing import Any

from django.core.management.base import BaseCommand

from repairshopr_api.client import Client
from repairshopr_data.management.commands.import_from_repairshopr import (
    _normalize_identifier,
)
from repairshopr_data.models import Invoice, InvoiceLineItem


class Command(BaseCommand):
    help = (
        "Forensically scan RepairShopr invoice line-item feed and report drift metrics."
    )

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--page-start",
            type=int,
            default=1,
            help="Start page for forensic scan (default: 1).",
        )
        parser.add_argument(
            "--page-end",
            type=int,
            default=0,
            help="Last page for forensic scan; 0 means scan through API total_pages.",
        )
        parser.add_argument(
            "--progress-every",
            type=int,
            default=250,
            help="Emit progress JSON every N pages (default: 250).",
        )
        parser.add_argument(
            "--compute-db-not-in-api",
            action="store_true",
            help="Compute db_not_in_api_unique (requires full DB ID set in memory).",
        )

    @staticmethod
    def _normalize_total_entries(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    @staticmethod
    def _emit(payload: dict[str, Any]) -> None:
        print(json.dumps(payload, sort_keys=True), flush=True)

    def _scan(
        self,
        client: Client,
        *,
        page_start: int,
        page_end: int,
        progress_every: int,
    ) -> dict[str, Any]:
        first_page_rows, meta = client.fetch_from_api(
            "line_item", params={"invoice_id_not_null": True, "page": 1}
        )
        total_pages = (
            self._normalize_total_entries(meta.get("total_pages"))
            if isinstance(meta, dict)
            else None
        )
        api_reported_total = (
            self._normalize_total_entries(meta.get("total_entries"))
            if isinstance(meta, dict)
            else None
        )

        if total_pages is None:
            total_pages = page_start
        final_page = page_end if page_end > 0 else total_pages
        final_page = min(final_page, total_pages)

        seen_api_ids: set[int] = set()
        missing_line_item_ids: set[int] = set()
        missing_invoice_ids: set[int] = set()
        missing_examples: list[int] = []
        duplicate_rows = 0
        api_rows_scanned = 0
        non_int_id_rows = 0
        non_int_invoice_id_rows = 0

        for page in range(page_start, final_page + 1):
            if page == 1 and page_start == 1:
                # Reuse the metadata probe payload instead of refetching page 1.
                response_data = first_page_rows
            else:
                response_data, _meta = client.fetch_from_api(
                    "line_item", params={"invoice_id_not_null": True, "page": page}
                )
            page_ids: list[int] = []
            page_line_item_invoice_map: dict[int, int] = {}

            for row in response_data:
                if not isinstance(row, dict):
                    continue

                line_item_id = _normalize_identifier(row.get("id"))
                if line_item_id is None:
                    non_int_id_rows += 1
                    continue

                api_rows_scanned += 1
                if line_item_id in seen_api_ids:
                    duplicate_rows += 1
                else:
                    seen_api_ids.add(line_item_id)

                page_ids.append(line_item_id)
                invoice_id = _normalize_identifier(row.get("invoice_id"))
                if invoice_id is None:
                    non_int_invoice_id_rows += 1
                    continue
                page_line_item_invoice_map[line_item_id] = invoice_id

            if page_ids:
                existing_ids = set(
                    InvoiceLineItem.objects.filter(id__in=page_ids).values_list(
                        "id", flat=True
                    )
                )
                for line_item_id in page_ids:
                    if line_item_id in existing_ids:
                        continue
                    if line_item_id in missing_line_item_ids:
                        continue
                    missing_line_item_ids.add(line_item_id)
                    if len(missing_examples) < 25:
                        missing_examples.append(line_item_id)
                    invoice_id = page_line_item_invoice_map.get(line_item_id)
                    if isinstance(invoice_id, int):
                        missing_invoice_ids.add(invoice_id)

            if page == final_page or (
                progress_every > 0 and page % progress_every == 0
            ):
                self._emit(
                    {
                        "event": "scan_progress",
                        "page": page,
                        "final_page": final_page,
                        "api_rows_scanned": api_rows_scanned,
                        "api_unique_ids": len(seen_api_ids),
                        "duplicate_rows": duplicate_rows,
                        "missing_unique_ids_so_far": len(missing_line_item_ids),
                    }
                )

        return {
            "page_start": page_start,
            "page_end": final_page,
            "api_reported_total_entries": api_reported_total,
            "api_rows_scanned": api_rows_scanned,
            "api_unique_ids": len(seen_api_ids),
            "api_duplicate_rows": duplicate_rows,
            "api_non_int_id_rows": non_int_id_rows,
            "api_non_int_invoice_id_rows": non_int_invoice_id_rows,
            "missing_line_item_ids": missing_line_item_ids,
            "missing_invoice_ids": missing_invoice_ids,
            "missing_examples": missing_examples,
            "seen_api_ids": seen_api_ids,
        }

    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        _ = args
        page_start = max(1, int(options["page_start"]))
        page_end = max(0, int(options["page_end"]))
        progress_every = max(0, int(options["progress_every"]))
        compute_db_not_in_api = bool(options["compute_db_not_in_api"])

        client = Client()
        scan = self._scan(
            client,
            page_start=page_start,
            page_end=page_end,
            progress_every=progress_every,
        )

        missing_invoice_ids: set[int] = scan["missing_invoice_ids"]
        existing_missing_invoices = set(
            Invoice.objects.filter(id__in=missing_invoice_ids).values_list("id", flat=True)
        )
        missing_parent_invoices = missing_invoice_ids - existing_missing_invoices

        db_total_rows = InvoiceLineItem.objects.count()
        gap_vs_reported_total: int | None = None
        if isinstance(scan["api_reported_total_entries"], int):
            gap_vs_reported_total = scan["api_reported_total_entries"] - db_total_rows

        summary: dict[str, Any] = {
            "event": "forensic_summary",
            "page_start": scan["page_start"],
            "page_end": scan["page_end"],
            "api_reported_total_entries": scan["api_reported_total_entries"],
            "api_rows_scanned": scan["api_rows_scanned"],
            "api_unique_ids": scan["api_unique_ids"],
            "api_duplicate_rows": scan["api_duplicate_rows"],
            "db_total_rows": db_total_rows,
            "gap_vs_api_reported_total": gap_vs_reported_total,
            "api_unique_not_in_db": len(scan["missing_line_item_ids"]),
            "missing_examples": scan["missing_examples"],
            "missing_invoice_ids_count": len(missing_invoice_ids),
            "missing_invoice_ids_without_parent_invoice_row": len(
                missing_parent_invoices
            ),
            "db_null_parent_invoice_id_count": InvoiceLineItem.objects.filter(
                parent_invoice_id__isnull=True
            ).count(),
        }

        if compute_db_not_in_api:
            db_ids = set(InvoiceLineItem.objects.values_list("id", flat=True))
            summary["db_not_in_api_unique"] = len(db_ids - scan["seen_api_ids"])

        self._emit(summary)
