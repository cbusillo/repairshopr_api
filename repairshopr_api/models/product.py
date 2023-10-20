from dataclasses import dataclass, field


@dataclass
class Product:
    id: int
    price_cost: float = 0
    price_retail: float = 0
    condition: str = ""
    description: str = ""
    maintain_stock: bool = False
    name: str = ""
    quantity: int = 0
    warranty: str = ""
    sort_order: str = ""
    reorder_at: str = ""
    disabled: bool = False
    taxable: bool = False
    product_category: str = ""
    category_path: str = ""
    upc_code: str = ""
    discount_percent: str = ""
    warranty_template_id: str = ""
    qb_item_id: str = ""
    desired_stock_level: str = ""
    price_wholesale: float = 0
    notes: str = ""
    tax_rate_id: str = ""
    physical_location: str = ""
    serialized: bool = False
    vendor_ids: list[int] = field(default=list)
    long_description: str = ""
    location_quantities: list[dict] = field(default=list)
    photos: list[dict] = field(default=list)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)
