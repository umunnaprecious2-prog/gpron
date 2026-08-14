"""Public order tracking: lookup by tracking id + progress payload."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.errors import NotFoundError
from app.models.db import Order

STATUS_LABELS = {
    "pending": "Order received and pending pickup",
    "picked_up": "Order picked up by our team",
    "in_cleaning": "Your items are being cleaned",
    "ready": "Your order is ready for delivery",
    "delivered": "Order delivered successfully",
}

STATUS_ORDER = ["pending", "picked_up", "in_cleaning", "ready", "delivered"]


async def get_order_by_tracking_id(db: AsyncSession, tracking_id: str) -> Order:
    result = await db.execute(
        select(Order).where(Order.tracking_id == tracking_id.upper())
    )
    order = result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Tracking ID not found")
    return order


def build_tracking_payload(order: Order) -> dict:
    current_index = (
        STATUS_ORDER.index(order.status) if order.status in STATUS_ORDER else 0
    )

    cart_out = [
        {
            "name": c["name"],
            "quantity": c["quantity"],
            "unit_price": c["unit_price"],
            "subtotal": round(c["unit_price"] * c["quantity"], 2),
        }
        for c in (order.cart or [])
    ]

    return {
        "tracking_id": order.tracking_id,
        "service_type": order.service_type,
        "status": order.status,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "price": order.price,
        "base_fee": order.base_fee or 0,
        "items": order.items or [],
        "cart": cart_out,
        "progress": current_index + 1,
        "total_steps": len(STATUS_ORDER),
        "steps": [
            {
                "step": i + 1,
                "key": s,
                "label": STATUS_LABELS[s],
                "completed": i <= current_index,
            }
            for i, s in enumerate(STATUS_ORDER)
        ],
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }
