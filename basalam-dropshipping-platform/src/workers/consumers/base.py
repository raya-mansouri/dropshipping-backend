"""
DLQ-Aware Kafka Consumer Base Class
====================================
Provides retry-before-DLQ routing for all Kafka consumers.

Subclasses must implement:
    - topic: str (class attribute)
    - group_id: str (class attribute)
    - process_message(message) -> None

Lifecycle managed by base class:
    - start() -> creates consumer + producer
    - consume() -> main loop with retry/DLQ routing
    - stop() -> graceful shutdown
"""

import asyncio
import json
import traceback
import structlog
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import CommitFailedError, ConsumerStoppedError

logger = structlog.get_logger("workers.base_consumer")


@dataclass(frozen=True)
class DLQConfig:
    """Per-consumer DLQ settings. Immutable after construction."""

    max_retries: int = 3
    retry_backoff_ms: tuple[int, ...] = (1000, 5000, 30000)
    dlq_topic_suffix: str = ".DLQ"
    retry_topic_suffix: str = ".retry"
    processing_timeout_seconds: int = 300

    def __post_init__(self):
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        if not self.retry_backoff_ms:
            raise ValueError("retry_backoff_ms must be non-empty")
        if any(b < 0 for b in self.retry_backoff_ms):
            raise ValueError("retry_backoff_ms values must be non-negative")
        if self.processing_timeout_seconds <= 0:
            raise ValueError(
                f"processing_timeout_seconds must be positive, "
                f"got {self.processing_timeout_seconds}"
            )
        if not self.dlq_topic_suffix:
            raise ValueError("dlq_topic_suffix must be non-empty")
        if not self.retry_topic_suffix:
            raise ValueError("retry_topic_suffix must be non-empty")


