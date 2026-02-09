import logging
import pprint
from datetime import date, datetime
from typing import Any

from django.core.management.base import BaseCommand
from django.db import DataError, OperationalError, models
from django.utils.timezone import make_aware, now

from repairshopr_api.config import settings
from repairshopr_api.client import Client, ModelType
from repairshopr_data.models import TicketType, TicketTypeField, TicketTypeFieldAnswer

logger = logging.getLogger(__name__)


def _parse_datetime(value: str, *, field_name: str) -> datetime | None:
    raw_value = value.strip()
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        logger.warning("Unable to parse datetime for %s: %s", field_name, value)
        return None


def _coerce_datetime(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        return _parse_datetime(value, field_name=field_name)
    return None


def create_or_update_django_instance(
    django_model: type[models.Model], api_instance: type[ModelType], extra_fields: dict[str, Any] | None = None
) -> models.Model:
    if extra_fields is None:
        extra_fields = {}

    field_data = {}
    # noinspection PyProtectedMember
    for field in django_model._meta.fields:
        if field.auto_created or isinstance(field, models.AutoField):
            continue
        if hasattr(api_instance, field.name):
            value = getattr(api_instance, field.name)
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
                related_api_instance = getattr(api_instance, field.name)
                if related_api_instance.id == 0:
                    related_api_instance.id = None

                # noinspection PyTypeChecker
                value = create_or_update_django_instance(related_django_model, related_api_instance)
            field_data[field.name] = value

    field_data.update(extra_fields)
    try:
        obj, created = django_model.objects.update_or_create(defaults=field_data, id=api_instance.id)
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
        return self.dynamic_import(
            f"repairshopr_data.models.{parent_model_name.lower()}.{parent_model_name}{formatted_sub_model_suffix}"
        )

    def handle_model(self, django_model_path, api_model_path, num_last_pages: int | None = None, params: dict | None = None):
        last_updated_at = settings.django.last_updated_at
        if not last_updated_at or last_updated_at < datetime(2010, 1, 1):
            num_last_pages = None

        django_model = self.dynamic_import(django_model_path)
        api_model = self.dynamic_import(api_model_path)

        api_instances = self.client.get_model(api_model, last_updated_at, num_last_pages, params)
        for api_instance in api_instances:
            django_instance = create_or_update_django_instance(django_model, api_instance)
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
                        setattr(sub_django_instance, related_obj.field.name, django_instance)
                        sub_django_instance.save()
                        sub_django_instances.append(sub_django_instance)

                    if hasattr(django_instance, related_obj.name):
                        getattr(django_instance, related_obj.name).set(sub_django_instances)

            logger.info(self.style.SUCCESS(f"Successfully imported {parent_model_name.rsplit('.', 1)[0]} {api_instance.id}"))

    @staticmethod
    def dynamic_import(path: str) -> type[ModelType] | type[models.Model]:
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
