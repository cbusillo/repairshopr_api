import logging
import re
from abc import ABC
from dataclasses import dataclass, field, fields
from datetime import datetime
from types import UnionType
from typing import Any, Self, TYPE_CHECKING, TypeVar, Union, get_args, get_origin

from repairshopr_api.config import settings
from repairshopr_api.utils import parse_datetime

if TYPE_CHECKING:
    from repairshopr_api.client import Client


ModelType = TypeVar("ModelType", bound="BaseModel")
logger = logging.getLogger(__name__)


@dataclass
class BaseModel(ABC):
    id: int | None

    rs_client: "Client | None" = field(default=None, init=False, repr=False)  # Add a reference to the Client instance

    @classmethod
    def set_client(cls, client: "Client"):
        cls.rs_client = client

    @classmethod
    def from_dict(cls: type[ModelType], data: dict[str, Any]) -> ModelType:
        instance = cls(id=data.get("id", 0))
        cleaned_data = {cls.clean_key(key): value for key, value in data.items() if value is not None}

        for current_field in fields(cls):
            if not current_field.init:
                continue

            if current_field.name in cleaned_data:
                value = cleaned_data[current_field.name]

                if isinstance(value, str) and cls._field_accepts_datetime(current_field.type):
                    parsed_value = cls._parse_datetime(value)
                    if parsed_value is not None:
                        value = parsed_value

                if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                    model_type = cls._resolve_list_model_type(current_field.type)
                    if model_type is not None:
                        value = [model_type.from_dict(item) for item in value]

                elif isinstance(value, dict):
                    model_type = cls._resolve_model_type(current_field.type)
                    if model_type is not None:
                        nested_payload = {"id": 0, **value}
                        value = model_type.from_dict(nested_payload)

                setattr(instance, current_field.name, value)

        return instance

    @classmethod
    def _get_field_names(cls, attribute: str | None = None) -> set[str]:
        field_names = set()
        if not cls.rs_client:
            raise AttributeError("The rs_client attribute is not set.")
        for model_item in cls.rs_client.get_model(cls):
            target = model_item
            if attribute:
                target = getattr(model_item, attribute)
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

    @staticmethod
    def _field_accepts_datetime(field_type: object) -> bool:
        if field_type is datetime:
            return True
        return datetime in get_args(field_type)

    @staticmethod
    def _resolve_model_type(field_type: object) -> type["BaseModel"] | None:
        origin = get_origin(field_type)
        if origin in {Union, UnionType}:
            for arg in get_args(field_type):
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    return arg
            return None

        if isinstance(field_type, type) and issubclass(field_type, BaseModel):
            return field_type

        return None

    @classmethod
    def _resolve_list_model_type(cls, field_type: object) -> type["BaseModel"] | None:
        origin = get_origin(field_type)
        if origin is list:
            args = get_args(field_type)
            if not args:
                return None
            return cls._resolve_model_type(args[0])

        if origin in {Union, UnionType}:
            for arg in get_args(field_type):
                resolved = cls._resolve_list_model_type(arg)
                if resolved is not None:
                    return resolved

        return None

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        return parse_datetime(value)
