import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert

from .base import DomainEvent

logger = logging.getLogger(__name__)


class TopicRouter:
    """Routes events to appropriate Kafka topics based on event type."""

    DEFAULT_TOPIC = "events.default"

    def __init__(self):
        self._routes: Dict[str, str] = {}

    def register_route(self, event_type: str, topic: str) -> None:
        """Register a route for an event type to a specific topic."""
        self._routes[event_type] = topic

    def get_topic(self, event: DomainEvent) -> str:
        """Get the topic for an event based on its type."""
        return self._routes.get(event.event_type, self.DEFAULT_TOPIC)

    def register_default_routes(self) -> None:
        """Register default topic routes for common event types."""
        self.register_route("inventory.reserved", "inventory.updated")
        self.register_route("inventory.released", "inventory.updated")
        self.register_route("inventory.consumed", "inventory.updated")
        self.register_route("order.created", "order.created")
        self.register_route("order.updated", "order.created")
        self.register_route("payment.held", "payment.updated")
        self.register_route("payment.released", "payment.updated")
        self.register_route("payment.refunded", "payment.updated")
        self.register_route("product.created", "product.updated")
        self.register_route("product.updated", "product.updated")
        self.register_route("product.deleted", "product.updated")


class EventStore:
    """Stores events in database for replay capability."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_event(
        self,
        event: DomainEvent,
        topic: str,
        partition: int = 0,
        offset: Optional[int] = None,
    ) -> None:
        """Save event to database for persistence."""
        from src.domains.webhooks.models import WebhookEventLog

        record = WebhookEventLog(
            platform_id="event_store",
            event_id=str(event.event_id),
            payload_hash="",
            processed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            metadata=json.dumps(
                {
                    "event_type": event.event_type,
                    "topic": topic,
                    "partition": partition,
                    "offset": offset,
                    "occurred_at": event.occurred_at.isoformat(),
                }
            ),
        )
        self.session.add(record)
        await self.session.flush()

    async def get_events(
        self,
        event_type: Optional[str] = None,
        from_offset: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve events from the event store."""
        from src.domains.webhooks.models import WebhookEventLog

        stmt = select(WebhookEventLog).order_by(WebhookEventLog.created_at).limit(limit)

        result = await self.session.execute(stmt)
        records = result.scalars().all()

        events = []
        for record in records:
            if record.metadata:
                metadata = json.loads(record.metadata)
                if event_type is None or metadata.get("event_type") == event_type:
                    events.append(
                        {
                            "event_id": record.event_id,
                            "event_type": metadata.get("event_type"),
                            "occurred_at": metadata.get("occurred_at"),
                            "topic": metadata.get("topic"),
                            "partition": metadata.get("partition"),
                            "offset": metadata.get("offset"),
                        }
                    )
        return events


class EventPublisher:
    """Event publisher with topic routing and event persistence."""

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        db_session: Optional[AsyncSession] = None,
    ):
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.producer: AIOKafkaProducer = None
        self.db_session = db_session
        self.router = TopicRouter()
        self.router.register_default_routes()
        self.event_store: Optional[EventStore] = None

    async def _get_producer(self) -> AIOKafkaProducer:
        if self.producer is None:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self.producer.start()
        return self.producer

    async def _get_event_store(self) -> EventStore:
        if self.event_store is None and self.db_session:
            self.event_store = EventStore(self.db_session)
        return self.event_store

    def register_topic_route(self, event_type: str, topic: str) -> None:
        """Register a custom topic route for an event type."""
        self.router.register_route(event_type, topic)

    async def publish(
        self,
        topic: str,
        event: DomainEvent,
        route_by_type: bool = True,
    ) -> Dict[str, Any]:
        """
        Publish an event to a topic.

        Args:
            topic: The Kafka topic to publish to (used if route_by_type is False)
            event: The domain event to publish
            route_by_type: If True, use topic router to determine topic from event type

        Returns:
            Dictionary with partition and offset
        """
        if route_by_type:
            topic = self.router.get_topic(event)

        producer = await self._get_producer()

        future = await producer.send_and_wait(topic, event.to_dict())
        result = {
            "topic": future.topic,
            "partition": future.partition,
            "offset": future.offset,
        }

        event_store = await self._get_event_store()
        if event_store:
            try:
                await event_store.save_event(
                    event,
                    topic=result["topic"],
                    partition=result["partition"],
                    offset=result["offset"],
                )
            except Exception as e:
                logger.warning(f"Failed to save event to event store: {e}")

        logger.debug(f"Published event {event.event_id} to {topic}")
        return result

    async def publish_batch(
        self,
        topic: str,
        events: List[DomainEvent],
        route_by_type: bool = True,
    ) -> List[Dict[str, Any]]:
        """Publish multiple events to topics."""
        results = []
        for event in events:
            result = await self.publish(topic, event, route_by_type=route_by_type)
            results.append(result)
        return results

    async def close(self):
        if self.producer:
            await self.producer.stop()
            self.producer = None
