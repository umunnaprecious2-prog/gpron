from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.tracking_service import (
    build_tracking_payload,
    get_order_by_tracking_id,
)

router = APIRouter(prefix="/track", tags=["tracking"])


@router.get("/{tracking_id}")
async def track_order(tracking_id: str, db: AsyncSession = Depends(get_db)):
    order = await get_order_by_tracking_id(db, tracking_id)
    return build_tracking_payload(order)
