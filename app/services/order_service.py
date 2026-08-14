"""Order creation, listing, status updates, pricing and tracking-id logic."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.errors import NotFoundError
from app.models.db import Log, Order, User
from app.validators.order import OrderCreate, OrderStatusUpdate

BASE_FEE = {
    "normal": 500.0,
    "express": 900.0,
}

# Per-item prices per service type (normal / express multiplier)
EXPRESS_MULTIPLIER = 1.6


async def generate_tracking_id(db: AsyncSession) -> str:
    # nextval() on a DB sequence is atomic under concurrent order creation,
    # unlike a SELECT count(*) which can race and hand out the same number
    # to two in-flight requests.
    year = datetime.utcnow().year
    result = await db.execute(text("SELECT nextval('order_tracking_seq')"))
    seq_value = result.scalar_one()
    return f"GPRON-{year}-{str(seq_value).zfill(4)}"


def calculate_order_total(service_type: str, cart: list[dict]) -> tuple[float, float]:
    """Returns (base_fee, total_price).
    Note: Frontend already applies price multiplier for express service,
    so we just sum the unit prices as-is."""
    base = BASE_FEE.get(service_type, 500.0)
    items_total = sum(item["unit_price"] * item["quantity"] for item in cart)
    total = round(base + items_total, 2)
    return base, total


async def create_order(
    db: AsyncSession, payload: OrderCreate, current_user: User
) -> Order:
    tracking_id = await generate_tracking_id(db)

    cart_dicts = [c.model_dump() for c in payload.cart]
    base_fee, total = calculate_order_total(payload.service_type.value, cart_dicts)

    # Flatten items list for tracking (repeat name * quantity)
    items_flat = [c["name"] for c in cart_dicts for _ in range(c["quantity"])]

    now = datetime.utcnow()
    order = Order(
        user_id=current_user.id,
        customer_name=current_user.name or "",
        customer_email=current_user.email or "",
        tracking_id=tracking_id,
        service_type=payload.service_type.value,
        status="pending",
        price=total,
        base_fee=base_fee,
        cart=cart_dicts,
        items=items_flat,
        notes=payload.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(order)
    db.add(
        Log(
            action=f"order_created:{tracking_id}",
            user_id=current_user.id,
            timestamp=now,
        )
    )
    await db.commit()
    await db.refresh(order)
    return order


async def get_user_orders(db: AsyncSession, current_user: User) -> list[Order]:
    result = await db.execute(
        select(Order)
        .where(Order.user_id == current_user.id)
        .order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())


async def get_all_orders(db: AsyncSession, status: Optional[str] = None) -> list[Order]:
    query = select(Order).order_by(Order.created_at.desc())
    if status:
        query = query.where(Order.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_order_status(
    db: AsyncSession, payload: OrderStatusUpdate, current_user: User
) -> Order:
    result = await db.execute(
        select(Order).where(Order.tracking_id == payload.tracking_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Order not found")

    now = datetime.utcnow()
    order.status = payload.status.value
    order.updated_at = now
    db.add(
        Log(
            action=f"status_updated:{payload.tracking_id}:{payload.status.value}",
            user_id=current_user.id,
            timestamp=now,
        )
    )
    await db.commit()
    await db.refresh(order)
    return order
