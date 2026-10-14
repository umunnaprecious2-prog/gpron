import hmac

from fastapi import APIRouter, Header
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import settings
from app.exceptions.errors import NotFoundError

router = APIRouter(tags=["monitoring"])


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint(authorization: str | None = Header(None)):
    """Prometheus scrape target. Disabled (404) unless METRICS_TOKEN is set,
    and then only served to callers presenting it as a bearer token."""
    expected = settings.metrics_token
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(supplied, expected):
        raise NotFoundError("Not found")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
