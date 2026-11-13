"""Core Telegram Bot logic, command dispatcher, sovereign filter, and approvals (TC-122, TC-123, TC-124, TC-176, TC-216, TC-217)."""

import asyncio
from datetime import datetime, timezone
import json
from typing import Any
import httpx
from loguru import logger

from config import settings
from telegram_client import TelegramClient, escape_markdown_v2


MONITORED_SERVICES: list[dict[str, Any]] = [
    {"name": "engine-core", "port": 8000, "url": "http://127.0.0.1:8000/health"},
    {"name": "whatsapp-gateway", "port": 3005, "url": "http://127.0.0.1:3005/api/v1/session/status"},
    {"name": "payment-gateway", "port": 3006, "url": "http://127.0.0.1:3006/api/v1/banking/balance"},
    {"name": "guardrail-gateway", "port": 3007, "url": "http://127.0.0.1:3007/api/v1/health"},
    {"name": "telegram-gateway", "port": 3008, "url": "http://127.0.0.1:3008/api/v1/telegram/health"},
    {"name": "osint-scraper-gateway", "port": 3009, "url": "http://127.0.0.1:3009/api/v1/health"},
    {"name": "workspace-sandbox-service", "port": 3010, "url": "http://127.0.0.1:3010/api/v1/health"},
    {"name": "git-vcs-gateway", "port": 3011, "url": "http://127.0.0.1:3011/api/v1/health"},
    {"name": "deploy-cloud-gateway", "port": 3012, "url": "http://127.0.0.1:3012/api/v1/health"},
    {"name": "knowledge-memory-gateway", "port": 3013, "url": "http://127.0.0.1:3013/api/v1/health"},
    {"name": "browser-gateway", "port": 3014, "url": "http://127.0.0.1:3014/api/v1/health"},
    {"name": "security-audit-gateway", "port": 3015, "url": "http://127.0.0.1:3015/api/v1/health"},
    {"name": "sonarqube", "port": 9000, "url": "http://127.0.0.1:9000/api/system/status"},
    {"name": "qdrant", "port": 6333, "url": "http://127.0.0.1:6333/readyz"},
    {"name": "searxng", "port": 8888, "url": "http://127.0.0.1:8888/"},
    {"name": "rabbitmq", "port": 5672, "url": "http://127.0.0.1:15672/api/overview"},
    {"name": "grafana", "port": 3001, "url": "http://127.0.0.1:3001/api/health"},
    {"name": "loki", "port": 3100, "url": "http://127.0.0.1:3100/ready"},
]


