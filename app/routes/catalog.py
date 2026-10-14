from fastapi import APIRouter

from app.services.catalog_service import catalog_payload

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("")
async def get_catalog():
    """Public price list used by the order form and the support agent."""
    return catalog_payload()
