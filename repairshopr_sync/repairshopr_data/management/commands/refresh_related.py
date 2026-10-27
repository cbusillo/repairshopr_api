import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from repairshopr_data.management.commands.import_from_repairshopr import (
    _normalize_identifier,
    create_or_update_django_instance,
)
from repairshopr_data.models import Invoice, InvoiceLineItem, Ticket, TicketComment

from repairshopr_api.client import Client
from repairshopr_api.type_defs import JsonObject, QueryParams


class Command(BaseCommand):
    help = (
        "Compare complete invoice-line or ticket-comment feeds for explicit parent IDs. "
        "Defaults to read-only; --apply upserts children without deleting or unlinking rows. "
        "Stop the continuous sync before apply. The incremental checkpoint is unchanged."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--kind", choices=("invoice", "ticket"), required=True)
        selectors = parser.add_mutually_exclusive_group(required=True)
        selectors.add_argument("--id", type=int, action="append", dest="ids")
        selectors.add_argument("--id-file", type=Path, help="One parent ID per line")
        parser.add_argument("--apply", action="store_true")

    @staticmethod
    def _invoice_rows(client: Client, parent_id: int) -> list[JsonObject]:
        rows: list[JsonObject] = []
        page = 1
        while True:
            params: QueryParams = {"invoice_id": parent_id, "page": page}
            data, meta = client.fetch_from_api("line_item", params, use_cache=False)
            if not all(isinstance(row, dict) for row in data):
                raise CommandError("Invalid invoice line-item payload")
            rows.extend(row for row in data if isinstance(row, dict))
            pages = meta.get("total_pages") if meta else None
            if not isinstance(pages, int) or pages < 0 or (pages == 0 and data):
                raise CommandError("Missing or invalid invoice pagination")
            if page >= pages:
                return rows
            page += 1

    def handle(self, *_args: Any, **options: Any) -> None:
        kind = options["kind"]
        try:
            identifiers = options["ids"] or [
                int(line.strip()) for line in options["id_file"].read_text().splitlines() if line.strip()
            ]
        except (OSError, ValueError) as exc:
            raise CommandError("Cannot read parent IDs") from exc
        identifiers = sorted(set(identifiers))
        if not identifiers or len(identifiers) > 1000 or any(i <= 0 for i in identifiers):
            raise CommandError("Select between 1 and 1000 positive parent IDs per batch")
        parent_model, child_model, relation, source_parent = (
            (Invoice, InvoiceLineItem, "parent_invoice", "invoice_id")
            if kind == "invoice"
            else (Ticket, TicketComment, "ticket", "ticket_id")
        )
        parents = parent_model.objects.in_bulk(identifiers)
        if len(parents) != len(identifiers):
            raise CommandError("Every selected parent must already exist locally")
        client = Client()
        try:
            for parent_id in identifiers:
                rows = (
                    self._invoice_rows(client, parent_id)
                    if kind == "invoice"
                    else [vars(row) for row in client.fetch_ticket_comments(parent_id)]
                )
                by_id: dict[int, dict] = {}
                for row in rows:
                    identifier = _normalize_identifier(row.get("id"))
                    upstream_parent = _normalize_identifier(row.get(source_parent))
                    if identifier is None or identifier <= 0:
                        raise CommandError("Missing or invalid child ID")
                    if upstream_parent != parent_id and (kind == "invoice" or upstream_parent is not None):
                        raise CommandError("Child belongs to a different parent")
                    by_id[identifier] = row
                local_ids = set(child_model.objects.filter(**{f"{relation}_id": parent_id}).values_list("id", flat=True))
                missing = by_id.keys() - local_ids
                if options["apply"]:
                    # Fetch every page before writes; rollback this entire parent
                    # on an import failure. Previously completed parents can be replayed.
                    with transaction.atomic():
                        for row in by_id.values():
                            imported = create_or_update_django_instance(child_model, row, {relation: parents[parent_id]})
                            if imported is None:
                                raise CommandError("Child import failed")
                self.stdout.write(
                    json.dumps(
                        {
                            "kind": kind,
                            "parent_id": parent_id,
                            "api_unique": len(by_id),
                            "missing_before": len(missing),
                            "local_only_retained": len(local_ids - by_id.keys()),
                            "applied": bool(options["apply"]),
                        },
                        sort_keys=True,
                    )
                )
                client.clear_cache()
        finally:
            client.close()
