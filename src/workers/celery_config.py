import asyncio

from celery import Celery
from celery.signals import worker_process_init

from src.core.config import get_settings


@worker_process_init.connect
def reset_db_pool(**kwargs):
    """Reset database connection pool after Celery worker fork.

    When Celery forks worker processes (prefork pool), child processes
    inherit the parent's SQLAlchemy engine connection pool. Those inherited
    connections are stale and can cause errors. Disposing the pool forces
    new connections to be created on first use in the child process.
    """
    import asyncio
    from src.core.database import engine

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(engine.dispose())).result()
    else:
        asyncio.run(engine.dispose())


def run_async(coro):
    """Run an async coroutine from synchronous Celery tasks.

    Handles both fresh processes (prefork pool) and existing event loops
    (gevent/eventlet/solo pools).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


REDIS_URL = get_settings().redis_url
CELERY_BROKER_URL = get_settings().celery_broker_url or REDIS_URL

celery_app = Celery("inventory_tasks")

celery_app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_soft_time_limit=300,
    task_time_limit=600,
    include=[
        "src.workers.tasks.inventory_tasks",
        "src.workers.tasks.product_tasks",
        "src.workers.tasks.order_tasks",
        "src.workers.tasks.outgoing_webhook_retry",
        "src.workers.tasks.webhook_tasks",
    ],
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
        "process-pending-outgoing-webhook-retries": {
            "task": "src.workers.tasks.outgoing_webhook_retry.process_pending_retries",
            "schedule": 60.0,
        },
        "cleanup-old-webhook-logs": {
            "task": "src.workers.tasks.outgoing_webhook_retry.cleanup_old_webhook_logs",
            "schedule": 86400.0,
        },
        "auto-confirm-deliveries": {
            "task": "src.workers.tasks.order_tasks.auto_confirm_deliveries",
            "schedule": 3600.0,
        },
    },
)
