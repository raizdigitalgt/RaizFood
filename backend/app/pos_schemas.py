from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.restaurant_schemas import ID, Money, Name, Payload, Quote, Text

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
Mode = Literal["dine_in", "takeaway", "delivery"]


class CreateOrder(Payload):
    request_id: ID
    mode: Mode
    table_id: ID | None = None
    customer_id: ID | None = None
    waiter_id: ID | None = None
    guests: Annotated[int, Field(ge=0, le=1000)] = 0
    name: Text = ""
    phone: Text = ""
    address: Text = ""
    reference: Text = ""
    estimated_at: Annotated[int, Field(ge=0, le=4_102_444_800)] | None = None
    notes: Text = ""
    shipping_cents: Money = 0


class Action(Payload):
    request_id: ID
    version: Annotated[int, Field(ge=1)]


class Line(Action, Quote):
    op: Literal["add", "edit"]
    item_id: ID
    line_id: ID | None = None
    notes: Text = ""
    reason: Reason | None = None


class Remove(Action):
    op: Literal["remove"]
    line_id: ID
    reason: Reason | None = None


class Simple(Action):
    op: Literal["confirm", "send", "bill", "deliver", "merge", "reopen_bill"]


class EditOrder(Action):
    op: Literal["details"]
    notes: Text
    waiter_id: ID | None = None


class Delivery(Action):
    op: Literal["delivery"]
    state: Literal["pending", "en_route", "delivered"]


class Cancel(Action):
    op: Literal["cancel"]
    reason: Reason


class Transfer(Action):
    op: Literal["transfer"]
    table_id: ID
    reason: Text = ""


class Discount(Action):
    op: Literal["discount"]
    line_id: ID | None = None
    kind: Literal["fixed", "percent"]
    value: Annotated[int, Field(ge=0, le=100_000_000)]
    reason: Reason


class Portion(Payload):
    line_id: ID
    quantity: Annotated[int, Field(ge=1, le=1000)]


class Split(Action):
    op: Literal["split"]
    name: Name
    source_id: ID | None = None
    items: Annotated[list[Portion], Field(min_length=1, max_length=100)]


Command = Annotated[
    Line | Remove | Simple | EditOrder | Delivery | Cancel | Transfer | Discount | Split,
    Field(discriminator="op"),
]


class KitchenAction(Action):
    state: Literal["preparing", "ready"]
    ticket_line_id: ID | None = None


class KitchenConfig(Payload):
    preparation_ids: Annotated[list[ID], Field(max_length=100)] = []


class PosConfig(Payload):
    kitchen_warning_minutes: Annotated[int, Field(ge=1, le=180)] = 15
    max_discount_bps: Annotated[int, Field(ge=0, le=10000)] = 10000
    max_discount_cents: Money = 100_000_000
