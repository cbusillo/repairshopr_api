from dataclasses import dataclass, field
from datetime import datetime

from repairshopr_api.base.model import BaseModel
from repairshopr_api.models import User


@dataclass
class Invoice(BaseModel):
    id: int
    customer_id: int = None
    customer_business_then_name: str = None
    number: int = None
    created_at: datetime = None
    updated_at: datetime = None
    date: datetime = None
    due_date: datetime = None
    subtotal: float = None
    total: float = None
    tax: float = None
    verified_paid: bool = None
    tech_marked_paid: bool = None
    ticket_id: int = None
    user_id: int = None
    pdf_url: str = None
    is_paid: bool = None
    location_id: int = None
    po_number: str = None
    contact_id: int = None
    note: str = None
    hardwarecost: float = None

    _user: User = field(default=None, init=False, repr=False)

    @property
    def user(self) -> User:
        if not self._user and self.user_id:
            self._user = self._client.fetch_from_api_by_id(User, self.user_id)
        return self._user
