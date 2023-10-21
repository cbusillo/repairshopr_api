import re
from abc import ABC
from dataclasses import dataclass, field, fields
from typing import TypeVar

ModelType = TypeVar("ModelType", bound="BaseModel")


@dataclass
class BaseModel(ABC):
    id: int = None
    strict: bool = field(default=True, init=False, repr=False)

    @classmethod
    def from_dict(cls: type[ModelType], data: dict) -> ModelType:
        instance = cls(id=data.get("id", 0))

        cleaned_data = {re.sub(r"[ /]", "_", key).lower(): value for key, value in data.items()}

        for current_field in fields(cls):
            if not current_field.init:
                continue
            if current_field.name in cleaned_data:
                value = cleaned_data[current_field.name]

                if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                    field_type = current_field.type.__args__[0] if hasattr(current_field.type, "__args__") else None
                    if issubclass(field_type, BaseModel):
                        value = [field_type.from_dict(item) for item in value]

                elif isinstance(value, dict):
                    field_type = current_field.type
                    if issubclass(field_type, BaseModel):
                        value = field_type.from_dict({**value, "id": 0})

                setattr(instance, current_field.name, value)
            elif instance.strict:
                raise ValueError(f"Field {current_field.name} is missing from the data")

        return instance
