from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.newsletter_service import subscribe as subscribe_service
from app.validators.newsletter import NewsletterSubscribe

router = APIRouter(prefix="/newsletter", tags=["newsletter"])


@router.post("/subscribe", status_code=201)
async def subscribe(payload: NewsletterSubscribe, db: AsyncSession = Depends(get_db)):
    await subscribe_service(db, payload)
    return {"message": "Subscribed successfully"}
