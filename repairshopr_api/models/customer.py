from dataclasses import dataclass, field
from datetime import datetime

from repairshopr_api.base.model import BaseModel


@dataclass
class Properties(BaseModel):
    id: int = None
    type: int = None
    notification_billing: str = None
    notification_reports: str = None
    notification_marketing: str = None
    title: str = None
    li_school: str = None


@dataclass
class Contact(BaseModel):
    id: int
    name: str = None
    address1: str = None
    address2: str = None
    city: str = None
    state: str = None
    zip: str = None
    email: str = None
    phone: str = None
    mobile: str = None
    latitude: float = None
    longitude: float = None
    customer_id: int = None
    account_id: int = None
    notes: str = None
    created_at: datetime = None
    updated_at: datetime = None
    vendor_id: int = None
    properties: Properties = field(default_factory=Properties)
    opt_out: bool = None
    extension: str = None
    processed_phone: str = None
    processed_mobile: str = None


@dataclass
class Customer(BaseModel):
    id: int
    firstname: str = None
    lastname: str = None
    fullname: str = None
    business_name: str = None
    email: str = None
    phone: str = None
    mobile: str = None
    created_at: datetime = None
    updated_at: datetime = None
    pdf_url: str = None
    address: str = None
    address_2: str = None
    city: str = None
    state: str = None
    zip: str = None
    latitude: float = None
    longitude: float = None
    notes: str = None
    get_sms: bool = None
    opt_out: bool = None
    disabled: bool = None
    no_email: bool = None
    location_name: str = None
    location_id: int = None
    properties: Properties = field(default_factory=Properties)
    online_profile_url: str = None
    tax_rate_id: int = None
    notification_email: str = None
    invoice_cc_emails: str = None
    invoice_term_id: int = None
    referred_by: str = None
    ref_customer_id: int = None
    business_and_full_name: str = None
    business_then_name: str = None

    contacts: list[Contact] = field(default_factory=list[Contact])
