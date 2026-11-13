"""Tests for AMQP Inbound Consumer (Onda 8)."""

from unittest.mock import AsyncMock, MagicMock
import uuid
import aio_pika
import pytest

from agency_common.amqp import AMQPMessageEnvelope
from src.services.amqp_inbound import AMQPInboundConsumer
from src.services.supervisor import EngineOperationalState, SupervisorService, set_supervisor


@pytest.fixture
def mock_channel():
    channel = MagicMock(spec=aio_pika.RobustChannel)
    channel.is_closed = False
    channel.set_qos = AsyncMock()
    channel.declare_exchange = AsyncMock()
    channel.declare_queue = AsyncMock()
    return channel


@pytest.mark.asyncio
async def test_amqp_inbound_process_clean_message():
    """Processes incoming valid AMQP envelope and triggers registered handler."""
    consumer = AMQPInboundConsumer()
    received_envelopes = []

    async def sample_handler(envelope: AMQPMessageEnvelope):
        received_envelopes.append(envelope)

    envelope = AMQPMessageEnvelope(
        from_service="guardrail-gateway",
        to_service="engine-core",
        payload={
            "from_phone": "+5511999998888",
            "text": "Ola, gostaria de um orcamento para ecommerce",
            "lead_id": "lead-123",
        },
    )

    mock_msg = MagicMock(spec=aio_pika.IncomingMessage)
    mock_msg.body = envelope.to_bytes()
    mock_msg.process = MagicMock()
    # Mock async context manager
    mock_msg.process.return_value.__aenter__ = AsyncMock()
    mock_msg.process.return_value.__aexit__ = AsyncMock()

    await consumer._process_incoming_message(mock_msg, custom_handler=sample_handler)

    assert len(received_envelopes) == 1
    assert received_envelopes[0].payload["from_phone"] == "+5511999998888"
    assert "ecommerce" in received_envelopes[0].payload["text"]


@pytest.mark.asyncio
async def test_amqp_inbound_idempotency_duplicate_skipped():
    """Duplicate message ID is skipped without re-running handler."""
    consumer = AMQPInboundConsumer()
    handler_mock = AsyncMock()

    envelope = AMQPMessageEnvelope(
        message_id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
        from_service="guardrail-gateway",
        to_service="engine-core",
        payload={"text": "First attempt"},
    )

    mock_msg = MagicMock(spec=aio_pika.IncomingMessage)
    mock_msg.body = envelope.to_bytes()
    mock_msg.process.return_value.__aenter__ = AsyncMock()
    mock_msg.process.return_value.__aexit__ = AsyncMock()

    # First delivery
    await consumer._process_incoming_message(mock_msg, custom_handler=handler_mock)
    assert handler_mock.call_count == 1

    # Second delivery of identical message_id
    await consumer._process_incoming_message(mock_msg, custom_handler=handler_mock)
    assert handler_mock.call_count == 1


@pytest.mark.asyncio
async def test_amqp_inbound_safe_during_emergency_pause():
    """Inbound message is received and processed safely during PAUSA_EMERGENCIAL without crash."""
    supervisor = SupervisorService()
    await supervisor.pause_manually("Emergency drill")
    set_supervisor(supervisor)

    consumer = AMQPInboundConsumer()
    received = []

    async def handler(env: AMQPMessageEnvelope):
        received.append(env)

    envelope = AMQPMessageEnvelope(
        from_service="guardrail-gateway",
        to_service="engine-core",
        payload={"text": "Client response while paused"},
    )

    mock_msg = MagicMock(spec=aio_pika.IncomingMessage)
    mock_msg.body = envelope.to_bytes()
    mock_msg.process.return_value.__aenter__ = AsyncMock()
    mock_msg.process.return_value.__aexit__ = AsyncMock()

    await consumer._process_incoming_message(mock_msg, custom_handler=handler)

    assert len(received) == 1
    # Cleanup supervisor singleton
    set_supervisor(None)


@pytest.mark.asyncio
async def test_amqp_inbound_lifecycle():
    """Tests consumer stop cleanly."""
    consumer = AMQPInboundConsumer()
    consumer.channel = MagicMock()
    consumer.channel.is_closed = False
    consumer.channel.close = AsyncMock()
    consumer.connection = MagicMock()
    consumer.connection.is_closed = False
    consumer.connection.close = AsyncMock()

    await consumer.stop()
    assert not consumer.is_consuming


@pytest.mark.asyncio
async def test_amqp_inbound_default_handler_and_error():
    """Default handler logs message and error bubbles up."""
    consumer = AMQPInboundConsumer()
    envelope = AMQPMessageEnvelope(
        from_service="guardrail-gateway",
        to_service="engine-core",
        payload={"from_phone": "+5511999991111", "text": "Mensagem direta"},
    )
    mock_msg = MagicMock(spec=aio_pika.IncomingMessage)
    mock_msg.body = envelope.to_bytes()
    mock_msg.process.return_value.__aenter__ = AsyncMock()
    mock_msg.process.return_value.__aexit__ = AsyncMock()

    # Default handler execution
    await consumer._process_incoming_message(mock_msg, custom_handler=None)

    # When an invalid body is sent, ValueError/ValidationError is raised
    bad_msg = MagicMock(spec=aio_pika.IncomingMessage)
    bad_msg.body = b"not-a-json"
    bad_msg.process.return_value.__aenter__ = AsyncMock()
    bad_msg.process.return_value.__aexit__ = AsyncMock(return_value=False)
    with pytest.raises(Exception):
        await consumer._process_incoming_message(bad_msg)


@pytest.mark.asyncio
async def test_amqp_inbound_connect_and_start_consuming():
    """Connect and start_consuming with mocked aio_pika."""
    from unittest.mock import patch
    from src.services.amqp_inbound import get_inbound_consumer, set_inbound_consumer

    mock_conn = MagicMock()
    mock_chan = MagicMock()
    mock_chan.is_closed = False
    mock_chan.set_qos = AsyncMock()
    mock_chan.declare_exchange = AsyncMock()
    mock_queue = MagicMock()
    mock_queue.bind = AsyncMock()
    mock_queue.consume = AsyncMock(return_value="consumer-tag-1")
    mock_chan.declare_queue = AsyncMock(return_value=mock_queue)
    mock_conn.channel = AsyncMock(return_value=mock_chan)

    with patch("aio_pika.connect_robust", AsyncMock(return_value=mock_conn)):
        consumer = AMQPInboundConsumer()
        connected = await consumer.connect(max_retries=1)
        assert connected is True

        handler = AsyncMock()
        await consumer.start_consuming(handler=handler)
        assert consumer.is_consuming is True
        mock_queue.consume.assert_called_once()

        # Stop
        consumer.queue = mock_queue
        mock_queue.cancel = AsyncMock()
        await consumer.stop()
        assert consumer.is_consuming is False

    # Singleton helpers
    inst = get_inbound_consumer()
    assert inst is not None
    set_inbound_consumer(None)


@pytest.mark.asyncio
async def test_amqp_inbound_connect_failure():
    """Connect handles connection failure with fallback."""
    from unittest.mock import patch

    with patch("aio_pika.connect_robust", AsyncMock(side_effect=RuntimeError("RabbitMQ down"))):
        consumer = AMQPInboundConsumer()
        connected = await consumer.connect(max_retries=1, initial_delay=0.01)
        assert connected is False

        with pytest.raises(RuntimeError, match="Failed to connect"):
            await consumer.start_consuming()
