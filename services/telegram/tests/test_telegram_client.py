"""Unit tests for TelegramClient and 429 Flood Control retry logic (TC-218)."""

import pytest
import respx
import httpx

from config import settings
from telegram_client import TelegramClient, escape_markdown_v2


def test_escape_markdown_v2():
    """Verifies all special reserved characters are escaped for Telegram MarkdownV2."""
    raw = "Hello_World*! [Link](url) #test +1 -1 =0 {tag} .end"
    escaped = escape_markdown_v2(raw)
    assert r"\_" in escaped
    assert r"\*" in escaped
    assert r"\!" in escaped
    assert r"\[" in escaped
    assert r"\#" in escaped
    assert r"\." in escaped


@pytest.mark.asyncio
@respx.mock
async def test_telegram_client_send_message_success():
    """Verifies normal message dispatch to Telegram API."""
    respx.post(f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 999}})
    )

    client = TelegramClient()
    result = await client.send_message(chat_id=123, text="Test Message")
    assert result["ok"] is True
    assert result["result"]["message_id"] == 999


@pytest.mark.asyncio
@respx.mock
async def test_telegram_client_flood_control_retry(monkeypatch):
    """TC-218: Verifies HTTP 429 Flood Control is captured, sleeps retry_after and succeeds on retry."""
    import asyncio
    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    route = respx.post(f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage")
    # First call returns 429 with retry_after: 2; second call succeeds with 200
    route.side_effect = [
        httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 2}}),
        httpx.Response(200, json={"ok": True, "result": {"message_id": 1001}}),
    ]

    client = TelegramClient()
    result = await client.send_message(chat_id=123, text="Flood test")
    assert result["ok"] is True
    assert result["result"]["message_id"] == 1001
    assert sleep_calls == [2.0]
