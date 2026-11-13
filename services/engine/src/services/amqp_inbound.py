"""Durable AMQP Inbound Consumer for WhatsApp Ingress (Onda 8)."""

import asyncio
from collections.abc import Callable, Coroutine
import json
from typing import Any
import aio_pika
from loguru import logger

from agency_common.amqp import (
    AMQPMessageEnvelope,
    DLX_EXCHANGE_NAME,
    POISON_QUEUE_NAME,
    TOPIC_EXCHANGE_NAME,
)
from src.config import get_settings
from src.services.supervisor import EngineOperationalState, get_supervisor


INBOUND_QUEUE_NAME: str = "whatsapp.inbound"


class AMQPInboundConsumer:
    """Durable consumer for clean WhatsApp messages delivered from guardrail-gateway."""

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        queue_name: str = INBOUND_QUEUE_NAME,
        handler: Callable[[AMQPMessageEnvelope], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        settings = get_settings()
        self.rabbitmq_url = rabbitmq_url or settings.RABBITMQ_URL
        self.queue_name = queue_name
        self.handler = handler

        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.RobustChannel | None = None
        self.queue: aio_pika.RobustQueue | None = None
        self._consumer_tag: str | None = None
        self._is_consuming: bool = False
        self._processed_message_ids: set[str] = set()

    @property
    def is_consuming(self) -> bool:
        return self._is_consuming and self.channel is not None and not self.channel.is_closed

    async def connect(self, max_retries: int = 3, initial_delay: float = 1.0) -> bool:
        """Establishes robust connection and declares durable queue bound to topic exchange."""
        delay = initial_delay
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"AMQP Inbound connecting to RabbitMQ ({self.rabbitmq_url}) attempt {attempt}/{max_retries}..."
                )
                self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=10)

                # Ensure exchange and durable queue exist
                topic_exchange = await self.channel.declare_exchange(
                    TOPIC_EXCHANGE_NAME,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                self.queue = await self.channel.declare_queue(
                    self.queue_name,
                    durable=True,
                    arguments={
                        "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
                    },
                )
                await self.queue.bind(topic_exchange, routing_key="whatsapp.msg.in.*")
                logger.info(f"AMQP Inbound queue '{self.queue_name}' ready and bound.")
                return True
            except Exception as exc:
                logger.warning(f"RabbitMQ connection failed on attempt {attempt}: {exc}")
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2

        logger.warning("RabbitMQ unavailable for AMQP inbound consumer.")
        return False

    async def _process_incoming_message(
        self,
        message: aio_pika.IncomingMessage,
        custom_handler: Callable[[AMQPMessageEnvelope], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """Processes a single incoming message from the queue with idempotency and safety."""
        async with message.process(requeue=False):
            try:
                envelope = AMQPMessageEnvelope.from_bytes(message.body)
                msg_id_str = str(envelope.message_id)

                # Idempotency check: prevent duplicate processing
                if msg_id_str in self._processed_message_ids:
                    logger.warning(f"Duplicate inbound message {msg_id_str} received. Skipping.")
                    return

                # Record processed ID (kept bounded in memory)
                if len(self._processed_message_ids) > 10000:
                    self._processed_message_ids.clear()
                self._processed_message_ids.add(msg_id_str)

                # Check supervisor operational state
                supervisor = get_supervisor()
                if supervisor.state == EngineOperationalState.PAUSA_EMERGENCIAL:
                    logger.info(
                        f"Inbound message {msg_id_str} safely buffered/recorded during PAUSA_EMERGENCIAL."
                    )
                    # Message is safely acknowledged and stored; outbound responses are suppressed

                handler = custom_handler or self.handler
                if handler is not None:
                    await handler(envelope)
                else:
                    logger.info(
                        f"Inbound message {msg_id_str} processed: from={envelope.payload.get('from_phone', 'unknown')} "
                        f"text_len={len(envelope.payload.get('text', ''))}"
                    )

            except Exception as exc:
                logger.error(f"Error processing inbound AMQP message: {exc}")
                raise

    async def start_consuming(
        self,
        handler: Callable[[AMQPMessageEnvelope], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """Starts consuming incoming messages from the durable queue."""
        if not self.queue or not self.channel or self.channel.is_closed:
            connected = await self.connect()
            if not connected or not self.queue:
                raise RuntimeError("Failed to connect AMQPInboundConsumer to RabbitMQ.")

        if handler is not None:
            self.handler = handler

        async def _on_message(message: aio_pika.IncomingMessage):
            await self._process_incoming_message(message, handler)

        self._consumer_tag = await self.queue.consume(_on_message)
        self._is_consuming = True
        logger.info(f"AMQPInboundConsumer active on queue '{self.queue_name}'.")

    async def stop(self) -> None:
        """Stops consuming and cleanly closes RabbitMQ connection."""
        self._is_consuming = False
        if self.queue and self._consumer_tag:
            try:
                await self.queue.cancel(self._consumer_tag)
            except Exception:
                pass
            self._consumer_tag = None

        if self.channel and not self.channel.is_closed:
            try:
                await self.channel.close()
            except Exception:
                pass

        if self.connection and not self.connection.is_closed:
            try:
                await self.connection.close()
            except Exception:
                pass

        logger.info("AMQPInboundConsumer stopped cleanly.")


# Global singleton instance
_inbound_consumer: AMQPInboundConsumer | None = None


def get_inbound_consumer() -> AMQPInboundConsumer:
    global _inbound_consumer
    if _inbound_consumer is None:
        _inbound_consumer = AMQPInboundConsumer()
    return _inbound_consumer


def set_inbound_consumer(consumer: AMQPInboundConsumer | None) -> None:
    global _inbound_consumer
    _inbound_consumer = consumer
