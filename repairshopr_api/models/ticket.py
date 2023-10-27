from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from repairshopr_api.base.model import BaseModel


class DayEnum(Enum):
    MONDAY = 1234
    TUESDAY = 2345
    WEDNESDAY = 3456
    THURSDAY = 4567
    FRIDAY = 5678
    SATURDAY = 6789
    SUNDAY = 7890


@dataclass
class Comment(BaseModel):
    id: int
    created_at: str | None = None
    updated_at: str | None = None
    ticket_id: int | None = None
    subject: str | None = None
    body: str | None = None
    tech: str | None = None
    hidden: bool | None = None
    user_id: int | None = None


@dataclass
class Properties(BaseModel):
    id: int | None = None
    day: DayEnum | None = None
    case: str | None = None
    other: str | None = None
    s_n_num: str | None = None
    tag_num: str | None = None
    claim_num: str | None = None
    location: str | None = None
    transport: str | None = None
    boces: str | None = None
    tag_num_2: str | None = None
    delivery_num: str | None = None
    transport_2: str | None = None
    po_num_2: str | None = None
    phone_num: str | None = None
    p_g_name: str | None = None
    student: str | None = None
    s_n: str | None = None
    drop_off_location: str | None = None
    call_num: str | None = None


@dataclass
class Ticket(BaseModel):
    id: int
    number: int | None = None
    subject: str | None = None
    created_at: datetime | None = None
    customer_id: int | None = None
    customer_business_then_name: str | None = None
    due_date: datetime | None = None
    resolved_at: datetime | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    location_id: int | None = None
    problem_type: str | None = None
    status: str | None = None
    ticket_type_id: int | None = None
    properties: Properties = field(default_factory=Properties)
    user_id: int | None = None
    updated_at: str | None = None
    pdf_url: str | None = None
    priority: str | None = None
    comments: list[Comment] = field(default_factory=list)
