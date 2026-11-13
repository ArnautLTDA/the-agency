"""Standard AMQP Message Envelope, Topology and Exceptions for The Agency."""

from datetime import datetime, timezone
import json
from typing import Any
import uuid

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue
from pydantic import BaseModel, Field, field_validator


MAX_PAYLOAD_BYTES: int = 65536  # 64 KB

TOPIC_EXCHANGE_NAME: str = "agency.topic"
DLX_EXCHANGE_NAME: str = "agency.dlx"
POISON_QUEUE_NAME: str = "agency.poison_messages"
POISON_QUEUE_TTL_MS: int = 604800000  # 7 days in milliseconds

OFFICIAL_SERVICES: set[str] = {
    "engine-core",
    "whatsapp-gateway",
    "payment-gateway",
    "guardrail-gateway",
    "telegram-gateway",
    "osint-scraper-gateway",
    "workspace-sandbox-service",
    "git-vcs-gateway",
    "deploy-cloud-gateway",
    "knowledge-memory-gateway",
    "browser-gateway",
    "security-audit-gateway",
}

QUEUE_BINDINGS: dict[str, str] = {
    "whatsapp.raw": "whatsapp.raw.*",
    "whatsapp.inbound": "whatsapp.msg.in.*",
    "whatsapp.outbound": "whatsapp.msg.out.*",
    "telegram.alerts": "telegram.alert.*",
    "telegram.approvals": "telegram.approval.*",
    "payment.webhooks": "payment.event.*",
}


class PayloadTooLargeError(ValueError):
    """Raised when an AMQP message payload exceeds 64 KB."""


class AMQPMessageEnvelope(BaseModel):
    """Standard typed AMQP message envelope with strict size cap and correlation."""

    message_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_service: str
    to_service: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("from_service")
    @classmethod
    def validate_from_service(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("from_service must not be empty")
        return value.strip()

    @field_validator("to_service")
    @classmethod
    def validate_to_service(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("to_service must not be empty")
        return value.strip()

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(value, default=str).encode("utf-8")
        if len(serialized) > MAX_PAYLOAD_BYTES:
            raise PayloadTooLargeError(
                f"Payload size of {len(serialized)} bytes exceeds maximum allowed limit of {MAX_PAYLOAD_BYTES} bytes."
            )
        return value

    def __init__(self, **data: Any) -> None:
        payload = data.get("payload")
        if payload is not None:
            serialized = json.dumps(payload, default=str).encode("utf-8")
            if len(serialized) > MAX_PAYLOAD_BYTES:
                raise PayloadTooLargeError(
                    f"Payload size of {len(serialized)} bytes exceeds maximum allowed limit of {MAX_PAYLOAD_BYTES} bytes."
                )
        super().__init__(**data)

    def to_json(self) -> str:
        """Serializes envelope to JSON string."""
        return self.model_dump_json()

    def to_bytes(self) -> bytes:
        """Serializes envelope to UTF-8 bytes."""
        return self.to_json().encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "AMQPMessageEnvelope":
        """Deserializes envelope from UTF-8 bytes."""
        return cls.model_validate_json(data.decode("utf-8"))


async def setup_amqp_topology(channel: AbstractChannel) -> dict[str, Any]:
    """Declares and binds the full Agency topic exchange, DLX, queues and bindings."""
    # 1. Declare DLX (Dead Letter Exchange)
    dlx_exchange: AbstractExchange = await channel.declare_exchange(
        DLX_EXCHANGE_NAME,
        aio_pika.ExchangeType.FANOUT,
        durable=True,
    )

    # 2. Declare Poison Messages Queue on DLX with 7-day TTL
    poison_queue: AbstractQueue = await channel.declare_queue(
        POISON_QUEUE_NAME,
        durable=True,
        arguments={
            "x-message-ttl": POISON_QUEUE_TTL_MS,
        },
    )
    await poison_queue.bind(dlx_exchange)

    # 3. Declare Main Topic Exchange
    topic_exchange: AbstractExchange = await channel.declare_exchange(
        TOPIC_EXCHANGE_NAME,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    # 4. Declare standard domain queues with DLX routing arguments
    declared_queues: dict[str, AbstractQueue] = {}
    for queue_name, binding_key in QUEUE_BINDINGS.items():
        queue: AbstractQueue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
            },
        )
        await queue.bind(topic_exchange, routing_key=binding_key)
        declared_queues[queue_name] = queue

    return {
        "topic_exchange": topic_exchange,
        "dlx_exchange": dlx_exchange,
        "poison_queue": poison_queue,
        "queues": declared_queues,
    }
