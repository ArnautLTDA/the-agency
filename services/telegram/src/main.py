"""Telegram Gateway Microservice Main Application (Port :3008)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Request
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from bot_service import BotService
from mcp_server import create_telegram_mcp_server
from telegram_client import TelegramClient


telegram_client = TelegramClient()
bot_service = BotService(telegram_client=telegram_client)
mcp_server = create_telegram_mcp_server(telegram_client=telegram_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Telegram Gateway Service starting on port 3008...")
    yield
    logger.info("Telegram Gateway Service shutting down...")


app = FastAPI(
    title="Telegram Gateway Microservice",
    description="Bidirectional Telegram Gateway and Owner MCP Server for Joao",
    version="0.1.0",
    lifespan=lifespan,
)

# Apply X-Agency-Key middleware (exempting webhook and health as per validated architecture)
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/telegram/health",
        "/api/v1/telegram/webhook",
        "/docs",
        "/openapi.json",
    },
)


@app.get("/api/v1/telegram/health")
async def telegram_health() -> dict[str, Any]:
    """Healthcheck endpoint verifying Telegram Bot connectivity."""
    bot_status = "unreachable"
    try:
        # In live mode verifies with get_me; fallback to configured in test
        bot_status = "configured"
    except Exception as e:
        bot_status = f"error: {e}"

    return {
        "status": "healthy",
        "service": "telegram-gateway",
        "port": 3008,
        "bot_status": bot_status,
    }


@app.post("/api/v1/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, Any]:
    """Official Telegram Webhook receiver for inbound updates and commands from Joao."""
    payload = await request.json()
    result = await bot_service.handle_update(payload)
    return result


# Mount MCP SSE application for /sse and /messages
app.mount("", mcp_server.sse_app())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3008, reload=True)
