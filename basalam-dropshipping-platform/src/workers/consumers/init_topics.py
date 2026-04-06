#!/usr/bin/env python3
import asyncio
import structlog
from aiokafka import AIOKafkaAdminClient
from aiokafka.admin import NewTopic

from src.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

KAFKA_BOOTSTRAP_SERVERS = get_settings().kafka_bootstrap_servers

TOPICS = [
    "webhook.received",
    "product.updated",
    "inventory.updated",
    "order.created",
    "payment.updated",
]

NUM_PARTITIONS = 3
REPLICATION_FACTOR = 1


async def create_topics():
    admin_client = None
    try:
        admin_client = AIOKafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            client_id="topic-initializer",
        )
        await admin_client.start()

        existing_topics = await admin_client.list_topics()
        topics_to_create = []

        for topic in TOPICS:
            if topic not in existing_topics:
                topics_to_create.append(
                    NewTopic(
                        name=topic,
                        num_partitions=NUM_PARTITIONS,
                        replication_factor=REPLICATION_FACTOR,
                    )
                )
                logger.info("topic_will_be_created", topic=topic)
            else:
                logger.info("topic_already_exists", topic=topic)

        if topics_to_create:
            await admin_client.create_topics(topics_to_create)
            logger.info("successfully_created_topics", count=str(len(topics_to_create)))
        else:
            logger.info("All topics already exist")

    except Exception as e:
        logger.error("error_creating_topics", error=str(e))
        raise
    finally:
        if admin_client:
            await admin_client.stop()


def main():
    asyncio.run(create_topics())


if __name__ == "__main__":
    main()
