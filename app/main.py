import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import SessionLocal, close_db, connect_db
from app.exceptions.handlers import register_exception_handlers
from app.middlewares.body_size_middleware import BodySizeLimitMiddleware
from app.routes import auth, catalog, metrics, newsletter, orders, support, tracking
from app.services.support_worker import build_support_runtime

# App loggers at INFO (uvicorn only configures its own). Log lines are
# key=value and never include message text, tokens or contact details.
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    runtime = build_support_runtime(settings, SessionLocal)
    app.state.support = runtime
    if runtime.worker:
        await runtime.worker.start()
    yield
    if runtime.worker:
        await runtime.worker.stop()
    await close_db()


app = FastAPI(
    title="Gpron Integrated Service Platform",
    version="1.0.0",
    lifespan=lifespan,
)

allowed_origins = (
    ["*"]
    if settings.allowed_origins.strip() == "*"
    else [
        origin.strip()
        for origin in settings.allowed_origins.split(",")
        if origin.strip()
    ]
)

app.add_middleware(BodySizeLimitMiddleware, voice_limit=settings.voice_max_upload_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # The frontend authenticates with a Bearer token (see frontend/src/api.js),
    # never cookies, so it never sends credentials: 'include'. Keeping this
    # False avoids the CORS-spec conflict between a wildcard origin and
    # allow_credentials=True (browsers reject that combination outright).
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(tracking.router)
app.include_router(newsletter.router)
app.include_router(catalog.router)
app.include_router(support.router)
app.include_router(metrics.router)


@app.get("/")
async def root():
    return {"message": "Gpron Integrated Service Platform API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
