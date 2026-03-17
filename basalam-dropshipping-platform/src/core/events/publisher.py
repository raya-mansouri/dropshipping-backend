import json
from typing import List
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from .base import DomainEvent


class EventPublisher:
    def __init__(self, kafka_bootstrap_servers: str):
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.producer: AIOKafkaProducer = None

    async def _get_producer(self) -> AIOKafkaProducer:
        if self.producer is None:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self.producer.start()
        return self.producer

    async def publish(self, topic: str, event: DomainEvent):
        producer = await self._get_producer()
        await producer.send_and_wait(topic, event.to_dict())

    async def publish_batch(self, topic: str, events: List[DomainEvent]):
        producer = await self._get_producer()
        for event in events:
            await producer.send_and_wait(topic, event.to_dict())

    async def close(self):
        if self.producer:
            await self.producer.stop()
            self.producer = None
