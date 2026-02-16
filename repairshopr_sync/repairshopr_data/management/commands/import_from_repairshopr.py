import logging
import pprint
import json
import requests
from uuid import uuid4
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Mapping, TypeAlias, TypeGuard

from django.core.management.base import BaseCommand
from django.db import DataError, DatabaseError, OperationalError, models
from django.utils.timezone import make_aware, now

from repairshopr_api.config import settings
from repairshopr_api.client import Client, ModelType
from repairshopr_api.base.model import BaseModel
from repairshopr_api.type_defs import JsonValue, QueryParams
from repairshopr_api.utils import coerce_datetime, parse_datetime
from repairshopr_data.models import (
    Invoice,
    InvoiceLineItem,
    SyncStatus,
    TicketType,
    TicketTypeField,
    TicketTypeFieldAnswer,
)
from repairshopr_data.models.estimate import EstimateLineItem

logger = logging.getLogger(__name__)

ApiInstance: TypeAlias = ModelType | SimpleNamespace
FieldValue: TypeAlias = JsonValue | datetime | models.Model
RELATED_PROPERTY_COLLECTIONS = frozenset({"line_items"})
BASELINE_UPDATED_AT = datetime(2010, 1, 1, tzinfo=timezone.utc)
LINE_ITEM_PARITY_ABSOLUTE_TOLERANCE = 50
LINE_ITEM_PARITY_RELATIVE_TOLERANCE = 0.005
FULL_SYNC_INVOICE_SAMPLE_SIZE = 12
INCREMENTAL_INVOICE_SAMPLE_SIZE = 4
HEARTBEAT_PAGE_INTERVAL = 10
HEARTBEAT_RECORD_INTERVAL = 100
HEARTBEAT_SECONDS_INTERVAL = 30


def _instance_values(api_instance: object) -> Mapping[str, object] | None:
    """Return instance values without triggering computed properties when possible."""

    if isinstance(api_instance, Mapping):
        return api_instance
    try:
        raw_values = vars(api_instance)
    except TypeError:
        return None
    return raw_values if isinstance(raw_values, Mapping) else None


def _instance_has_field(api_instance: object, field_name: str) -> bool:
    values = _instance_values(api_instance)
    if values is not None:
        return field_name in values
    return hasattr(api_instance, field_name)


def _instance_get_field(api_instance: object, field_name: str) -> object:
    values = _instance_values(api_instance)
    if values is not None:
        return values.get(field_name)
    return getattr(api_instance, field_name, None)


def _resolve_related_collection(api_instance: object, field_name: str) -> object:
    if _instance_has_field(api_instance, field_name):
        return _instance_get_field(api_instance, field_name)

    if field_name not in RELATED_PROPERTY_COLLECTIONS:
        return None

    descriptor = getattr(type(api_instance), field_name, None)
    if not isinstance(descriptor, property):
        return None

    return getattr(api_instance, field_name, None)


def _instance_with_updated_identifier(
    api_instance: object, normalized_identifier: int | None
) -> object:
    if isinstance(api_instance, Mapping):
        mutable_values = dict(api_instance)
        mutable_values["id"] = normalized_identifier
        return SimpleNamespace(**mutable_values)
    if isinstance(api_instance, SimpleNamespace):
        mutable_values = vars(api_instance).copy()
        mutable_values["id"] = normalized_identifier
        return SimpleNamespace(**mutable_values)
    if hasattr(api_instance, "id"):
        setattr(api_instance, "id", normalized_identifier)
    return api_instance


def _is_base_model_type(candidate: type) -> TypeGuard[type[BaseModel]]:
    return issubclass(candidate, BaseModel)


def _is_django_model_like(candidate: type) -> TypeGuard[type[models.Model]]:
    return hasattr(candidate, "_meta") and hasattr(candidate, "objects")


def _parse_datetime(value: str, *, field_name: str) -> datetime | None:
    parsed = parse_datetime(value)
    if parsed is None:
        logger.warning("Unable to parse datetime for %s: %s", field_name, value)
    return parsed


