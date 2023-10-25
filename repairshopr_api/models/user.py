from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Self

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
        if not self.updated_at and self.rs_client.updated_at and self.rs_client.updated_at > datetime.now() - timedelta(days=1):
            data = self.rs_client.fetch_from_api_by_id(User, self.id)
            for key, value in data.items():
                setattr(self, key, value)

    @classmethod
    def from_list(cls, data: list[str | int]) -> Self:
        return cls(id=data[0], full_name=data[1])
