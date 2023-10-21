from dataclasses import dataclass
from datetime import datetime

from repairshopr_api.base.model import BaseModel


@dataclass
class Estimate(BaseModel):
    id: int
    customer_id: int = None
    customer_business_then_name: str = None
    number: int = None
    status: str = None
    created_at: datetime = None
    updated_at: datetime = None
    date: datetime = None
    subtotal: float = None
    total: float = None
    tax: float = None
    ticket_id: int = None
    pdf_url: str = None
    location_id: int = None
    invoice_id: int = None
    employee: str = None
