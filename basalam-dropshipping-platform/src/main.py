"""
FastAPI Application Entry Point
===============================
Main FastAPI application with all routers.
Runs Alembic migrations on startup via asyncio.to_thread.
"""
import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from src.api.v1 import auth, orders, products, shops, health
from src.api.v1 import webhooks, webhook_health
from src.core.config import get_settings

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run Alembic migrations on startup, then serve."""
    logger.info("application_starting")

    alembic_cfg = Config("alembic.ini")
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    logger.info("application_ready")
    yield
    logger.info("application_shutting_down")


# Check if we should serve docs offline (no CDN)
DOCS_OFFLINE = get_settings().docs_offline

app = FastAPI(
    title="Basalam Dropshipping Platform API",
    description="API for the Basalam dropshipping platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if DOCS_OFFLINE else "/docs",
    redoc_url=None if DOCS_OFFLINE else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for Swagger UI
app.mount("/static", StaticFiles(directory="src/static"), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Serve Swagger UI with local static files (no CDN)."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Basalam API - Swagger UI",
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    """Serve ReDoc with local static files (no CDN)."""
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="Basalam API - ReDoc",
        redoc_js_url="/static/swagger-ui/redoc.standalone.js",
    )

app.include_router(auth.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(shops.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(webhook_health.router, prefix="/api/v1")


# ============================================
# Global Exception Handlers
# ============================================


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors"""
    errors = exc.errors()
    logger.error(f"Validation error: {errors}")
    return JSONResponse(
        status_code=422, content={"detail": "Validation error", "errors": errors}
    )


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    """Handle ValueError exceptions"""
    logger.error(f"ValueError: {str(exc)}")
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions - logs the full traceback"""
    # Check if we're in production mode
    try:
        from src.core.config import get_settings

        settings = get_settings()
        is_production = settings.app_env == "production"
    except Exception:
        is_production = False

    # Always log the full error
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}\n"
        f"Full traceback:\n{traceback.format_exc()}"
    )

    # Return different responses based on environment
    if is_production:
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Basalam Dropshipping Platform API", "version": "1.0.0"}


@app.get("/ping")
async def ping():
    """Simple ping endpoint"""
    return {"pong": True}
