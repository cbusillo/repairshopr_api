from dataclasses import dataclass, field

from repairshopr_api.base.model import BaseModel


@dataclass
class Product(BaseModel):
    id: int
    price_cost: float = None
    price_retail: float = None
    condition: str = None
    description: str = None
    maintain_stock: bool = None
    name: str = None
    quantity: int = None
    warranty: str = None
    sort_order: str = None
    reorder_at: str = None
    disabled: bool = None
    taxable: bool = None
    product_category: str = None
    category_path: str = None
    upc_code: str = None
    discount_percent: str = None
    warranty_template_id: str = None
    qb_item_id: str = None
    desired_stock_level: str = None
    price_wholesale: float = None
    notes: str = None
    tax_rate_id: str = None
    physical_location: str = None
    serialized: bool = None
    vendor_ids: list[int] = field(default=list)
    long_description: str = None
    location_quantities: list[dict] = field(default=list)
    photos: list[dict] = field(default=list)
