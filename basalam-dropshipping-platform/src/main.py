"""
FastAPI Application Entry Point
===============================
Main FastAPI application with all routers.
Runs Alembic migrations on startup via asyncio.to_thread.
"""
import asyncio
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.staticfiles import StaticFiles

from src.api.v1 import auth, orders, products, shops, health
from src.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run Alembic migrations on startup, then serve."""
    alembic_cfg = Config("alembic.ini")
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    yield


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


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Basalam Dropshipping Platform API", "version": "1.0.0"}


@app.get("/ping")
async def ping():
    """Simple ping endpoint"""
    return {"pong": True}