def _coerce_datetime(value: object, *, field_name: str) -> datetime | None:
    coerced = coerce_datetime(value)
    if isinstance(value, str) and coerced is None:
        logger.warning("Unable to parse datetime for %s: %s", field_name, value)
    return coerced


def _normalize_identifier(raw_identifier: object) -> int | None:
    if raw_identifier is None:
        return None
    if isinstance(raw_identifier, int):
        return None if raw_identifier == 0 else raw_identifier
    if isinstance(raw_identifier, str):
        stripped_value = raw_identifier.strip()
        if stripped_value in {"", "0"}:
            return None
        if stripped_value.isdigit() or (
            stripped_value.startswith("-") and stripped_value[1:].isdigit()
        ):
            return int(stripped_value)
    return None


def _coerce_integer_value(value: object, *, field_name: str) -> object:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped_value = value.strip()
        if stripped_value == "":
            return None
        if stripped_value.isdigit() or (
            stripped_value.startswith("-") and stripped_value[1:].isdigit()
        ):
            return int(stripped_value)
        logger.warning("Unable to parse integer for %s: %r", field_name, value)
        return None
    return value


def create_or_update_django_instance(
    django_model: type[models.Model],
    api_instance: ApiInstance | Mapping[str, object],
    extra_fields: Mapping[str, FieldValue] | None = None,
) -> models.Model | None:
    if extra_fields is None:
        extra_fields = {}

    model_fields = django_model._meta.fields
    field_data: dict[str, FieldValue] = {}
    # noinspection PyProtectedMember
    for field in model_fields:
        if field.auto_created or isinstance(field, models.AutoField):
            continue
        if _instance_has_field(api_instance, field.name):
            value = _instance_get_field(api_instance, field.name)
            if isinstance(field, models.IntegerField):
                value = _coerce_integer_value(
                    value, field_name=f"{django_model.__name__}.{field.name}"
                )
            if isinstance(field, models.DateTimeField):
                parsed_value = _coerce_datetime(
                    value, field_name=f"{django_model.__name__}.{field.name}"
                )
                if parsed_value is not None:
                    if parsed_value.tzinfo is None:
                        parsed_value = make_aware(parsed_value)
                    value = parsed_value
            elif isinstance(value, datetime) and value.tzinfo is None:
                value = make_aware(value)
            if isinstance(field, models.ForeignKey):
                related_django_model = field.related_model
                if not isinstance(
                    related_django_model, type
                ) or not _is_django_model_like(related_django_model):
                    raise TypeError(
                        f"Expected Django model type for foreign key, got {related_django_model!r}"
                    )

                related_api_instance = _instance_get_field(api_instance, field.name)
                if related_api_instance is None:
                    value = None
                else:
                    related_identifier = _normalize_identifier(
                        _instance_get_field(related_api_instance, "id")
                    )
                    related_api_instance = _instance_with_updated_identifier(
                        related_api_instance, related_identifier
                    )

                    value = create_or_update_django_instance(
                        related_django_model, related_api_instance
                    )

            field_data[field.name] = value

    field_data.update(extra_fields)
    lookup_identifier = _normalize_identifier(_instance_get_field(api_instance, "id"))
    primary_key_field = getattr(django_model._meta, "pk", None)
    is_auto_primary_key = isinstance(primary_key_field, models.AutoField)
    if (
        lookup_identifier is None
        and primary_key_field is not None
        and not is_auto_primary_key
    ):
        logger.warning(
            "Skipping %s import because id is missing or invalid.",
            django_model.__name__,
        )
        return None

    try:
        if lookup_identifier is None and is_auto_primary_key:
            obj = django_model.objects.create(**field_data)
        else:
            obj, _created = django_model.objects.update_or_create(
                defaults=field_data, id=lookup_identifier
            )
    except DataError as e:
        formatted_field_data = pprint.pformat(field_data)
        logger.error(
            f"DataError on {django_model.__name__} with data {formatted_field_data}: {e}"
        )
        raise
    except OperationalError as e:
        formatted_field_data = pprint.pformat(field_data)
        logger.error(
            f"OperationalError on {django_model.__name__} with data {formatted_field_data}: {e}"
        )
        raise
    return obj


