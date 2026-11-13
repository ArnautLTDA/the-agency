"""Unit tests for Agency AMQP contracts, topology and envelope validation (TC-171, TC-172, TC-173)."""

from datetime import datetime
import json
from unittest.mock import AsyncMock, MagicMock
import uuid

import aio_pika
import pytest

from agency_common.amqp import (
    AMQPMessageEnvelope,
    DLX_EXCHANGE_NAME,
    MAX_PAYLOAD_BYTES,
    POISON_QUEUE_NAME,
    POISON_QUEUE_TTL_MS,
    TOPIC_EXCHANGE_NAME,
    PayloadTooLargeError,
    setup_amqp_topology,
)


def test_envelope_creation_and_defaults():
    """Verifies that AMQPMessageEnvelope generates UUIDs, timestamps, and default correlation."""
    envelope = AMQPMessageEnvelope(
        from_service="whatsapp-gateway",
        to_service="guardrail-gateway",
        payload={"text": "hello world"},
    )
    assert isinstance(envelope.message_id, uuid.UUID)
    assert isinstance(envelope.correlation_id, str)
    assert envelope.from_service == "whatsapp-gateway"
    assert envelope.to_service == "guardrail-gateway"
    assert isinstance(envelope.timestamp, datetime)
    assert envelope.payload == {"text": "hello world"}


def test_envelope_serialization_and_deserialization():
    """Verifies round-trip serialization and correlation_id preservation (TC-173)."""
    corr_id = "corr-" + str(uuid.uuid4())
    original = AMQPMessageEnvelope(
        correlation_id=corr_id,
        from_service="engine-core",
        to_service="payment-gateway",
        payload={"txid": "pix-12345", "amount_cents": 50000},
    )

    data_bytes = original.to_bytes()
    assert isinstance(data_bytes, bytes)

    recovered = AMQPMessageEnvelope.from_bytes(data_bytes)
    assert recovered.message_id == original.message_id
    assert recovered.correlation_id == corr_id
    assert recovered.from_service == "engine-core"
    assert recovered.to_service == "payment-gateway"
    assert recovered.payload == {"txid": "pix-12345", "amount_cents": 50000}


def test_envelope_payload_within_limit_passes():
    """Verifies payloads under 64 KB are accepted."""
    small_data = {"key": "x" * 1000}
    envelope = AMQPMessageEnvelope(
        from_service="test-service",
        to_service="test-dest",
        payload=small_data,
    )
    assert envelope.payload == small_data


def test_envelope_payload_exceeding_limit_fails():
    """Verifies payload exceeding 64 KB strictly raises PayloadTooLargeError (TC-172)."""
    oversized_data = {"data": "x" * (MAX_PAYLOAD_BYTES + 100)}
    with pytest.raises(PayloadTooLargeError) as exc_info:
        AMQPMessageEnvelope(
            from_service="test-service",
            to_service="test-dest",
            payload=oversized_data,
        )
    assert "exceeds maximum allowed limit of 65536 bytes" in str(exc_info.value)

    with pytest.raises(Exception):
        AMQPMessageEnvelope.model_validate({
            "from_service": "test-service",
            "to_service": "test-dest",
            "payload": oversized_data,
        })


def test_envelope_empty_service_names_fail():
    """Verifies from_service and to_service cannot be blank."""
    with pytest.raises(ValueError, match="from_service must not be empty"):
        AMQPMessageEnvelope(from_service="", to_service="dest", payload={})

    with pytest.raises(ValueError, match="to_service must not be empty"):
        AMQPMessageEnvelope(from_service="src", to_service="   ", payload={})


@pytest.mark.asyncio
async def test_setup_amqp_topology_declares_exchanges_and_dlx():
    """Verifies AMQP topology setup declares DLX, poison queue, and binds domain queues (TC-171)."""
    channel = AsyncMock()
    mock_dlx = MagicMock()
    mock_topic = MagicMock()
    mock_poison_queue = AsyncMock()
    mock_domain_queue = AsyncMock()

    # declare_exchange mock: returns dlx first, topic second
    channel.declare_exchange.side_effect = [mock_dlx, mock_topic]
    # declare_queue mock: returns poison queue first, then domain queues
    channel.declare_queue.side_effect = [mock_poison_queue] + [AsyncMock() for _ in range(6)]

    topology = await setup_amqp_topology(channel)

    assert topology["dlx_exchange"] == mock_dlx
    assert topology["topic_exchange"] == mock_topic
    assert topology["poison_queue"] == mock_poison_queue
    assert len(topology["queues"]) == 6

    # Verify DLX declared as fanout, durable
    channel.declare_exchange.assert_any_call(
        DLX_EXCHANGE_NAME,
        aio_pika.ExchangeType.FANOUT,
        durable=True,
    )

    # Verify Topic declared as topic, durable
    channel.declare_exchange.assert_any_call(
        TOPIC_EXCHANGE_NAME,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    # Verify poison queue declared with 7-day TTL
    channel.declare_queue.assert_any_call(
        POISON_QUEUE_NAME,
        durable=True,
        arguments={"x-message-ttl": POISON_QUEUE_TTL_MS},
    )
