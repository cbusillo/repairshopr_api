from dataclasses import dataclass
from datetime import datetime

from repairshopr_api.base.fields import related_field
from repairshopr_api.base.model import BaseModel
from repairshopr_api.models import Product, User


# noinspection DuplicatedCode
@dataclass
class LineItem(BaseModel):
    id: int
    created_at: datetime = None
    updated_at: datetime = None
    invoice_id: int = None
    item: str = None
    name: str = None
    cost: float = None
    price: float = None
    quantity: float = None
    product_id: int = None
    taxable: bool = None
    discount_percent: float = None
    position: int = None
    invoice_bundle_id: int = None
    discount_dollars: float = None
    product_category: str = None

    @related_field(Product)
    def product(self) -> Product:
        pass


@dataclass
class Invoice(BaseModel):
    id: int
    customer_id: int = None
    customer_business_then_name: str = None
    number: str = None
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

    @related_field(User)
    def user(self) -> User:
        pass

    @related_field(LineItem)
    def line_items(self) -> list["LineItem"]:
        pass