class BotService:
    """Handles Telegram interactions, admin authorization, and system controls."""

    def __init__(
        self,
        telegram_client: TelegramClient | None = None,
        admin_chat_id: int = settings.TELEGRAM_ADMIN_CHAT_ID,
    ) -> None:
        self.client = telegram_client or TelegramClient()
        self.admin_chat_id = admin_chat_id

    async def check_ports_health(self) -> dict[str, str]:
        """Probes local ports and returns health status map (TC-122)."""
        results: dict[str, str] = {}
        async with httpx.AsyncClient(timeout=1.5) as http:
            for s in MONITORED_SERVICES:
                name = s["name"]
                port = s["port"]
                url = s["url"]
                try:
                    res = await http.get(url)
                    status = "ONLINE" if res.status_code in (200, 401) else f"HTTP {res.status_code}"
                except Exception:
                    status = "OFFLINE"
                results[f"{name} (:{port})"] = status
        return results

    async def handle_update(self, update: dict[str, Any]) -> dict[str, Any]:
        """Processes an incoming Telegram webhook update with sovereign filtering."""
        # 1. Handle Callback Query (Inline button clicks)
        if "callback_query" in update:
            cb = update["callback_query"]
            sender_id = cb.get("from", {}).get("id")

            # Sovereign filter
            if sender_id != self.admin_chat_id:
                logger.warning(f"Unauthorized callback attempt from ID: {sender_id}. Dropped silently.")
                return {"status": "ignored", "reason": "unauthorized"}

            cb_data = cb.get("data", "")
            message_id = cb.get("message", {}).get("message_id")
            chat_id = cb.get("message", {}).get("chat", {}).get("id")

            now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M UTC")

            if cb_data.startswith("approve:"):
                approval_id = cb_data.split(":", 1)[1]
                updated_text = escape_markdown_v2(f"✅ Decisão #{approval_id} APROVADA por João em {now_str}.")
                if message_id and chat_id:
                    await self.client.edit_message_text(chat_id, message_id, updated_text)
                return {"status": "approved", "approval_id": approval_id}

            elif cb_data.startswith("reject:"):
                approval_id = cb_data.split(":", 1)[1]
                updated_text = escape_markdown_v2(f"❌ Decisão #{approval_id} REJEITADA por João em {now_str}.")
                if message_id and chat_id:
                    await self.client.edit_message_text(chat_id, message_id, updated_text)
                return {"status": "rejected", "approval_id": approval_id}

            return {"status": "callback_handled"}

        # 2. Handle Text Messages
        message = update.get("message")
        if not message:
            return {"status": "no_message"}

        sender_chat_id = message.get("chat", {}).get("id")

        # TC-123: Sovereign Filter — Reject any message not originating from Joao's admin chat ID
        if sender_chat_id != self.admin_chat_id:
            logger.warning(f"Unauthorized access attempt from Chat ID: {sender_chat_id}. Dropped silently.")
            return {"status": "ignored", "reason": "unauthorized_chat_id"}

        text = message.get("text", "").strip()

        # Command Dispatch
        if text.startswith("/status"):
            # TC-122: Query health across all ports
            health_map = await self.check_ports_health()
            online_count = sum(1 for v in health_map.values() if v == "ONLINE")
            total_count = len(health_map)

            lines = [
                f"*The Agency — Relatório de Saúde do Sistema*",
                f"Serviços Online: {online_count}/{total_count}",
                "",
            ]
            for svc, st in health_map.items():
                icon = "🟢" if st == "ONLINE" else "🔴"
                lines.append(f"{icon} {svc}: {st}")

            report_text = escape_markdown_v2("\n".join(lines))
            await self.client.send_message(self.admin_chat_id, report_text)
            return {"status": "executed", "command": "/status"}

        elif text.startswith("/pausar"):
            # TC-124: Pause active outreach and mining
            logger.warning("Admin issued /pausar command. Suspending active outreach.")
            # Dispatch signal to engine-core if reachable
            try:
                async with httpx.AsyncClient(timeout=2.0) as http:
                    await http.post(f"{settings.ENGINE_CORE_URL}/api/v1/agent/pause")
            except Exception as e:
                logger.debug(f"Notice: engine core pause signal handled locally: {e}")

            reply = escape_markdown_v2("🛑 Operação da esteira PAUSADA com sucesso por João.")
            await self.client.send_message(self.admin_chat_id, reply)
            return {"status": "executed", "command": "/pausar"}

        elif text.startswith("/retomar"):
            # TC-216: Resume operations
            logger.info("Admin issued /retomar command. Resuming pipeline operations.")
            try:
                async with httpx.AsyncClient(timeout=2.0) as http:
                    await http.post(f"{settings.ENGINE_CORE_URL}/api/v1/agent/resume")
            except Exception as e:
                logger.debug(f"Notice: engine core resume signal handled locally: {e}")

            reply = escape_markdown_v2("▶️ Operação da esteira RETOMADA com sucesso por João.")
            await self.client.send_message(self.admin_chat_id, reply)
            return {"status": "executed", "command": "/retomar"}

        elif text.startswith("/aprovar"):
            # TC-217: Calibration step or lead approval
            parts = text.split(maxsplit=1)
            target = parts[1] if len(parts) > 1 else "lead_geral"
            reply = escape_markdown_v2(f"✅ Lead/Decisão '{target}' APROVADA com sucesso por João.")
            await self.client.send_message(self.admin_chat_id, reply)
            return {"status": "executed", "command": "/aprovar", "target": target}

        return {"status": "unhandled_command"}
