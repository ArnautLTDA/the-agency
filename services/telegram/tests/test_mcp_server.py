"""Unit tests for Telegram MCP Server tools (TC-121, TC-176)."""

from unittest.mock import AsyncMock
import pytest

from mcp_server import create_telegram_mcp_server


@pytest.fixture
def mock_telegram_client():
    client = AsyncMock()
    client.send_message.return_value = {"ok": True, "result": {"message_id": 77}}
    return client


@pytest.mark.asyncio
async def test_send_telegram_alert_mcp_tool(mock_telegram_client):
    """TC-121: Invocação MCP send_telegram_alert com formatação e botões."""
    server = create_telegram_mcp_server(telegram_client=mock_telegram_client)

    result = await server.call_tool(
        "send_telegram_alert",
        {
            "level": "CRITICAL",
            "title": "Alerta de Segurança",
            "message": "Tentativa de invasão detectada.",
            "action_buttons": [{"label": "Ver Logs", "callback_data": "view_logs"}],
        },
    )

    assert result is not None
    mock_telegram_client.send_message.assert_called_once()
    _, kwargs = mock_telegram_client.send_message.call_args
    assert kwargs["reply_markup"] is not None
    assert "Alerta de Segurança" in kwargs["text"]


@pytest.mark.asyncio
async def test_request_owner_approval_mcp_tool(mock_telegram_client):
    """TC-176: Invocação MCP request_owner_approval com inline keyboard e status PENDING."""
    server = create_telegram_mcp_server(telegram_client=mock_telegram_client)

    result = await server.call_tool(
        "request_owner_approval",
        {
            "decision_type": "DEPLOY_PRODUCTION",
            "details": "Deploy da Barbearia Vintage para domínio oficial",
            "lead_id": "barbearia-vintage",
        },
    )

    assert result is not None
    mock_telegram_client.send_message.assert_called_once()
    _, kwargs = mock_telegram_client.send_message.call_args
    # Check approve/reject keyboard
    kb = kwargs["reply_markup"]["inline_keyboard"][0]
    assert kb[0]["text"] == "✅ Aprovar"
    assert kb[1]["text"] == "❌ Rejeitar"
    assert "DEPLOY\\_PRODUCTION" in kwargs["text"]
