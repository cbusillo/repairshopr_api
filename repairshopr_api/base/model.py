import re
from abc import ABC
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from repairshopr_api.client import Client


ModelType = TypeVar("ModelType", bound="BaseModel")


@dataclass
class BaseModel(ABC):
    id: int

    client: "Client" = field(default=None, init=False, repr=False)  # Add a reference to the Client instance

    @classmethod
    def set_client(cls, client: "Client"):
        cls.client = client

    @classmethod
    def from_dict(cls: type[ModelType], data: dict[str, Any]) -> ModelType:
        instance = cls(id=data.get("id", 0))

        cleaned_data = {re.sub(r"[ /]", "_", key).lower(): value for key, value in data.items() if value}

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
    def from_list(cls: type[ModelType], data: list[dict[str, Any]]) -> list[ModelType]:
        raise NotImplementedError("This method should be implemented in the subclass that expects a list.")
