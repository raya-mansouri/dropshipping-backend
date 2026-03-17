#!/usr/bin/env python3
import asyncio
import os
import logging
from aiokafka import AIOKafkaAdminClient
from aiokafka.admin import NewTopic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

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
                logger.info(f"Topic '{topic}' will be created")
            else:
                logger.info(f"Topic '{topic}' already exists")

        if topics_to_create:
            await admin_client.create_topics(topics_to_create)
            logger.info(f"Successfully created {len(topics_to_create)} topics")
        else:
            logger.info("All topics already exist")

    except Exception as e:
        logger.error(f"Error creating topics: {e}")
        raise
    finally:
        if admin_client:
            await admin_client.stop()


def main():
    asyncio.run(create_topics())


if __name__ == "__main__":
    main()
