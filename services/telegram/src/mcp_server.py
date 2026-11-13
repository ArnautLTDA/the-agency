"""Native MCP Server registering Telegram alert and owner approval tools (:3008)."""

import uuid
from typing import Any
from mcp.server.mcpserver import MCPServer

from config import settings
from telegram_client import TelegramClient, escape_markdown_v2


def create_telegram_mcp_server(telegram_client: TelegramClient | None = None) -> MCPServer:
    """Builds and configures the telegram-gateway MCP server instance."""
    server = MCPServer(
        name="telegram-gateway",
        version="0.1.0",
        instructions="Official Agency Telegram Gateway MCP Server",
    )
    client = telegram_client or TelegramClient()
    admin_id = settings.TELEGRAM_ADMIN_CHAT_ID

    @server.tool(
        name="send_telegram_alert",
        description="Sends a critical or informational alert formatted in MarkdownV2 directly to Joao's Telegram.",
    )
    async def send_telegram_alert(
        level: str,
        title: str,
        message: str,
        action_buttons: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        level_icons = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "CRITICAL": "🚨",
            "SUCCESS": "🎉",
        }
        icon = level_icons.get(level.upper(), "📢")
        formatted_header = f"{icon} *{title}*\n\n"
        formatted_body = message
        full_text = escape_markdown_v2(formatted_header + formatted_body)

        reply_markup = None
        if action_buttons:
            keyboard = [
                [{"text": btn["label"], "callback_data": btn["callback_data"]} for btn in action_buttons]
            ]
            reply_markup = {"inline_keyboard": keyboard}

        result = await client.send_message(
            chat_id=admin_id,
            text=full_text,
            reply_markup=reply_markup,
        )
        return {
            "status": "sent",
            "level": level,
            "message_id": result.get("result", {}).get("message_id"),
        }

    @server.tool(
        name="request_owner_approval",
        description="Requests an interactive human approval decision from Joao via Telegram with inline buttons (24h timeout).",
    )
    async def request_owner_approval(
        decision_type: str,
        details: str,
        lead_id: str | None = None,
    ) -> dict[str, Any]:
        approval_id = str(uuid.uuid4())[:8]
        header = f"⚖️ *Solicitação de Aprovação Humana*\n"
        body = f"*Tipo:* {decision_type}\n*Lead:* {lead_id or 'N/A'}\n\n*Detalhes:*\n{details}\n\n_Esta solicitação expira em 24 horas._"
        full_text = escape_markdown_v2(header + body)

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Aprovar", "callback_data": f"approve:{approval_id}"},
                    {"text": "❌ Rejeitar", "callback_data": f"reject:{approval_id}"},
                ]
            ]
        }

        res = await client.send_message(
            chat_id=admin_id,
            text=full_text,
            reply_markup=reply_markup,
        )

        return {
            "approval_id": approval_id,
            "decision_type": decision_type,
            "status": "PENDING",
            "message_id": res.get("result", {}).get("message_id"),
        }

    return server
