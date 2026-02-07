from dataclasses import dataclass
from datetime import datetime

from repairshopr_api.base.fields import related_field
from repairshopr_api.base.model import BaseModel
from repairshopr_api.models import Customer, Product, User


# noinspection DuplicatedCode
@dataclass
class LineItem(BaseModel):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    since_updated_at: str | None = None
    invoice_id: int | None = None
    item: str | None = None
    name: str | None = None
    cost: float | None = None
    price: float | None = None
    quantity: float | None = None
    product_id: int | None = None
    taxable: bool | None = None
    discount_percent: float | None = None
    position: int | None = None
    invoice_bundle_id: int | None = None
    discount_dollars: float | None = None
    product_category: str | None = None

    @related_field(Product)
    def product(self) -> Product:
        pass


@dataclass
class Estimate(BaseModel):
    id: int
    customer_id: int | None = None
    customer_business_then_name: str | None = None
    number: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    date: datetime | None = None
    subtotal: float | None = None
    total: float | None = None
    tax: float | None = None
    ticket_id: int | None = None
    pdf_url: str | None = None
    location_id: int | None = None
    invoice_id: int | None = None
    employee: str | None = None

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
