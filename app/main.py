from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import connect_db, close_db
from app.exceptions.handlers import register_exception_handlers
from app.routes import auth, orders, tracking, newsletter


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
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


@app.get("/")
async def root():
    return {"message": "Gpron Integrated Service Platform API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
