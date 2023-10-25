import logging
import re
from abc import ABC
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Self, TYPE_CHECKING, TypeVar

from config import settings

if TYPE_CHECKING:
    from repairshopr_api.client import Client


ModelType = TypeVar("ModelType", bound="BaseModel")
logger = logging.getLogger(__name__)


@dataclass
class BaseModel(ABC):
    id: int

    rs_client: "Client" = field(default=None, init=False, repr=False)  # Add a reference to the Client instance

    @classmethod
    def set_client(cls, client: "Client"):
        cls.rs_client = client

    @classmethod
    def from_dict(cls: type[ModelType], data: dict[str, Any]) -> ModelType:
        instance = cls(id=data.get("id", 0))

        cleaned_data = {cls.clean_key(key): value for key, value in data.items() if value}

        model_fields = {current_field.name for current_field in fields(cls)}
        extra_fields_in_data = set(cleaned_data.keys()) - model_fields
        if extra_fields_in_data and not settings.debug:
            raise AttributeError(
                f"{cls.__module__}.{cls.__name__} has extra fields: {extra_fields_in_data} with data: {cleaned_data}"
            )

        for current_field in fields(cls):
            if not current_field.init:
                continue

            if current_field.name in cleaned_data:
                value = cleaned_data[current_field.name]

                if isinstance(value, str) and isinstance(current_field.type, type) and issubclass(current_field.type, datetime):
                    value = datetime.fromisoformat(value)

                if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                    field_type = current_field.type.__args__[0] if hasattr(current_field.type, "__args__") else None
                    if issubclass(field_type, BaseModel):
                        value = [field_type.from_dict(item) for item in value]

                elif isinstance(value, dict):
                    field_type = current_field.type
                    if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                        value = field_type.from_dict({**value, "id": 0})

                setattr(instance, current_field.name, value)

        return instance

    @classmethod
    def _get_field_names(cls, attribute: str = None) -> set[str]:
        field_names = set()
        for model_item in cls.rs_client.get_model(cls):
            target = model_item
            if attribute:
                target = getattr(model_item, attribute, None)
            if target:
                target_keys = set(target.__dict__.keys())
                target_keys.discard("rs_client")
                field_names.update(target_keys)
        return field_names

    @classmethod
    def _log_field_info(cls, field_names: set[str], model_type: type[Self]) -> None:
        existing_attributes = set(f.name for f in fields(model_type))
        existing_attributes.discard("rs_client")
        logging.info(f"Found {len(field_names)} fields for {model_type.__name__}")
        logging.info(f"Fields: {field_names}")
        logging.warning(f"Missing fields: {(existing_attributes - field_names) or 'None'}")
        logging.warning(f"Extra fields: {(field_names - existing_attributes) or 'None'}")

    @classmethod
    def get_properties_fields(cls) -> list[str]:
        with settings.debug_on():
            properties_field_names = cls._get_field_names(attribute="properties")
            properties_model_type = next((f.type for f in fields(cls) if f.name == "properties"), None)
            if properties_model_type is None:
                raise AttributeError(f"{cls.__name__} does not have a 'properties' attribute.")
            cls._log_field_info(properties_field_names, properties_model_type)
        return list(properties_field_names)

    @classmethod
    def get_fields(cls) -> list[str]:
        with settings.debug_on():
            field_names = cls._get_field_names()
            cls._log_field_info(field_names, cls)
        return list(field_names)

    @classmethod
    def from_list(cls: type[ModelType], data: list[dict[str, Any]]) -> list[ModelType]:
        raise NotImplementedError("This method should be implemented in the subclass that expects a list.")

    @staticmethod
    def clean_key(key: str) -> str:
        cleaned_key = re.sub(r"[ /]", "_", key)
        cleaned_key = re.sub(r"^-", "transport", cleaned_key)
        cleaned_key = re.sub(r"_$", "_2", cleaned_key)
        cleaned_key = cleaned_key.replace(r"#", "num")
        return cleaned_key.lower()
