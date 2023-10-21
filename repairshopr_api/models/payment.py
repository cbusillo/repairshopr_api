from dataclasses import dataclass, field
from datetime import datetime

from repairshopr_api.base.fields import related_field
from repairshopr_api.base.model import BaseModel
from repairshopr_api.models import Customer, Invoice


@dataclass
class Payment(BaseModel):
    id: int
    created_at: datetime = None
    updated_at: datetime = None
    success: bool = None
    payment_amount: float = None
    invoice_ids: list[int] = field(default_factory=list)
    ref_num: str = None
    applied_at: datetime = None
    payment_method: str = None
    transaction_response: str = None
    signature_date: datetime = None
    customer: Customer = None

    @related_field(Invoice)
    def invoices(self) -> list[Invoice]:
        pass
