from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ServiceType(str, Enum):
    normal = "normal"
    express = "express"


class OrderStatus(str, Enum):
    pending = "pending"
    picked_up = "picked_up"
    in_cleaning = "in_cleaning"
    ready = "ready"
    delivered = "delivered"


class CartItemOut(BaseModel):
    name: str
    quantity: int
    unit_price: float
    subtotal: float


class OrderOut(BaseModel):
    id: str
    tracking_id: str
    service_type: str
    status: str
    price: float
    base_fee: float
    items: list[str]
    cart: list[CartItemOut]
    notes: Optional[str]
    customer_name: str = ""
    customer_email: str = ""
    created_at: str
    updated_at: str
    user_id: str
