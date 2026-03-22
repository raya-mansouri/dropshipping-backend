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

from src.api.v1 import auth, orders, products, shops, health
from src.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run Alembic migrations on startup, then serve."""
    alembic_cfg = Config("alembic.ini")
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    yield


app = FastAPI(
    title="Basalam Dropshipping Platform API",
    description="API for the Basalam dropshipping platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