class DLQAwareConsumer:
    """
    Base class providing retry-before-DLQ for aiokafka consumers.

    Subclasses define `topic`, `group_id` as class attributes and
    implement `process_message()`.
    """

    topic: str = ""
    group_id: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "topic", ""):
            raise TypeError(
                f"{cls.__name__} must set a non-empty 'topic' class attribute"
            )
        if not getattr(cls, "group_id", ""):
            raise TypeError(
                f"{cls.__name__} must set a non-empty 'group_id' class attribute"
            )

    def __init__(
        self,
        bootstrap_servers: str,
        dlq_config: Optional[DLQConfig] = None,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.dlq_config = dlq_config or DLQConfig()
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self._shutdown = asyncio.Event()

    @abstractmethod
    async def process_message(self, message) -> None:
        """Business logic. Raise on failure — base class handles routing."""
        ...

    # ── Header helpers ──

    @staticmethod
    def _get_header(
        headers: Optional[List[Tuple[str, bytes]]], key: str
    ) -> Optional[str]:
        if not headers:
            return None
        for k, v in headers:
            if k == key or k == key.encode():
                return (
                    v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v
                )
        return None

    @staticmethod
    def _set_header(
        headers: List[Tuple[str, bytes]], key: str, value: str
    ) -> List[Tuple[str, bytes]]:
        filtered = [(k, v) for k, v in headers if k != key and k != key.encode()]
        filtered.append((key, value.encode("utf-8")))
        return filtered

    def _get_retry_count(self, headers: Optional[List[Tuple[str, bytes]]]) -> int:
        val = self._get_header(headers, "retry_count")
        if val:
            try:
                return int(val)
            except (ValueError, TypeError):
                logger.warning("malformed_retry_count_header", value=val)
                return 0
        return 0

    # ── Error enrichment ──

    def _build_error_headers(
        self, message, error: Exception, retry_count: int
    ) -> List[Tuple[str, bytes]]:
        headers = list(message.headers or [])
        enrichment = {
            "retry_count": str(retry_count),
            "original_topic": message.topic,
            "original_partition": str(message.partition),
            "original_offset": str(message.offset),
            "error_class": type(error).__name__,
            "error_message": str(error)[:4096],
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "stacktrace": traceback.format_exc()[:4096],
        }
        for k, v in enrichment.items():
            headers = self._set_header(headers, k, v)
        return headers

    # ── Producer ──

    async def _ensure_producer(self) -> AIOKafkaProducer:
        if self.producer is None:
            producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                enable_idempotence=True,
            )
            try:
                await producer.start()
            except Exception:
                self.producer = None
                raise
            self.producer = producer
        return self.producer

    # ── Routing ──

    async def _send_to_retry(self, message, error: Exception, retry_count: int) -> None:
        producer = await self._ensure_producer()
        next_retry = retry_count + 1
        headers = self._build_error_headers(message, error, next_retry)
        retry_topic = f"{self.topic}{self.dlq_config.retry_topic_suffix}"

        await producer.send_and_wait(
            retry_topic, value=message.value, key=message.key, headers=headers
        )
        backoff = self.dlq_config.retry_backoff_ms[
            min(retry_count, len(self.dlq_config.retry_backoff_ms) - 1)
        ]
        logger.warning(
            "message_sent_to_retry",
            retry_topic=retry_topic,
            attempt=next_retry,
            max_retries=self.dlq_config.max_retries,
            backoff_ms=backoff,
            offset=message.offset,
            error=str(error)[:200],
        )

    async def _send_to_dlq(self, message, error: Exception, retry_count: int) -> None:
        producer = await self._ensure_producer()
        headers = self._build_error_headers(message, error, retry_count)
        dlq_topic = f"{self.topic}{self.dlq_config.dlq_topic_suffix}"

        await producer.send_and_wait(
            dlq_topic, value=message.value, key=message.key, headers=headers
        )
        logger.error(
            "message_sent_to_dlq",
            dlq_topic=dlq_topic,
            retry_count=retry_count,
            offset=message.offset,
            error=str(error)[:200],
        )

    async def _route_failure(self, message, error: Exception, retry_count: int) -> None:
        if retry_count < self.dlq_config.max_retries:
            await self._send_to_retry(message, error, retry_count)
        else:
            await self._send_to_dlq(message, error, retry_count)
        # Commit after successful routing to prevent poison pill loop
        await self.consumer.commit()

    # ── Lifecycle ──

    async def start(self) -> None:
        self.consumer = AIOKafkaConsumer(
            self.topic,
            f"{self.topic}{self.dlq_config.retry_topic_suffix}",
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            max_poll_interval_ms=self.dlq_config.processing_timeout_seconds * 1000,
        )
        await self.consumer.start()
        logger.info(
            "consumer_started",
            topic=self.topic,
            group_id=self.group_id,
            max_retries=self.dlq_config.max_retries,
        )

    async def stop(self) -> None:
        self._shutdown.set()
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        logger.info("consumer_stopped", topic=self.topic)

    async def consume(self) -> None:
        if self.consumer is None:
            raise RuntimeError("Consumer not started. Call start() first.")
        try:
            async for message in self.consumer:
                if self._shutdown.is_set():
                    break

                retry_count = self._get_retry_count(message.headers)

                # Apply backoff delay for retry messages
                if retry_count > 0:
                    backoff = self.dlq_config.retry_backoff_ms[
                        min(retry_count - 1, len(self.dlq_config.retry_backoff_ms) - 1)
                    ]
                    await asyncio.sleep(backoff / 1000)

                try:
                    await asyncio.wait_for(
                        self.process_message(message),
                        timeout=self.dlq_config.processing_timeout_seconds,
                    )
                    await self.consumer.commit()
                except asyncio.TimeoutError:
                    timeout_msg = (
                        f"Processing timed out after "
                        f"{self.dlq_config.processing_timeout_seconds}s"
                    )
                    try:
                        await self._route_failure(
                            message, TimeoutError(timeout_msg), retry_count
                        )
                    except Exception as route_err:
                        logger.critical(
                            "dlq_routing_failed_re_raising",
                            original_error=timeout_msg,
                            routing_error=str(route_err)[:200],
                            offset=message.offset,
                            topic=message.topic,
                        )
                        raise
                except CommitFailedError as e:
                    # Transient rebalance — must be before generic Exception
                    # since CommitFailedError is a subclass of Exception.
                    logger.warning(
                        "commit_failed_rebalance_skipping",
                        error=str(e),
                        offset=message.offset,
                    )
                except Exception as e:
                    try:
                        await self._route_failure(message, e, retry_count)
                    except Exception as route_err:
                        logger.critical(
                            "dlq_routing_failed_re_raising",
                            original_error=str(e)[:200],
                            routing_error=str(route_err)[:200],
                            offset=message.offset,
                            topic=message.topic,
                        )
                        raise

        except ConsumerStoppedError:
            logger.info("consumer_stopped_gracefully")
        except CommitFailedError as e:
            logger.error("commit_failed_outside_loop", error=str(e))
        finally:
            await self.stop()
