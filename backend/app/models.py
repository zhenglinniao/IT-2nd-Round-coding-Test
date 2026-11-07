from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
PositiveDecimal = Annotated[Decimal, Field(gt=0, allow_inf_nan=False, le=1000000)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Address(InputModel):
    line1: Code
    suburb: Code
    state: Literal["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]
    postcode: Annotated[str, Field(pattern=r"^\d{4}$")]
    country: Literal["AU"] = "AU"


class Customer(InputModel):
    company: Code
    name: Code
    phone: str = ""
    email: str = ""
    address: Address


class Shipment(InputModel):
    id: Code
    carrier: Literal["startrack", "auspost", "tnt"]
    tracking_number: Annotated[str, Field(pattern=r"^[A-Za-z0-9-]{1,100}$")]


class Line(InputModel):
    id: Code
    sku: Code
    quantity: Annotated[StrictInt, Field(gt=0, le=1000000)]
    shipment_id: Code


class Order(InputModel):
    id: Code
    date: date
    status: Code
    customer: Customer
    shipments: list[Shipment]
    items: list[Line] = Field(min_length=1)
    source_note: str | None = None


class Product(InputModel):
    sku: Code
    name: Code
    rrp: Annotated[Decimal, Field(ge=0, le=1000000, allow_inf_nan=False, decimal_places=2)]
    weight_kg: PositiveDecimal | None = None
    width_cm: PositiveDecimal | None = None
    length_cm: PositiveDecimal | None = None
    height_cm: PositiveDecimal | None = None
    volume_m3: PositiveDecimal | None = None
