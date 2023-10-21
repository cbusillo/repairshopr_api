from datetime import datetime
from typing import Self
from dataclasses import dataclass
from repairshopr_api.base.model import BaseModel


@dataclass
class User(BaseModel):
    id: int
    email: str = None
    full_name: str = None
    created_at: datetime = None
    updated_at: datetime = None
    group: str = None
    admin: bool = None
    color: str = None

    def __post_init__(self) -> None:
        if not self.updated_at:
            data = self.client.fetch_from_api_by_id(User, self.id)
            for key, value in data.items():
                setattr(self, key, value)

    @classmethod
    def from_list(cls, data: list[str | int]) -> Self:
        return cls(id=data[0], full_name=data[1])
