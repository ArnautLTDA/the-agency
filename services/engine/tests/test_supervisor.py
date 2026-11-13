"""Tests for Supervisor Service, Fail-Fast Pause, and Autonomous Recovery (TC-147, TC-148)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest
import respx

from src.services.queue import QueueService
from src.services.supervisor import (
    DEFAULT_VITAL_GATEWAYS,
    EngineOperationalState,
    SupervisorService,
    VitalGatewayStatus,
)


@pytest.fixture
def mock_queue_service():
    qs = MagicMock(spec=QueueService)
    qs.is_connected = True
    qs.channel = None
    qs.freeze_outbound = MagicMock()
    qs.unfreeze_outbound = MagicMock()
    return qs


@pytest.mark.asyncio
async def test_supervisor_all_healthy(mock_queue_service):
    """When all 3 vital gateways respond healthy, state remains OPERACIONAL."""
    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(
            200, json={"status": "connected", "ready": True}
        )
        respx_mock.get("http://127.0.0.1:3006/api/v1/health").respond(
            200, json={"status": "healthy"}
        )
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(
            200, json={"status": "healthy"}
        )

        supervisor = SupervisorService(queue_service=mock_queue_service)
        results = await supervisor.check_vital_gateways()

        assert len(results) == 3
        assert all(s.is_healthy for s in results.values())
        state = await supervisor.step()
        assert state == EngineOperationalState.OPERACIONAL
        assert not supervisor.is_paused()
        mock_queue_service.freeze_outbound.assert_not_called()


@pytest.mark.asyncio
async def test_supervisor_fail_fast_whatsapp_down_tc147(mock_queue_service):
    """TC-147: When WhatsApp gateway becomes unhealthy, engine transitions to PAUSA_EMERGENCIAL."""
    alert_callback = AsyncMock()

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(
            503, json={"status": "unhealthy", "error": "disconnected"}
        )
        respx_mock.get("http://127.0.0.1:3006/api/v1/health").respond(
            200, json={"status": "healthy"}
        )
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(
            200, json={"status": "healthy"}
        )

        supervisor = SupervisorService(
            queue_service=mock_queue_service,
            alert_callback=alert_callback,
        )

        state = await supervisor.step()

        assert state == EngineOperationalState.PAUSA_EMERGENCIAL
        assert supervisor.is_paused()
        mock_queue_service.freeze_outbound.assert_called_once()
        alert_callback.assert_called_once()
        call_args = alert_callback.call_args[0]
        assert call_args[0] == "CRITICAL"
        assert "Pausa Emergencial" in call_args[1]


@pytest.mark.asyncio
async def test_supervisor_fail_fast_payment_timeout_tc147(mock_queue_service):
    """TC-147: When payment gateway times out or raises connection error, transitions to PAUSA_EMERGENCIAL."""
    alert_callback = AsyncMock()

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(
            200, json={"status": "connected"}
        )
        respx_mock.get("http://127.0.0.1:3006/api/v1/health").side_effect = httpx.ConnectTimeout("Timeout")
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(
            200, json={"status": "healthy"}
        )

        supervisor = SupervisorService(
            queue_service=mock_queue_service,
            alert_callback=alert_callback,
        )

        state = await supervisor.step()
        assert state == EngineOperationalState.PAUSA_EMERGENCIAL
        assert supervisor.is_paused()
        mock_queue_service.freeze_outbound.assert_called_once()


@pytest.mark.asyncio
async def test_supervisor_autonomous_recovery_tc148(mock_queue_service):
    """TC-148: When all vital gateways are restored healthy, engine automatically resumes OPERACIONAL."""
    alert_callback = AsyncMock()

    with respx.mock(assert_all_called=False) as respx_mock:
        # Step 1: Payment fails -> state becomes PAUSA_EMERGENCIAL
        pay_route = respx_mock.get("http://127.0.0.1:3006/api/v1/health")
        pay_route.respond(500, json={"status": "error"})
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(200, json={"status": "ready"})
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(200, json={"status": "healthy"})

        supervisor = SupervisorService(
            queue_service=mock_queue_service,
            alert_callback=alert_callback,
        )

        state_1 = await supervisor.step()
        assert state_1 == EngineOperationalState.PAUSA_EMERGENCIAL
        assert alert_callback.call_count == 1

        # Step 2: Payment recovers -> state transitions back to OPERACIONAL
        pay_route.respond(200, json={"status": "healthy"})

        state_2 = await supervisor.step()
        assert state_2 == EngineOperationalState.OPERACIONAL
        assert not supervisor.is_paused()
        mock_queue_service.unfreeze_outbound.assert_called_once()
        assert alert_callback.call_count == 2
        recovery_args = alert_callback.call_args[0]
        assert recovery_args[0] == "INFO"
        assert "Normalizada" in recovery_args[1]


@pytest.mark.asyncio
async def test_supervisor_manual_pause_and_resume(mock_queue_service):
    """Admin manual pause and resume (TC-124, TC-216)."""
    alert_callback = AsyncMock()

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(200, json={"status": "ready"})
        respx_mock.get("http://127.0.0.1:3006/api/v1/health").respond(200, json={"status": "healthy"})
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(200, json={"status": "healthy"})

        supervisor = SupervisorService(
            queue_service=mock_queue_service,
            alert_callback=alert_callback,
        )

        # Pause manually
        await supervisor.pause_manually("Maintenance requested")
        assert supervisor.is_paused()
        assert supervisor._manually_paused is True
        mock_queue_service.freeze_outbound.assert_called_once()

        # Step while manually paused does NOT auto-resume even if gateways are healthy
        await supervisor.step()
        assert supervisor.is_paused()

        # Resume manually
        resumed = await supervisor.resume_manually()
        assert resumed is True
        assert not supervisor.is_paused()
        assert supervisor._manually_paused is False
        mock_queue_service.unfreeze_outbound.assert_called_once()


@pytest.mark.asyncio
async def test_supervisor_manual_resume_rejected_if_vital_down(mock_queue_service):
    """Admin manual resume is rejected if vital gateways are still unhealthy."""
    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(503, json={"status": "down"})
        respx_mock.get("http://127.0.0.1:3006/api/v1/health").respond(200, json={"status": "healthy"})
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(200, json={"status": "healthy"})

        supervisor = SupervisorService(queue_service=mock_queue_service)
        await supervisor.pause_manually("Test pause")

        resumed = await supervisor.resume_manually()
        assert resumed is False
        assert supervisor.is_paused()


@pytest.mark.asyncio
async def test_supervisor_background_lifecycle():
    """Supervisor start and stop background task cleanly."""
    supervisor = SupervisorService(poll_interval_seconds=0.05)
    await supervisor.start()
    assert supervisor._is_running is True
    assert supervisor._background_task is not None

    await asyncio.sleep(0.1)
    await supervisor.stop()
    assert supervisor._is_running is False
    assert supervisor._background_task is None


@pytest.mark.asyncio
async def test_supervisor_amqp_alert_dispatch():
    """Supervisor dispatches alert to AMQP exchange when connected."""
    mock_qs = MagicMock()
    mock_qs.is_connected = True
    mock_channel = MagicMock()
    mock_exchange = MagicMock()
    mock_exchange.publish = AsyncMock()
    mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)
    mock_qs.channel = mock_channel
    mock_qs.freeze_outbound = MagicMock()

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(503, json={"status": "error"})
        respx_mock.get("http://127.0.0.1:3006/api/v1/health").respond(200, json={"status": "healthy"})
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(200, json={"status": "healthy"})

        async with httpx.AsyncClient() as client:
            supervisor = SupervisorService(queue_service=mock_qs, http_client=client)
            await supervisor.step()

            assert supervisor.is_paused()
            mock_exchange.publish.assert_called_once()
            call_kwargs = mock_exchange.publish.call_args[1]
            assert call_kwargs["routing_key"] == "telegram.alert.emergency"

            # Check status report
            report = supervisor.get_status_report()
            assert report["state"] == "PAUSA_EMERGENCIAL"
            assert report["is_paused"] is True
            assert "whatsapp" in report["vital_gateways"]


def test_supervisor_singletons():
    """get_supervisor and set_supervisor helpers."""
    from src.services.supervisor import get_supervisor, set_supervisor

    sup1 = get_supervisor()
    assert sup1 is not None
    set_supervisor(None)
    sup2 = get_supervisor()
    assert sup2 is not None
    set_supervisor(None)
