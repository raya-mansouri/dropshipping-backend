#!/usr/bin/env python3
"""
Kafka Consumer Runner
=====================
Starts all Kafka consumers concurrently, including ProductSyncConsumer.
"""
import asyncio
import signal
import structlog
import logging

from src.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


async def main():
    from src.workers.consumers.product_consumer import ProductConsumer
    from src.workers.consumers.inventory_consumer import InventoryConsumer
    from src.workers.consumers.order_consumer import OrderConsumer
    from src.workers.consumers.payment_consumer import PaymentUpdatedConsumer
    from src.workers.consumers.webhook_consumer import WebhookConsumer
    from src.workers.consumers.product_sync_consumer import ProductSyncConsumer

    settings = get_settings()
    bootstrap = settings.kafka_bootstrap_servers

    # Some consumers take bootstrap_servers, others have custom __init__
    consumers = [
        ProductConsumer(bootstrap_servers=bootstrap),
        InventoryConsumer(bootstrap_servers=bootstrap),
        OrderConsumer(bootstrap_servers=bootstrap),
        PaymentUpdatedConsumer(),  # Reads settings internally
        WebhookConsumer(bootstrap_servers=bootstrap),
        ProductSyncConsumer(bootstrap_servers=bootstrap),
    ]

    # Start all consumers
    for c in consumers:
        try:
            await c.start()
        except Exception as e:
            logger.error("consumer_start_failed", topic=c.topic, error=str(e))

    # Run consume loops concurrently
    consume_tasks = []
    for c in consumers:
        task = asyncio.create_task(c.consume(), name=f"consume-{c.topic}")
        consume_tasks.append(task)

    logger.info("all_consumers_started", count=len(consumers))

    # Run until shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler(*_):
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await shutdown_event.wait()

    # Cancel consume tasks and stop consumers
    for task in consume_tasks:
        task.cancel()
    for task in consume_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    for c in consumers:
        try:
            await c.stop()
        except Exception as e:
            logger.error("consumer_stop_failed", topic=c.topic, error=str(e))

    logger.info("all_consumers_stopped")


if __name__ == "__main__":
    asyncio.run(main())
