from typing import Optional

from pydantic import BaseModel, Field

from app.types.order import ServiceType, OrderStatus


class CartItem(BaseModel):
    name: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1, le=50)
    unit_price: float = Field(..., gt=0)


class OrderCreate(BaseModel):
    service_type: ServiceType
    cart: list[CartItem] = Field(..., min_length=1)
    notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    tracking_id: str
    status: OrderStatus
