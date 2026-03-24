"""
Health Check API Endpoints
==========================
FastAPI endpoints for monitoring service health
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text

from src.core.config import get_settings
from src.core.database import async_session_maker
from src.core.events.publisher import EventPublisher


router = APIRouter(prefix="/health", tags=["Health Check"])


class HealthStatus(BaseModel):
    status: str
    details: Dict[str, Any]


class DependencyHealth(BaseModel):
    status: str
    message: str = ""


async def check_database() -> DependencyHealth:
    """Check database connection"""
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return DependencyHealth(status="healthy", message="Database connection OK")
    except Exception as e:
        return DependencyHealth(status="unhealthy", message=f"Database error: {str(e)}")


async def get_redis_client():
    """Get Redis client from environment"""
    redis_url = get_settings().redis_url
    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, decode_responses=True)
        yield client
        await client.close()
    except Exception as e:
        yield None


async def check_redis(redis_client) -> DependencyHealth:
    """Check Redis connection"""
    try:
        if redis_client is None:
            return DependencyHealth(
                status="unavailable", message="Redis client not configured"
            )
        await redis_client.ping()
        return DependencyHealth(status="healthy", message="Redis connection OK")
    except Exception as e:
        return DependencyHealth(status="unhealthy", message=f"Redis error: {str(e)}")


async def check_kafka() -> DependencyHealth:
    """Check Kafka connection"""
    kafka_servers = get_settings().kafka_bootstrap_servers
    if not kafka_servers:
        return DependencyHealth(status="unavailable", message="Kafka not configured")

    try:
        publisher = EventPublisher(kafka_bootstrap_servers=kafka_servers)
        producer = await publisher._get_producer()
        await publisher.close()
        return DependencyHealth(status="healthy", message="Kafka connection OK")
    except Exception as e:
        return DependencyHealth(status="unhealthy", message=f"Kafka error: {str(e)}")


@router.get("", response_model=HealthStatus)
async def health_check():
    """
    Basic health check endpoint
    Returns overall status of the service
    """
    return HealthStatus(status="ok", details={})


@router.get("/detailed", response_model=HealthStatus)
async def detailed_health_check():
    """
    Detailed health check endpoint
    Checks database, Redis, and Kafka connections
    """
    db_health = await check_database()
    redis_client = None
    try:
        import redis.asyncio as redis

        redis_url = get_settings().redis_url
        redis_client = redis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        redis_health = DependencyHealth(status="healthy", message="Redis connection OK")
    except Exception as e:
        redis_health = DependencyHealth(
            status="unhealthy", message=f"Redis error: {str(e)}"
        )
    finally:
        if redis_client:
            await redis_client.close()

    kafka_health = await check_kafka()

    dependencies = {
        "database": db_health.dict(),
        "redis": redis_health.dict(),
        "kafka": kafka_health.dict(),
    }

    all_healthy = all(dep["status"] == "healthy" for dep in dependencies.values())

    overall_status = "healthy" if all_healthy else "degraded"

    return HealthStatus(status=overall_status, details=dependencies)


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness():
    """Liveness probe - indicates if service is running"""
    return {"status": "alive"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness():
    """Readiness probe - indicates if service can handle requests"""
    db_health = await check_database()
    if db_health.status != "healthy":
        raise Exception("Database not ready")
    return {"status": "ready"}
