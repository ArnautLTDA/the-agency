"""Persistent Task Queue Service with AMQP/RabbitMQ and QoS control (SEC-008)."""

import asyncio
import json
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import aio_pika
from loguru import logger

from src.config import get_settings


class QueueCapacityExceededError(Exception):
    """Raised when the message queue exceeds MAX_QUEUE_CAPACITY."""
    pass


class OutboundQueueFrozenError(Exception):
    """Raised when an outbound prospecting task is dispatched while outbound is frozen."""
    pass


class QueueService:
    """Manages asynchronous task enqueuing and consumption via RabbitMQ or in-memory fallback."""

    QUEUE_NAME = "agency.tasks"
    EXCHANGE_NAME = "agency.topic"

    def __init__(self, rabbitmq_url: str | None = None, max_capacity: int | None = None):
        settings = get_settings()
        self.rabbitmq_url = rabbitmq_url or settings.RABBITMQ_URL
        self.max_capacity = max_capacity or settings.MAX_QUEUE_CAPACITY
        self.prefetch_count = settings.MAX_CONCURRENT_AGENTS

        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.RobustChannel | None = None
        self.queue: aio_pika.RobustQueue | None = None
        self._consumer_tag: str | None = None
        self._connected = False
        self._reconnecting = False
        self._in_memory_queue: asyncio.Queue | None = None
        self._in_memory_consumer_task: asyncio.Task | None = None
        self._outbound_frozen: bool = False

    @property
    def is_outbound_frozen(self) -> bool:
        """Returns True if outbound prospecting queues are frozen by the supervisor."""
        return self._outbound_frozen

    def freeze_outbound(self) -> None:
        """Freezes outbound prospecting queues."""
        self._outbound_frozen = True

    def unfreeze_outbound(self) -> None:
        """Resumes outbound prospecting queues."""
        self._outbound_frozen = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.connection is not None and not self.connection.is_closed

    async def connect(self, max_retries: int = 3, initial_delay: float = 1.0) -> bool:
        """Connects to RabbitMQ with robust reconnection and exponential backoff."""
        delay = initial_delay
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Connecting to RabbitMQ ({self.rabbitmq_url}) attempt {attempt}/{max_retries}...")
                self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=self.prefetch_count)

                # Declare durable queue
                self.queue = await self.channel.declare_queue(
                    self.QUEUE_NAME,
                    durable=True,
                )
                self._connected = True
                logger.info(f"Connected to RabbitMQ. Queue '{self.QUEUE_NAME}' declared (prefetch={self.prefetch_count}).")
                return True
            except Exception as exc:
                logger.warning(f"RabbitMQ connection failed on attempt {attempt}: {exc}")
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2

        logger.warning("RabbitMQ unavailable. Initializing local in-memory queue fallback.")
        self._in_memory_queue = asyncio.Queue(maxsize=self.max_capacity)
        self._connected = False
        return False

    async def get_queue_size(self) -> int:
        """Returns the number of messages waiting in the queue."""
        if self.is_connected and self.queue is not None:
            try:
                # Re-declaring queue passive retrieves current message_count
                decl = await self.channel.declare_queue(self.QUEUE_NAME, passive=True)
                return decl.declaration_result.message_count
            except Exception:
                return 0
        if self._in_memory_queue is not None:
            return self._in_memory_queue.qsize()
        return 0

    async def publish_task(
        self,
        run_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> bool:
        """Publishes a task payload. Raises QueueCapacityExceededError if over capacity (SEC-008)."""
        if self._outbound_frozen and payload.get("is_outbound_prospecting", False):
            logger.warning(f"Rejecting outbound prospecting task {run_id}: Outbound queues frozen.")
            raise OutboundQueueFrozenError("Outbound prospecting is frozen due to emergency pause.")

        current_size = await self.get_queue_size()
        if current_size >= self.max_capacity:
            logger.error(f"Task queue capacity reached ({current_size}/{self.max_capacity}). Rejecting task {run_id}.")
            raise QueueCapacityExceededError(
                f"Queue capacity exceeded ({current_size}/{self.max_capacity}). Service Unavailable."
            )

        task_data = {"run_id": str(run_id), **payload}
        encoded = json.dumps(task_data).encode("utf-8")

        if self.is_connected and self.channel is not None:
            message = aio_pika.Message(
                body=encoded,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                correlation_id=str(run_id),
            )
            await self.channel.default_exchange.publish(
                message,
                routing_key=self.QUEUE_NAME,
            )
            logger.info(f"Task {run_id} enqueued to RabbitMQ queue '{self.QUEUE_NAME}'.")
            return True

        # Fallback to in-memory queue
        if self._in_memory_queue is None:
            self._in_memory_queue = asyncio.Queue(maxsize=self.max_capacity)

        try:
            self._in_memory_queue.put_nowait(task_data)
            logger.info(f"Task {run_id} enqueued to local in-memory fallback queue.")
            return True
        except asyncio.QueueFull:
            raise QueueCapacityExceededError("In-memory queue is full.")

    async def start_consumer(
        self,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ):
        """Starts consuming tasks with QoS prefetch concurrency control."""
        if self.is_connected and self.queue is not None:
            async def on_message(message: aio_pika.IncomingMessage):
                async with message.process():
                    try:
                        data = json.loads(message.body.decode("utf-8"))
                        await handler(data)
                    except Exception as exc:
                        logger.error(f"Consumer task processing failed: {exc}")

            self._consumer_tag = await self.queue.consume(on_message)
            logger.info(f"Consumer active on queue '{self.QUEUE_NAME}' with prefetch={self.prefetch_count}.")
        elif self._in_memory_queue is not None:
            # Consume from in-memory queue with semaphore
            semaphore = asyncio.Semaphore(self.prefetch_count)

            async def in_memory_worker():
                while True:
                    task_data = await self._in_memory_queue.get()
                    asyncio.create_task(self._process_in_memory_slot(task_data, handler, semaphore))

            self._in_memory_consumer_task = asyncio.create_task(in_memory_worker())
            logger.info(f"In-memory worker active with concurrency limit {self.prefetch_count}.")

    async def _process_in_memory_slot(
        self,
        task_data: dict[str, Any],
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
        semaphore: asyncio.Semaphore,
    ):
        async with semaphore:
            try:
                await handler(task_data)
            except Exception as exc:
                logger.error(f"In-memory worker error: {exc}")
            finally:
                if self._in_memory_queue is not None:
                    self._in_memory_queue.task_done()

    async def close(self):
        """Closes connections and consumer tasks cleanly."""
        if self._in_memory_consumer_task is not None:
            self._in_memory_consumer_task.cancel()
        if self.connection is not None and not self.connection.is_closed:
            await self.connection.close()
        self._connected = False
        logger.info("Queue service shut down cleanly.")


# Singleton queue service instance
_queue_service: QueueService | None = None


def get_queue_service() -> QueueService:
    global _queue_service
    if _queue_service is None:
        _queue_service = QueueService()
    return _queue_service
