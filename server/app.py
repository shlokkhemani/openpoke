from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .logging_config import configure_logging, logger
from .routes import api_router
from .services import get_important_email_watcher, get_trigger_scheduler


# Register global exception handlers for consistent error responses across the API
def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.debug("validation error", extra={"errors": exc.errors(), "path": str(request.url)})
        return JSONResponse(
            {"ok": False, "error": "Invalid request", "detail": exc.errors()},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        logger.debug(
            "http error",
            extra={"detail": exc.detail, "status": exc.status_code, "path": str(request.url)},
        )
        detail = exc.detail
        if not isinstance(detail, str):
            detail = json.dumps(detail)
        return JSONResponse({"ok": False, "error": detail}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error", extra={"path": str(request.url)})
        return JSONResponse(
            {"ok": False, "error": "Internal server error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


configure_logging()
_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown of background services."""
    # Startup: Initialize background services
    logger.info("=" * 80)
    logger.info("LIFESPAN STARTUP TRIGGERED")
    logger.info("=" * 80)

    # Initialize database FIRST
    try:
        from .database import check_db_connection, init_db
        logger.info("Initializing database...")

        if check_db_connection():
            init_db()
            logger.info("✅ Database initialized successfully")
        else:
            logger.warning("⚠️ Database connection failed - some features may not work")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        # Don't crash - fallback to JSON if DB unavailable

    logger.info("Starting background services")

    try:
        scheduler = get_trigger_scheduler()
        logger.info(f"Scheduler instance obtained: {scheduler}")
        await scheduler.start()
        logger.info("Trigger scheduler started successfully")

        watcher = get_important_email_watcher()
        logger.info(f"Email watcher instance obtained: {watcher}")
        await watcher.start()
        logger.info("Email watcher started successfully")

        logger.info("=" * 80)
        logger.info("ALL BACKGROUND SERVICES STARTED SUCCESSFULLY")
        logger.info("=" * 80)
    except Exception as e:
        logger.exception(f"CRITICAL ERROR during startup: {e}")
        raise

    yield
    
    # Shutdown: Gracefully stop background services
    logger.info("=" * 80)
    logger.info("LIFESPAN SHUTDOWN TRIGGERED")
    logger.info("=" * 80)
    logger.info("Stopping background services")
    await scheduler.stop()
    await watcher.stop()
    logger.info("Background services stopped successfully")


app = FastAPI(
    title=_settings.app_name,
    version=_settings.app_version,
    docs_url=_settings.resolved_docs_url,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)


__all__ = ["app"]
