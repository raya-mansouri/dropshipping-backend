"""
FastAPI Application Entry Point
===============================
Main FastAPI application with all routers
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1 import auth, orders, products, shops, health
from src.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    await init_db()
    yield


app = FastAPI(
    title="Basalam Dropshipping Platform API",
    description="API for the Basalam dropshipping platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
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
