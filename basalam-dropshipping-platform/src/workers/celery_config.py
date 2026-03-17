import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("inventory_tasks")

celery_app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "cleanup-expired-reservations": {
            "task": "src.workers.tasks.inventory_tasks.cleanup_expired_reservations",
            "schedule": 300.0,
        },
        "sync-inventory": {
            "task": "src.workers.tasks.inventory_tasks.sync_inventory",
            "schedule": 300.0,
        },
        "reconcile-inventory": {
            "task": "src.workers.tasks.inventory_tasks.reconcile_inventory",
            "schedule": 900.0,
        },
        "product-sync": {
            "task": "src.workers.tasks.product_tasks.product_sync",
            "schedule": 1800.0,
        },
        "order-sync": {
            "task": "src.workers.tasks.order_tasks.order_sync",
            "schedule": 120.0,
        },
    },
)
