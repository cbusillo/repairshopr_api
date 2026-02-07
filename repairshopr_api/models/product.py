from dataclasses import dataclass, field

from repairshopr_api.base.model import BaseModel


@dataclass
class Product(BaseModel):
    id: int
    since_updated_at: str | None = None
    price_cost: float | None = None
    price_retail: float | None = None
    condition: str | None = None
    description: str | None = None
    maintain_stock: bool | None = None
    name: str | None = None
    quantity: int | None = None
    warranty: str | None = None
    sort_order: str | None = None
    reorder_at: str | None = None
    disabled: bool | None = None
    taxable: bool | None = None
    product_category: str | None = None
    category_path: str | None = None
    upc_code: str | None = None
    discount_percent: str | None = None
    warranty_template_id: str | None = None
    qb_item_id: str | None = None
    desired_stock_level: str | None = None
    price_wholesale: float | None = None
    notes: str | None = None
    tax_rate_id: str | None = None
    physical_location: str | None = None
    serialized: bool | None = None
    vendor_ids: list[int] = field(default=list)
    long_description: str | None = None
    location_quantities: list[dict] = field(default=list)
    photos: list[dict] = field(default=list)
