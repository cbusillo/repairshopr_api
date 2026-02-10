import logging
import pprint
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Mapping, TypeAlias, TypeGuard

from django.core.management.base import BaseCommand
from django.db import DataError, OperationalError, models
from django.utils.timezone import make_aware, now

from repairshopr_api.config import settings
from repairshopr_api.client import Client, ModelType
from repairshopr_api.base.model import BaseModel
from repairshopr_api.type_defs import JsonValue, QueryParams
from repairshopr_api.utils import coerce_datetime, parse_datetime
from repairshopr_data.models import TicketType, TicketTypeField, TicketTypeFieldAnswer

logger = logging.getLogger(__name__)

ApiInstance: TypeAlias = ModelType | SimpleNamespace
FieldValue: TypeAlias = JsonValue | datetime | models.Model


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
        if stripped_value.isdigit() or (stripped_value.startswith("-") and stripped_value[1:].isdigit()):
            return int(stripped_value)
    return None


def _coerce_integer_value(value: object, *, field_name: str) -> object:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped_value = value.strip()
        if stripped_value == "":
            return None
        if stripped_value.isdigit() or (stripped_value.startswith("-") and stripped_value[1:].isdigit()):
            return int(stripped_value)
        logger.warning("Unable to parse integer for %s: %r", field_name, value)
        return None
    return value


