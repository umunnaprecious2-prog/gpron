from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middlewares.auth_middleware import get_current_user, require_manager
from app.models.db import Order, User
from app.services.order_service import (
    create_order as create_order_service,
    get_all_orders as get_all_orders_service,
    get_user_orders as get_user_orders_service,
    update_order_status as update_order_status_service,
)
from app.types.order import CartItemOut, OrderOut
from app.validators.order import OrderCreate, OrderStatusUpdate

router = APIRouter(prefix="/orders", tags=["orders"])


def format_order(order: Order) -> OrderOut:
    return OrderOut(
        id=str(order.id),
        tracking_id=order.tracking_id,
        service_type=order.service_type,
        status=order.status,
        price=order.price,
        base_fee=order.base_fee,
        items=order.items or [],
        cart=[
            CartItemOut(
                name=c["name"],
                quantity=c["quantity"],
                unit_price=c["unit_price"],
                subtotal=round(c["unit_price"] * c["quantity"], 2),
            )
            for c in (order.cart or [])
        ],
        notes=order.notes,
        customer_name=order.customer_name or "",
        customer_email=order.customer_email or "",
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
        user_id=str(order.user_id),
    )


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await create_order_service(db, payload, current_user)
    return format_order(order)


@router.get("/user", response_model=list[OrderOut])
async def get_user_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orders = await get_user_orders_service(db, current_user)
    return [format_order(o) for o in orders]


@router.get("/all", response_model=list[OrderOut])
async def get_all_orders(
    status: Optional[str] = None,
    current_user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    orders = await get_all_orders_service(db, status)
    return [format_order(o) for o in orders]


@router.patch("/status", response_model=OrderOut)
async def update_order_status(
    payload: OrderStatusUpdate,
    current_user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    order = await update_order_status_service(db, payload, current_user)
    return format_order(order)
