"""Async HTTP client for Telegram Bot API with 429 Flood Control resilience (TC-218)."""

import asyncio
import re
from typing import Any
import httpx
from loguru import logger

from config import settings


def escape_markdown_v2(text: str) -> str:
    """Escapes Telegram MarkdownV2 reserved characters."""
    reserved_chars = r"_*[]()~>#+-=|{}.!\\"
    return re.sub(f"([{re.escape(reserved_chars)}])", r"\\\1", text)


class TelegramClient:
    """Resilient client communicating with Telegram Bot API."""

    def __init__(
        self,
        token: str = settings.TELEGRAM_BOT_TOKEN,
        api_base: str = settings.TELEGRAM_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")
        self._client = client

    @property
    def base_url(self) -> str:
        return f"{self.api_base}/bot{self.token}"

    async def _post_with_retry(self, endpoint: str, json_data: dict[str, Any], max_retries: int = 3) -> dict[str, Any]:
        """Posts payload to Telegram API with automatic backoff for 429 Too Many Requests (TC-218)."""
        url = f"{self.base_url}/{endpoint}"
        client_to_use = self._client or httpx.AsyncClient(timeout=10.0)
        should_close = self._client is None

        try:
            for attempt in range(max_retries + 1):
                response = await client_to_use.post(url, json=json_data)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429:
                    error_data = response.json()
                    retry_after = error_data.get("parameters", {}).get("retry_after", 1)
                    logger.warning(
                        f"Telegram API 429 Flood Control: retry after {retry_after}s (attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(float(retry_after))
                        continue

                # Raise for any persistent non-200 status
                response.raise_for_status()
            raise httpx.HTTPStatusError("Telegram API retry attempts exhausted", request=None, response=response)
        finally:
            if should_close:
                await client_to_use.aclose()

    async def get_me(self) -> dict[str, Any]:
        """Validates bot credentials and connectivity."""
        url = f"{self.base_url}/getMe"
        client_to_use = self._client or httpx.AsyncClient(timeout=10.0)
        should_close = self._client is None
        try:
            res = await client_to_use.get(url)
            res.raise_for_status()
            return res.json()
        finally:
            if should_close:
                await client_to_use.aclose()

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "MarkdownV2",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Sends message with optional inline buttons and MarkdownV2 formatting."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        return await self._post_with_retry("sendMessage", payload)

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str = "MarkdownV2",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edits an existing message in chat (e.g. updating approval status)."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        return await self._post_with_retry("editMessageText", payload)
