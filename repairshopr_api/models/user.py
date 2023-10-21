from typing import Self
from dataclasses import dataclass
from repairshopr_api.base.model import BaseModel


@dataclass
class User(BaseModel):
    strict: bool = False
    id: int
    email: str = None
    full_name: str = None
    created_at: str = None
    updated_at: str = None
    group: str = None
    admin: bool = None
    color: str = None

    @classmethod
    def from_list(cls, data: list[str | int]) -> Self:
        return cls(id=data[0], full_name=data[1])
