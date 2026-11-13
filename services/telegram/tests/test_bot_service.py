"""Unit tests for BotService commands, sovereign filter and callbacks (TC-122, TC-123, TC-124, TC-176, TC-216, TC-217)."""

from unittest.mock import AsyncMock
import pytest

from bot_service import BotService


@pytest.fixture
def mock_telegram_client():
    client = AsyncMock()
    client.send_message.return_value = {"ok": True, "result": {"message_id": 42}}
    client.edit_message_text.return_value = {"ok": True, "result": {"message_id": 42}}
    return client


@pytest.mark.asyncio
async def test_sovereign_filter_rejects_unauthorized_chat_id(mock_telegram_client):
    """TC-123: Messages from non-admin Chat IDs are silently dropped without response."""
    bot = BotService(telegram_client=mock_telegram_client, admin_chat_id=123456789)

    update = {
        "message": {
            "chat": {"id": 999999999},  # Unauthorized intruder
            "text": "/status",
        }
    }

    result = await bot.handle_update(update)
    assert result["status"] == "ignored"
    assert result["reason"] == "unauthorized_chat_id"
    mock_telegram_client.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_admin_status_command(mock_telegram_client):
    """TC-122: Joao sends /status and receives health report across all ports."""
    bot = BotService(telegram_client=mock_telegram_client, admin_chat_id=123456789)
    bot.check_ports_health = AsyncMock(return_value={"engine-core (:8000)": "ONLINE", "whatsapp-gateway (:3005)": "ONLINE"})

    update = {
        "message": {
            "chat": {"id": 123456789},
            "text": "/status",
        }
    }

    result = await bot.handle_update(update)
    assert result["status"] == "executed"
    assert result["command"] == "/status"
    mock_telegram_client.send_message.assert_called_once()
    msg_sent = mock_telegram_client.send_message.call_args[0][1]
    assert "The Agency" in msg_sent


@pytest.mark.asyncio
async def test_admin_pausar_command(mock_telegram_client):
    """TC-124: Joao sends /pausar and pauses pipeline operations."""
    bot = BotService(telegram_client=mock_telegram_client, admin_chat_id=123456789)

    update = {
        "message": {
            "chat": {"id": 123456789},
            "text": "/pausar",
        }
    }

    result = await bot.handle_update(update)
    assert result["status"] == "executed"
    assert result["command"] == "/pausar"
    mock_telegram_client.send_message.assert_called_once()
    msg_sent = mock_telegram_client.send_message.call_args[0][1]
    assert "PAUSADA" in msg_sent


@pytest.mark.asyncio
async def test_admin_retomar_command(mock_telegram_client):
    """TC-216: Joao sends /retomar and resumes operations."""
    bot = BotService(telegram_client=mock_telegram_client, admin_chat_id=123456789)

    update = {
        "message": {
            "chat": {"id": 123456789},
            "text": "/retomar",
        }
    }

    result = await bot.handle_update(update)
    assert result["status"] == "executed"
    assert result["command"] == "/retomar"
    mock_telegram_client.send_message.assert_called_once()
    msg_sent = mock_telegram_client.send_message.call_args[0][1]
    assert "RETOMADA" in msg_sent


@pytest.mark.asyncio
async def test_admin_aprovar_command(mock_telegram_client):
    """TC-217: Joao sends /aprovar barbearia-vintage."""
    bot = BotService(telegram_client=mock_telegram_client, admin_chat_id=123456789)

    update = {
        "message": {
            "chat": {"id": 123456789},
            "text": "/aprovar barbearia-vintage",
        }
    }

    result = await bot.handle_update(update)
    assert result["status"] == "executed"
    assert result["command"] == "/aprovar"
    assert result["target"] == "barbearia-vintage"
    mock_telegram_client.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_callback_query_approve_and_reject(mock_telegram_client):
    """TC-176 / BDD-F1-21: Inline button click updates message with decision."""
    bot = BotService(telegram_client=mock_telegram_client, admin_chat_id=123456789)

    # Approve callback
    update_approve = {
        "callback_query": {
            "from": {"id": 123456789},
            "data": "approve:req-99",
            "message": {"message_id": 42, "chat": {"id": 123456789}},
        }
    }
    res_app = await bot.handle_update(update_approve)
    assert res_app["status"] == "approved"
    assert res_app["approval_id"] == "req-99"
    mock_telegram_client.edit_message_text.assert_called_once()
    assert "APROVADA" in mock_telegram_client.edit_message_text.call_args[0][2]

    # Reject callback
    mock_telegram_client.edit_message_text.reset_mock()
    update_reject = {
        "callback_query": {
            "from": {"id": 123456789},
            "data": "reject:req-99",
            "message": {"message_id": 42, "chat": {"id": 123456789}},
        }
    }
    res_rej = await bot.handle_update(update_reject)
    assert res_rej["status"] == "rejected"
    assert "REJEITADA" in mock_telegram_client.edit_message_text.call_args[0][2]
