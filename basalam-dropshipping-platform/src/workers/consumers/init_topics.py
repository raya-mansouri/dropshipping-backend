#!/usr/bin/env python3
import asyncio
import json
import structlog
import logging

from aiokafka import AIOKafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

from src.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

KAFKA_BOOTSTRAP_SERVERS = get_settings().kafka_bootstrap_servers

SOURCE_TOPICS = [
    "webhook.received",
    "product.updated",
    "inventory.updated",
    "order.created",
    "payment.updated",
    "sync.requested",
]

# Generate retry + DLQ topics for each source topic
TOPICS = (
    SOURCE_TOPICS
    + [f"{t}.retry" for t in SOURCE_TOPICS]
    + [f"{t}.DLQ" for t in SOURCE_TOPICS]
)

NUM_PARTITIONS = 3
REPLICATION_FACTOR = 1
DLQ_RETENTION_MS = 2592000000  # 30 days


async def create_topics():
    """
    Create Kafka topics with explicit partition/replication/retention config.

    Falls back to dummy-message auto-creation if the admin client is
    unavailable (e.g. running outside the Docker network).
    """
    try:
        await _create_via_admin()
    except Exception as e:
        logger.error(
            "admin_client_unavailable_cannot_control_topic_config",
            error=str(e),
            note="DLQ retention, partitions, and replication will use broker defaults",
        )
        await _create_via_dummy_messages()


async def _create_via_admin():
    """Create topics using the Kafka admin client with explicit configuration."""
    loop = asyncio.get_running_loop()
    admin = await loop.run_in_executor(
        None,
        lambda: KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS),
    )

    try:
        existing = set(await loop.run_in_executor(None, admin.list_topics))
        new_topics = []

        for topic_name in TOPICS:
            if topic_name in existing:
                logger.info("topic_already_exists", topic=topic_name)
                continue

            retention = DLQ_RETENTION_MS if topic_name.endswith(".DLQ") else None
            topic_configs = {}
            if retention:
                topic_configs["retention.ms"] = str(retention)

            new_topics.append(
                NewTopic(
                    name=topic_name,
                    num_partitions=NUM_PARTITIONS,
                    replication_factor=REPLICATION_FACTOR,
                    topic_configs=topic_configs,
                )
            )

        if new_topics:
            try:
                await loop.run_in_executor(None, admin.create_topics, new_topics)
                for t in new_topics:
                    logger.info(
                        "topic_created",
                        topic=t.name,
                        partitions=t.num_partitions,
                        replication=t.replication_factor,
                    )
            except TopicAlreadyExistsError:
                logger.warning(
                    "some_topics_already_exist",
                    attempted_topics=[t.name for t in new_topics],
                )
        else:
            logger.info("all_topics_already_exist", count=len(TOPICS))
    finally:
        await loop.run_in_executor(None, admin.close)


async def _create_via_dummy_messages():
    """Fallback: send a dummy message to trigger auto-creation.

    Requires auto.create.topics.enable=true on the broker.
    Does NOT control partitions, replication, or retention.
    """
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()

    try:
        for topic_name in TOPICS:
            try:
                await producer.send_and_wait(
                    topic_name,
                    value={"__init__": True, "topic": topic_name},
                )
                logger.info("topic_initialized_via_dummy", topic=topic_name)
            except Exception as e:
                logger.error("topic_init_failed", topic=topic_name, error=str(e))

        logger.info(
            "topic_initialization_complete_fallback",
            count=len(TOPICS),
            note="broker_defaults_used",
        )
    finally:
        await producer.stop()


def main():
    asyncio.run(create_topics())


if __name__ == "__main__":
    main()