def create_or_update_django_instance(
    django_model: type[models.Model],
    api_instance: ApiInstance,
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
        if hasattr(api_instance, field.name):
            value = getattr(api_instance, field.name)
            if isinstance(field, models.IntegerField):
                value = _coerce_integer_value(value, field_name=f"{django_model.__name__}.{field.name}")
            if isinstance(field, models.DateTimeField):
                parsed_value = _coerce_datetime(value, field_name=f"{django_model.__name__}.{field.name}")
                if parsed_value is not None:
                    if parsed_value.tzinfo is None:
                        parsed_value = make_aware(parsed_value)
                    value = parsed_value
            elif isinstance(value, datetime) and value.tzinfo is None:
                value = make_aware(value)
            if isinstance(field, models.ForeignKey):
                related_django_model = field.related_model
                if not isinstance(related_django_model, type) or not _is_django_model_like(related_django_model):
                    raise TypeError(f"Expected Django model type for foreign key, got {related_django_model!r}")

                related_api_instance = getattr(api_instance, field.name)
                if _normalize_identifier(getattr(related_api_instance, "id", None)) is None:
                    related_api_instance.id = None

                value = create_or_update_django_instance(related_django_model, related_api_instance)
            field_data[field.name] = value

    field_data.update(extra_fields)
    lookup_identifier = _normalize_identifier(getattr(api_instance, "id", None))
    primary_key_field = getattr(django_model._meta, "pk", None)
    is_auto_primary_key = isinstance(primary_key_field, models.AutoField)
    if lookup_identifier is None and primary_key_field is not None and not is_auto_primary_key:
        logger.warning("Skipping %s import because id is missing or invalid.", django_model.__name__)
        return None

    try:
        if lookup_identifier is None and is_auto_primary_key:
            obj = django_model.objects.create(**field_data)
        else:
            obj, _created = django_model.objects.update_or_create(defaults=field_data, id=lookup_identifier)
    except DataError as e:
        formatted_field_data = pprint.pformat(field_data)
        logger.error(f"DataError on {django_model.__name__} with data {formatted_field_data}: {e}")
        raise
    except OperationalError as e:
        formatted_field_data = pprint.pformat(field_data)
        logger.error(f"OperationalError on {django_model.__name__} with data {formatted_field_data}: {e}")
        raise
    return obj


class Command(BaseCommand):
    help = "Imports data from RepairShopr API into the local Django database"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.client = Client()
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

    def get_submodel_class(self, parent_model_name: str, sub_model_suffix: str) -> type[models.Model]:
        if sub_model_suffix.lower() != "properties" and sub_model_suffix.endswith("s"):
            sub_model_suffix = sub_model_suffix[:-1]

        formatted_sub_model_suffix = sub_model_suffix.title()
        imported = self.dynamic_import(
            f"repairshopr_data.models.{parent_model_name.lower()}.{parent_model_name}{formatted_sub_model_suffix}"
        )
        if not _is_django_model_like(imported):
            raise TypeError(f"Expected Django model class for submodel, got {imported!r}")
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
        baseline_updated_at = datetime(2010, 1, 1, tzinfo=timezone.utc)
        if not last_updated_at or last_updated_at < baseline_updated_at:
            num_last_pages = None

        django_model_candidate = self.dynamic_import(django_model_path)
        if not _is_django_model_like(django_model_candidate):
            raise TypeError(f"Expected Django model class, got {django_model_candidate!r}")
        django_model = django_model_candidate

        api_model_candidate = self.dynamic_import(api_model_path)
        if not _is_base_model_type(api_model_candidate):
            raise TypeError(f"Expected BaseModel subclass, got {api_model_candidate!r}")
        api_model = api_model_candidate

        api_instances = self.client.get_model(api_model, last_updated_at, num_last_pages, params)
        for api_instance in api_instances:
            django_instance = create_or_update_django_instance(django_model, api_instance)
            if django_instance is None:
                continue
            parent_model_name = django_model.__name__

            # noinspection PyProtectedMember
            for related_obj in django_model._meta.related_objects:
                sub_model_suffix = related_obj.name.replace(parent_model_name.lower(), "")
                sub_django_model = self.get_submodel_class(parent_model_name, sub_model_suffix)

                if hasattr(api_instance, related_obj.name):
                    sub_api_instances = getattr(api_instance, related_obj.name)
                    sub_django_instances = []
                    for sub_api_instance in sub_api_instances:
                        sub_django_instance = create_or_update_django_instance(sub_django_model, sub_api_instance)
                        if sub_django_instance is None:
                            continue
                        setattr(sub_django_instance, related_obj.field.name, django_instance)
                        if hasattr(sub_django_instance, "save"):
                            save = getattr(sub_django_instance, "save")
                            if callable(save):
                                save()
                        sub_django_instances.append(sub_django_instance)

                    if hasattr(django_instance, related_obj.name):
                        getattr(django_instance, related_obj.name).set(sub_django_instances)

            logger.info(self.style.SUCCESS(f"Successfully imported {parent_model_name.rsplit('.', 1)[0]} {api_instance.id}"))

    @staticmethod
    def dynamic_import(path: str) -> type:
        module_path, class_name = path.rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name.replace("_", ""))

    def handle(self, *_args, **_kwargs) -> None:
        start_updated_at = now()
        logger.info("SYNC_RUN start=%s", start_updated_at.isoformat())
        for model_name, (num_last_pages, params) in self.model_mapping.items():
            django_model_path = f"repairshopr_data.models.{model_name.lower()}.{model_name}"
            api_model_path = f"repairshopr_api.models.{model_name}"
            self.handle_model(django_model_path, api_model_path, num_last_pages, params)

        self.sync_ticket_settings()

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
        self.client.clear_cache()

    def sync_ticket_settings(self) -> None:
        try:
            payload = self.client.fetch_ticket_settings()
        except Exception as exc:
            logger.warning("Failed to fetch ticket settings: %s", exc)
            return

        ticket_types = payload.get("ticket_types", [])
        for item in ticket_types:
            TicketType.objects.update_or_create(
                id=item.get("id"),
                defaults={"name": item.get("name")},
            )

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

        ticket_answers = payload.get("ticket_type_field_answers", [])
        for item in ticket_answers:
            TicketTypeFieldAnswer.objects.update_or_create(
                id=item.get("id"),
                defaults={
                    "ticket_field_id": item.get("ticket_field_id"),
                    "value": item.get("value"),
                },
            )
