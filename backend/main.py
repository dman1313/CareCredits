import os
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.database import Base, engine, get_db, SessionLocal
from models import SchemaVersion, SCHEMA_VERSION
from errors import envelope, http_exception_handler, validation_exception_handler, request_id
from backend.archive.observe import setup as setup_logs, request_line, log as app_log

# === Import all domain routers ===
from routers.internal.ingestion import router as ingestion_router
from routers.auth import router as auth_router
from backend.routers.user import router as me_router
from routers.admin import router as admin_router


def production_env() -> bool:
    return (os.getenv("APP_ENV") or "").strip().casefold() == "production"


def initialize():
    if os.getenv("DEMO_MODE") == "true" and production_env():
        raise RuntimeError("Demo mode cannot run in production")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        migrate_schema(db)
        if os.getenv("DEMO_MODE") == "true":
            from seed_demo import seed
            seed(db)


def migrate_schema(db):
    versions = db.query(SchemaVersion).all()
    current = max((v.version for v in versions), default=0)
    if current >= SCHEMA_VERSION:
        return
    db.add(SchemaVersion(version=SCHEMA_VERSION))
    db.commit()


@asynccontextmanager
async def lifespan(app):
    initialize()
    import asyncio

    stop = asyncio.Event()
    tasks = []

    async def retention_loop():
        while not stop.is_set():
            try:
                with SessionLocal() as db:
                    from backend.archive.schedule import purge_expired_source_text
                    purge_expired_source_text(db)
            except Exception as exc:
                app_log.warning("retention_loop failed message=%s", str(exc)[:200])
            try:
                await asyncio.wait_for(stop.wait(), timeout=86400)
            except asyncio.TimeoutError:
                continue

    tasks.append(asyncio.create_task(retention_loop()))
    yield
    stop.set()
    for task in tasks:
        try:
            await asyncio.wait_for(task, timeout=2)
        except Exception:
            task.cancel()


app = FastAPI(title="CareCredits", version="0.5.0", lifespan=lifespan)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return envelope(500, "Request failed.", request)


setup_logs()

DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def normalize_origin(value: str | None) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned or cleaned.casefold() == "null":
        return ""
    return cleaned.casefold()


def origin_allowed(origin: str | None, allowed: list[str] | set[str] | tuple[str, ...]) -> bool:
    normalized = normalize_origin(origin)
    if not normalized:
        return False
    allowlist = {normalize_origin(item) for item in allowed if normalize_origin(item)}
    return normalized in allowlist


@app.middleware("http")
async def request_boundary(request: Request, call_next):
    started = time.perf_counter()
    request.state.request_id = secrets.token_hex(8)
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.url.path.startswith("/internal/"):
        origins = [item for item in os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",") if item.strip()]
        if (request.headers.get("x-care-client") or "").strip() != "1" or not origin_allowed(
            request.headers.get("origin"), origins
        ):
            return envelope(403, "Request origin not allowed.", request)
    try:
        result = await call_next(request)
    except Exception:
        return envelope(500, "Request failed.", request)
    result.headers["Cache-Control"] = "no-store"
    result.headers["X-Content-Type-Options"] = "nosniff"
    rid = request_id(request)
    result.headers["X-Request-Id"] = rid
    duration_ms = int((time.perf_counter() - started) * 1000)
    request_line(rid, request.method, request.url.path, result.status_code, duration_ms)
    return result


# === Register All Routers ===
app.include_router(ingestion_router)
app.include_router(auth_router)       
app.include_router(me_router)
app.include_router(admin_router)


# === Health Endpoints Only (Infrastructure) ===
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/live")
def health_live():
    return {"status": "live"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "Database is unavailable.")
    return {"status": "ready", "database": "ready"}