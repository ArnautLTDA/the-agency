"""Tests for RabbitMQ Queue, Concurrency QoS, Backpressure and SSE Framing Sanitization (TC-055 to TC-058, TC-071)."""

import asyncio
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.sse import SSEBroker, SSEEvent
from src.config import get_settings
from src.main import create_app
from src.models.database import create_db_and_tables, get_async_engine, init_db
from src.services.queue import QueueCapacityExceededError, QueueService, get_queue_service


@pytest_asyncio.fixture
async def app_instance():
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_queue.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        init_db(db_url)
        app = create_app(db_url=db_url)
        yield app
        await engine.dispose()


@pytest.mark.asyncio
async def test_tc055_rabbitmq_task_enqueue(app_instance):
    """TC-055 / SEC-008: POST /api/v1/agent/run publishes task to queue and responds 202 Accepted with status queued."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        with patch("src.runner.agent_runner.AgentRunner.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Success"
            payload = {
                "agent_id": "homologation_agent",
                "task": "Test RabbitMQ queueing",
                "workspace_slug": "default",
            }
            res = await client.post("/api/v1/agent/run", json=payload)
            assert res.status_code == 202
            data = res.json()
            assert data["status"] == "queued"
            assert "run_id" in data
            assert "/api/v1/events/stream" in data["stream_url"]


@pytest.mark.asyncio
async def test_tc056_consumer_qos_prefetch_5():
    """TC-056 / SEC-008: Consumer sets QoS prefetch_count=5 enforcing max concurrent tasks."""
    queue = QueueService(rabbitmq_url="amqp://fake:fake@localhost:5672/", max_capacity=100)

    # Mock aio_pika channel and queue
    mock_channel = AsyncMock()
    mock_queue = AsyncMock()
    mock_connection = AsyncMock()
    mock_connection.is_closed = False
    mock_connection.channel.return_value = mock_channel
    mock_channel.declare_queue.return_value = mock_queue

    with patch("aio_pika.connect_robust", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_connection
        connected = await queue.connect()
        assert connected is True
        assert mock_channel.set_qos.called
        assert mock_channel.set_qos.call_args.kwargs["prefetch_count"] == 5

        # Test start_consumer registers with queue
        mock_handler = AsyncMock()
        await queue.start_consumer(mock_handler)
        assert mock_queue.consume.called


@pytest.mark.asyncio
async def test_tc057_rabbitmq_disconnect_reconnect_resilience():
    """TC-057 / SEC-008: Connection retry with exponential backoff survives transient failures."""
    queue = QueueService(rabbitmq_url="amqp://fake:fake@localhost:5672/")

    call_count = 0

    async def mock_connect_robust(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Broker temporarily offline")
        mock_conn = AsyncMock()
        mock_conn.is_closed = False
        mock_chan = AsyncMock()
        mock_conn.channel.return_value = mock_chan
        return mock_conn

    with patch("aio_pika.connect_robust", side_effect=mock_connect_robust):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            connected = await queue.connect(max_retries=3, initial_delay=0.1)
            assert connected is True
            assert call_count == 3
            # Check exponential backoff delays were called
            assert mock_sleep.call_count == 2
            delays = [call[0][0] for call in mock_sleep.call_args_list]
            assert delays[0] == pytest.approx(0.1)
            assert delays[1] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_tc058_backpressure_queue_capacity_exceeded(app_instance):
    """TC-058 / SEC-008: When queue capacity exceeds MAX_QUEUE_CAPACITY, dispatch returns HTTP 503."""
    settings = get_settings()
    transport = ASGITransport(app=app_instance)
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as client:
        # Mock queue service to simulate full capacity
        with patch("src.services.queue.QueueService.get_queue_size", new_callable=AsyncMock) as mock_size:
            mock_size.return_value = 100  # Equal to MAX_QUEUE_CAPACITY
            payload = {
                "agent_id": "homologation_agent",
                "task": "Overflow task",
                "workspace_slug": "default",
            }
            res = await client.post("/api/v1/agent/run", json=payload)
            assert res.status_code == 503
            assert "Queue capacity exceeded" in res.json()["detail"]


@pytest.mark.asyncio
async def test_tc071_sse_newline_injection_sanitized():
    """TC-071 / SEC-022: Newline and carriage return injection in SSE event_type is sanitized."""
    broker = SSEBroker()
    run_id = uuid.uuid4()

    # Attempt injecting newline into event_type
    malicious_event_type = "tool_call\nevent: malicious_injected_event\ndata: hacked"

    await broker.publish(
        run_id=run_id,
        event_type=malicious_event_type,
        data={"message": "ok"},
    )

    # Encode test
    event = SSEEvent(id=1, event=malicious_event_type, data="{}")
    encoded = event.encode()

    # Verify no unescaped newline injection splits the framing
    lines = encoded.strip().split("\n")
    # Must only have: id, event, data
    assert len(lines) == 3
    assert lines[0] == "id: 1"
    assert lines[1].startswith("event: tool_callevent: malicious_injected_eventdata: hacked")
    assert lines[2] == "data: {}"
    assert not any("\r" in line for line in lines)
