import re
from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime
from types import UnionType
from typing import TYPE_CHECKING, TypeVar, Union, get_args, get_origin

from repairshopr_api.type_defs import JsonValue, is_json_object
from repairshopr_api.utils import parse_datetime

if TYPE_CHECKING:
    from repairshopr_api.client import Client


ModelType = TypeVar("ModelType", bound="BaseModel")


@dataclass
class BaseModel(ABC):
    id: int | None

    rs_client: "Client | None" = field(default=None, init=False, repr=False)  # Add a reference to the Client instance

    @classmethod
    def set_client(cls, client: "Client") -> None:
        cls.rs_client = client

    @classmethod
    def from_dict(cls: type[ModelType], data: Mapping[str, JsonValue]) -> ModelType:
        raw_id = data.get("id", 0)
        instance_id = raw_id if isinstance(raw_id, int) else 0
        instance = cls(id=instance_id)
        cleaned_data: dict[str, JsonValue] = {cls.clean_key(key): value for key, value in data.items() if value is not None}

        for current_field in fields(cls):
            if not current_field.init:
                continue

            if current_field.name in cleaned_data:
                value: JsonValue | datetime | BaseModel | list[BaseModel] = cleaned_data[current_field.name]

                if isinstance(value, str) and cls._field_accepts_datetime(current_field.type):
                    parsed_value = parse_datetime(value)
                    if parsed_value is not None:
                        value = parsed_value

                if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                    model_type = cls._resolve_list_model_type(current_field.type)
                    if model_type is not None:
                        value = [model_type.from_dict(item) for item in value if is_json_object(item)]

                elif isinstance(value, dict):
                    model_type = cls._resolve_model_type(current_field.type)
                    if model_type is not None:
                        nested_payload = {"id": 0, **value}
                        value = model_type.from_dict(nested_payload)

                setattr(instance, current_field.name, value)

        return instance

    @classmethod
    def from_list(cls: type[ModelType], data: list[JsonValue]) -> ModelType | list[ModelType]:
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
