from dataclasses import dataclass
from datetime import datetime

from repairshopr_api.base.fields import related_field
from repairshopr_api.base.model import BaseModel
from repairshopr_api.models import Customer, Product, User


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
class Estimate(BaseModel):
    id: int
    customer_id: int = None
    customer_business_then_name: str = None
    number: str = None
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

    @related_field(Customer)
    def customer(self) -> Customer:
        pass

    @property
    def user(self) -> User:
        users = self.rs_client.get_model(User)
        for user in users:
            if user.email == self.employee:
                return user

    @related_field(LineItem)
    def line_items(self) -> list[LineItem]:
        pass