class Command(BaseCommand):
    help = "Imports data from RepairShopr API into the local Django database"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.client = Client()
        self._cycle_id: str | None = None
        self._cycle_mode: str | None = None
        self._cycle_started_at: datetime | None = None
        self._status_current_model: str | None = None
        self._status_current_page: int = 0
        self._status_records_processed: int = 0
        self._status_last_written_at: datetime | None = None
        self._status_last_written_page: int = 0
        self._status_last_written_records: int = 0
        reverse_sort_on_updated_at = {"sort": "updated_at ASC"}
        self.model_mapping = {
            # Django model name: (num_last_pages, params)
            "Customer": (10, reverse_sort_on_updated_at),
            "Estimate": (1, None),
            "Invoice": (None, None),
            "Payment": (2, None),
            "Product": (2, reverse_sort_on_updated_at),
            "Ticket": (None, None),
            "User": (None, None),
        }

    def _upsert_sync_status(self, **updates: object) -> None:
        payload: dict[str, object] = {
            "cycle_id": self._cycle_id,
            "mode": self._cycle_mode,
            "status": "running",
            "current_model": self._status_current_model,
            "current_page": self._status_current_page,
            "records_processed": self._status_records_processed,
            "cycle_started_at": self._cycle_started_at,
            "last_heartbeat": now(),
            "last_error": None,
        }
        payload.update(updates)
        SyncStatus.objects.update_or_create(id=1, defaults=payload)

    def _set_model_sync_progress(self, model_name: str) -> None:
        self._status_current_model = model_name
        self._status_current_page = 0
        self._status_records_processed = 0
        self._status_last_written_page = 0
        self._status_last_written_records = 0
        self._status_last_written_at = None
        self._maybe_write_sync_heartbeat(force=True)

    def _on_page_progress(
        self,
        model_name: str,
        page: int,
        processed_rows: int,
        _processed_on_page: int,
        _meta_data: Mapping[str, object] | None,
    ) -> None:
        if self._status_current_model != model_name:
            self._status_current_model = model_name
        self._status_current_page = page
        self._status_records_processed = processed_rows
        self._maybe_write_sync_heartbeat()

    def _maybe_write_sync_heartbeat(self, *, force: bool = False) -> None:
        current_time = now()
        if not force:
            enough_records = (
                self._status_records_processed - self._status_last_written_records
            ) >= HEARTBEAT_RECORD_INTERVAL
            enough_pages = (
                self._status_current_page > self._status_last_written_page
                and self._status_current_page % HEARTBEAT_PAGE_INTERVAL == 0
            )
            enough_time = (
                self._status_last_written_at is None
                or (current_time - self._status_last_written_at).total_seconds()
                >= HEARTBEAT_SECONDS_INTERVAL
            )
            if not (enough_records or enough_pages or enough_time):
                return

        self._upsert_sync_status(last_heartbeat=current_time)
        self._status_last_written_at = current_time
        self._status_last_written_page = self._status_current_page
        self._status_last_written_records = self._status_records_processed

    def _mark_sync_cycle_started(self, *, full_sync: bool) -> None:
        self._cycle_id = uuid4().hex
        self._cycle_mode = "full" if full_sync else "incremental"
        self._cycle_started_at = now()
        self._status_current_model = None
        self._status_current_page = 0
        self._status_records_processed = 0
        self._status_last_written_page = 0
        self._status_last_written_records = 0
        self._status_last_written_at = None
        self._upsert_sync_status(
            status="running",
            current_model=None,
            current_page=0,
            records_processed=0,
            cycle_finished_at=None,
            last_error=None,
            last_heartbeat=self._cycle_started_at,
        )

    def _mark_sync_cycle_finished(self, *, error_message: str | None = None) -> None:
        final_status = "failed" if error_message else "success"
        self._upsert_sync_status(
            status=final_status,
            cycle_finished_at=now(),
            last_error=error_message,
            last_heartbeat=now(),
        )

    def get_submodel_class(
        self, parent_model_name: str, sub_model_suffix: str
    ) -> type[models.Model]:
        if sub_model_suffix.lower() != "properties" and sub_model_suffix.endswith("s"):
            sub_model_suffix = sub_model_suffix[:-1]

        formatted_sub_model_suffix = sub_model_suffix.title()
        imported = self.dynamic_import(
            f"repairshopr_data.models.{parent_model_name.lower()}.{parent_model_name}{formatted_sub_model_suffix}"
        )
        if not _is_django_model_like(imported):
            raise TypeError(
                f"Expected Django model class for submodel, got {imported!r}"
            )
        return imported

    def handle_model(
        self,
        django_model_path: str,
        api_model_path: str,
        num_last_pages: int | None = None,
        params: QueryParams | None = None,
    ) -> None:
        last_updated_at = settings.django.last_updated_at
        if last_updated_at and last_updated_at.tzinfo is None:
            last_updated_at = make_aware(last_updated_at)
        if not last_updated_at or last_updated_at < BASELINE_UPDATED_AT:
            num_last_pages = None

        django_model_candidate = self.dynamic_import(django_model_path)
        if not _is_django_model_like(django_model_candidate):
            raise TypeError(
                f"Expected Django model class, got {django_model_candidate!r}"
            )
        django_model = django_model_candidate

        api_model_candidate = self.dynamic_import(api_model_path)
        if not _is_base_model_type(api_model_candidate):
            raise TypeError(f"Expected BaseModel subclass, got {api_model_candidate!r}")
        api_model = api_model_candidate

        self._set_model_sync_progress(api_model.__name__.lower())

        api_instances = self.client.get_model(
            api_model, last_updated_at, num_last_pages, params
        )
        for api_instance in api_instances:
            # Keep heartbeat current during slow record-level processing.
            self._maybe_write_sync_heartbeat()
            django_instance = create_or_update_django_instance(
                django_model, api_instance
            )
            if django_instance is None:
                continue
            parent_model_name = django_model.__name__

            # noinspection PyProtectedMember
            for related_obj in django_model._meta.related_objects:
                sub_model_suffix = related_obj.name.replace(
                    parent_model_name.lower(), ""
                )
                sub_django_model = self.get_submodel_class(
                    parent_model_name, sub_model_suffix
                )

                sub_api_instances = _resolve_related_collection(
                    api_instance, related_obj.name
                )
                if not isinstance(sub_api_instances, list):
                    continue

                sub_django_instances = []
                skipped_submodel_instances = 0
                for sub_api_instance in sub_api_instances:
                    self._maybe_write_sync_heartbeat()
                    sub_django_instance = create_or_update_django_instance(
                        sub_django_model, sub_api_instance
                    )
                    if sub_django_instance is None:
                        skipped_submodel_instances += 1
                        continue
                    setattr(
                        sub_django_instance, related_obj.field.name, django_instance
                    )
                    if hasattr(sub_django_instance, "save"):
                        save = getattr(sub_django_instance, "save")
                        if callable(save):
                            save()
                    sub_django_instances.append(sub_django_instance)

                if not hasattr(django_instance, related_obj.name):
                    continue
                related_manager = getattr(django_instance, related_obj.name)
                set_method = getattr(related_manager, "set", None)
                if not callable(set_method):
                    continue
                if skipped_submodel_instances > 0:
                    if related_obj.name in RELATED_PROPERTY_COLLECTIONS:
                        logger.warning(
                            "Skipping relation reset for %s.%s due to %s skipped child imports.",
                            parent_model_name,
                            related_obj.name,
                            skipped_submodel_instances,
                        )
                        continue
                set_method(sub_django_instances)

            logger.info(
                self.style.SUCCESS(
                    f"Successfully imported {parent_model_name.rsplit('.', 1)[0]} {_instance_get_field(api_instance, 'id')}"
                )
            )

        self._maybe_write_sync_heartbeat(force=True)

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
    def _line_item_allowed_delta(expected_count: int) -> int:
        ratio_tolerance = int(expected_count * LINE_ITEM_PARITY_RELATIVE_TOLERANCE)
        return max(LINE_ITEM_PARITY_ABSOLUTE_TOLERANCE, ratio_tolerance)

    @staticmethod
    def _is_full_sync_run(last_updated_at: datetime | None) -> bool:
        if last_updated_at is None:
            return True
        if last_updated_at.tzinfo is None:
            last_updated_at = make_aware(last_updated_at)
        return last_updated_at < BASELINE_UPDATED_AT

    @staticmethod
    def _log_sync_check(event: str, payload: Mapping[str, object]) -> None:
        logger.info(
            "SYNC_CHECK %s",
            json.dumps({"event": event, **payload}, sort_keys=True, default=str),
        )

    def _fetch_line_item_total_entries(self, filter_key: str) -> int | None:
        _rows, meta_data = self.client.fetch_from_api(
            "line_item", params={filter_key: "true"}
        )
        if not isinstance(meta_data, dict):
            return None
        return self._normalize_total_entries(meta_data.get("total_entries"))

    def _fetch_invoice_line_item_count(self, invoice_id: int) -> int:
        total_rows = 0
        page = 1
        while True:
            self._status_current_page = page
            self._maybe_write_sync_heartbeat()
            params: QueryParams = {"invoice_id": invoice_id}
            if page > 1:
                params["page"] = page

            response_data, meta_data = self.client.fetch_from_api(
                "line_item", params=params
            )
            total_rows += len(response_data)
            self._status_records_processed += len(response_data)
            self._maybe_write_sync_heartbeat()

            if not isinstance(meta_data, dict):
                break

            total_pages = self._normalize_total_entries(meta_data.get("total_pages"))
            if total_pages is None or page >= total_pages:
                break
            page += 1

        return total_rows


    @staticmethod
    def _pick_first_invoice_id_at_or_after(target_id: int) -> int | None:
        return (
            Invoice.objects.filter(id__gte=target_id)
            .order_by("id")
            .values_list("id", flat=True)
            .first()
        )

    def _build_invoice_sample_ids(self, sample_size: int) -> list[int]:
        if sample_size <= 0:
            return []

        newest_count = min(3, sample_size)
        recent_invoice_ids = list(
            Invoice.objects.order_by("-updated_at", "-id").values_list("id", flat=True)[:newest_count]
        )

        aggregate = Invoice.objects.aggregate(min_id=models.Min("id"), max_id=models.Max("id"))
        min_id = aggregate.get("min_id")
        max_id = aggregate.get("max_id")
        if not isinstance(min_id, int) or not isinstance(max_id, int):
            return recent_invoice_ids

        remaining = max(0, sample_size - len(recent_invoice_ids))
        sampled_ids: list[int] = []
        if remaining == 1:
            sampled_ids = [min_id]
        elif remaining > 1:
            step_denominator = remaining - 1
            for index in range(remaining):
                target_id = min_id + ((max_id - min_id) * index // step_denominator)
                candidate_id = self._pick_first_invoice_id_at_or_after(target_id)
                if candidate_id is None:
                    candidate_id = (
                        Invoice.objects.filter(id__lte=target_id)
                        .order_by("-id")
                        .values_list("id", flat=True)
                        .first()
                    )
                if isinstance(candidate_id, int):
                    sampled_ids.append(candidate_id)

        deduplicated_ids: list[int] = []
        for candidate_id in recent_invoice_ids + sampled_ids:
            if candidate_id not in deduplicated_ids:
                deduplicated_ids.append(candidate_id)
        return deduplicated_ids

    def _evaluate_invoice_line_item_sample_parity(
        self, sample_size: int
    ) -> dict[str, object]:
        self._status_current_model = "line_item_sample"
        self._status_current_page = 0
        self._status_records_processed = 0
        self._maybe_write_sync_heartbeat(force=True)
        sample_invoice_ids = self._build_invoice_sample_ids(sample_size)
        mismatches: list[dict[str, int]] = []

        for sample_index, invoice_id in enumerate(sample_invoice_ids, start=1):
            self._status_current_page = sample_index
            self._maybe_write_sync_heartbeat()
            api_line_item_count = self._fetch_invoice_line_item_count(invoice_id)
            db_line_item_count = InvoiceLineItem.objects.filter(
                parent_invoice_id=invoice_id
            ).count()
            if api_line_item_count != db_line_item_count:
                mismatches.append(
                    {
                        "invoice_id": invoice_id,
                        "api_count": api_line_item_count,
                        "db_count": db_line_item_count,
                    }
                )
            self._status_records_processed = sample_index
            self._maybe_write_sync_heartbeat()

        return {
            "sample_size": len(sample_invoice_ids),
            "mismatch_count": len(mismatches),
            "mismatches": mismatches[:10],
        }

    def validate_sync_completeness(self, *, full_sync: bool) -> None:
        self._status_current_model = "sync_validation"
        self._status_current_page = 0
        self._status_records_processed = 0
        self._maybe_write_sync_heartbeat(force=True)
        needs_invoice_line_item_repair = False
        parity_expectations = (
            (
                "invoice_line_items",
                "invoice_id_not_null",
                InvoiceLineItem.objects.count,
            ),
            (
                "estimate_line_items",
                "estimate_id_not_null",
                EstimateLineItem.objects.count,
            ),
        )

        for parity_index, (model_name, filter_key, db_counter) in enumerate(
            parity_expectations, start=1
        ):
            self._status_current_page = parity_index
            self._maybe_write_sync_heartbeat()
            try:
                expected_total = self._fetch_line_item_total_entries(filter_key)
            except (
                requests.RequestException,
                PermissionError,
                ValueError,
                TypeError,
            ) as exc:
                logger.warning(
                    "Unable to fetch expected totals for %s during %s sync: %s",
                    model_name,
                    "full" if full_sync else "incremental",
                    exc,
                )
                continue

            if expected_total is None:
                logger.warning(
                    "RepairShopr metadata did not include total_entries for %s during %s sync.",
                    model_name,
                    "full" if full_sync else "incremental",
                )
                continue

            actual_total = db_counter()
            delta = actual_total - expected_total
            allowed_delta = self._line_item_allowed_delta(expected_total)

            self._log_sync_check(
                "line_item_parity",
                {
                    "model": model_name,
                    "mode": "full" if full_sync else "incremental",
                    "expected": expected_total,
                    "actual": actual_total,
                    "delta": delta,
                    "allowed_delta": allowed_delta,
                },
            )

            if abs(delta) > allowed_delta:
                logger.warning(
                    f"{model_name}: expected={expected_total} actual={actual_total} "
                    f"delta={delta} allowed_delta={allowed_delta}"
                )
                if model_name == "invoice_line_items" and delta < 0:
                    needs_invoice_line_item_repair = True
            self._status_records_processed = parity_index
            self._maybe_write_sync_heartbeat()

        sample_size = (
            FULL_SYNC_INVOICE_SAMPLE_SIZE
            if full_sync
            else INCREMENTAL_INVOICE_SAMPLE_SIZE
        )
        self._status_current_page += 1
        self._maybe_write_sync_heartbeat()
        try:
            sample_report = self._evaluate_invoice_line_item_sample_parity(sample_size)
        except (
            requests.RequestException,
            PermissionError,
            ValueError,
            TypeError,
            DatabaseError,
        ) as exc:
            logger.warning(
                "Unable to evaluate invoice line-item sample parity during %s sync: %s",
                "full" if full_sync else "incremental",
                exc,
            )
            self._log_sync_check(
                "invoice_line_item_sample_error",
                {
                    "mode": "full" if full_sync else "incremental",
                    "error": str(exc),
                },
            )
        else:
            self._log_sync_check(
                "invoice_line_item_sample",
                {
                    "mode": "full" if full_sync else "incremental",
                    **sample_report,
                },
            )

            mismatch_count = (
                self._normalize_total_entries(sample_report.get("mismatch_count")) or 0
            )
            allowed_sample_mismatches = 1 if full_sync else 2
            if mismatch_count > allowed_sample_mismatches:
                mismatch_message = (
                    f"Invoice line-item sample mismatches={mismatch_count} "
                    f"allowed={allowed_sample_mismatches}"
                )
                logger.warning(mismatch_message)
                needs_invoice_line_item_repair = True

        if full_sync and needs_invoice_line_item_repair:
            self._status_current_page += 1
            self._maybe_write_sync_heartbeat(force=True)
            logger.warning(
                "Invoice line-item parity mismatch detected during full sync; deferred to dedicated reconcile command."
            )
            self._log_sync_check(
                "invoice_line_item_repair_deferred",
                {
                    "mode": "full",
                    "reason": "global_line_item_parity_is_not_a_strict_truth_source",
                },
            )

    @staticmethod
    def dynamic_import(path: str) -> type:
        module_path, class_name = path.rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name.replace("_", ""))

    def handle(self, *_args, **_kwargs) -> None:
        last_updated_at = settings.django.last_updated_at
        full_sync = self._is_full_sync_run(last_updated_at)
        self._mark_sync_cycle_started(full_sync=full_sync)
        start_updated_at = self._cycle_started_at or now()
        logger.info(
            "SYNC_RUN start=%s mode=%s",
            start_updated_at.isoformat(),
            "full" if full_sync else "incremental",
        )
        if hasattr(self.client, "set_progress_callback"):
            self.client.set_progress_callback(self._on_page_progress)

        try:
            for model_name, (num_last_pages, params) in self.model_mapping.items():
                django_model_path = (
                    f"repairshopr_data.models.{model_name.lower()}.{model_name}"
                )
                api_model_path = f"repairshopr_api.models.{model_name}"
                self.handle_model(
                    django_model_path, api_model_path, num_last_pages, params
                )

            self.sync_ticket_settings()
            self.validate_sync_completeness(full_sync=full_sync)

            settings.django.last_updated_at = start_updated_at
            settings.save()

            end_updated_at = now()
            elapsed_seconds = int((end_updated_at - start_updated_at).total_seconds())
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            logger.info(
                "SYNC_RUN done start=%s end=%s elapsed_seconds=%s elapsed_hms=%02d:%02d:%02d",
                start_updated_at.isoformat(),
                end_updated_at.isoformat(),
                elapsed_seconds,
                hours,
                minutes,
                seconds,
            )
            self._mark_sync_cycle_finished()
        except Exception as exc:
            self._mark_sync_cycle_finished(error_message=str(exc))
            raise
        finally:
            if hasattr(self.client, "set_progress_callback"):
                self.client.set_progress_callback(None)
            self.client.clear_cache()

    def sync_ticket_settings(self) -> None:
        self._set_model_sync_progress("ticket_settings")
        try:
            payload = self.client.fetch_ticket_settings()
        except (
            requests.RequestException,
            PermissionError,
            ValueError,
            TypeError,
        ) as exc:
            logger.warning("Failed to fetch ticket settings: %s", exc)
            return

        ticket_types = payload.get("ticket_types", [])
        for item in ticket_types:
            TicketType.objects.update_or_create(
                id=item.get("id"),
                defaults={"name": item.get("name")},
            )
            self._status_records_processed += 1
            self._maybe_write_sync_heartbeat()

        ticket_fields = payload.get("ticket_type_fields", [])
        for item in ticket_fields:
            TicketTypeField.objects.update_or_create(
                id=item.get("id"),
                defaults={
                    "name": item.get("name"),
                    "field_type": item.get("field_type"),
                    "ticket_type_id": item.get("ticket_type_id"),
                    "position": item.get("position"),
                    "required": item.get("required"),
                },
            )
            self._status_records_processed += 1
            self._maybe_write_sync_heartbeat()

        ticket_answers = payload.get("ticket_type_field_answers", [])
        for item in ticket_answers:
            TicketTypeFieldAnswer.objects.update_or_create(
                id=item.get("id"),
                defaults={
                    "ticket_field_id": item.get("ticket_field_id"),
                    "value": item.get("value"),
                },
            )
            self._status_records_processed += 1
            self._maybe_write_sync_heartbeat()
