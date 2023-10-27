from dataclasses import dataclass, field
from datetime import datetime

from repairshopr_api.base.model import BaseModel


@dataclass
class Properties(BaseModel):
    id: int | None = None
    type: int | None = None
    notification_billing: str | None = None
    notification_reports: str | None = None
    notification_marketing: str | None = None
    title: str | None = None
    li_school: str | None = None


@dataclass
class Contact(BaseModel):
    id: int
    name: str | None = None
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    customer_id: int | None = None
    account_id: int | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    vendor_id: int | None = None
    properties: Properties = field(default_factory=Properties)
    opt_out: bool | None = None
    extension: str | None = None
    processed_phone: str | None = None
    processed_mobile: str | None = None


@dataclass
class Customer(BaseModel):
    id: int
    firstname: str | None = None
    lastname: str | None = None
    fullname: str | None = None
    business_name: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pdf_url: str | None = None
    address: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None
    get_sms: bool | None = None
    opt_out: bool | None = None
    disabled: bool | None = None
    no_email: bool | None = None
    location_name: str | None = None
    location_id: int | None = None
    properties: Properties = field(default_factory=Properties)
    online_profile_url: str | None = None
    tax_rate_id: int | None = None
    notification_email: str | None = None
    invoice_cc_emails: str | None = None
    invoice_term_id: int | None = None
    referred_by: str | None = None
    ref_customer_id: int | None = None
    business_and_full_name: str | None = None
    business_then_name: str | None = None

    contacts: list[Contact] = field(default_factory=list[Contact])
