"""Banco Inter Payment Gateway Main Application (Port :3006)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Request
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from config import settings
from inter_client import BancoInterClient
from mcp_server import create_payment_mcp_server
from webhook_handler import PaymentWebhookHandler

inter_client = BancoInterClient()
webhook_handler = PaymentWebhookHandler()
mcp_server = create_payment_mcp_server(inter_client=inter_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Payment Gateway Service starting on port {port}...", port=settings.PAYMENT_PORT)
    yield
    logger.info("Payment Gateway Service shutting down...")


app = FastAPI(
    title="Payment Gateway Microservice",
    description="Banco Inter mTLS integration, PIX immediate charges and webhook receiver",
    version="0.1.0",
    lifespan=lifespan,
)

# Apply X-Agency-Key middleware (exempting health, webhooks, docs)
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/payment/health",
        "/api/v1/inter/webhook",
        "/docs",
        "/openapi.json",
    },
)


@app.get("/api/v1/health")
@app.get("/api/v1/payment/health")
async def health_check() -> dict[str, Any]:
    """Healthcheck endpoint for payment gateway."""
    return {
        "status": "healthy",
        "service": "payment-gateway",
        "port": settings.PAYMENT_PORT,
    }


@app.post("/api/v1/inter/webhook")
async def inter_webhook_endpoint(request: Request) -> dict[str, Any]:
    """Receives and processes PIX payment clearance webhooks from Banco Inter (TC-116, TC-117, TC-118, TC-119, TC-178)."""
    # 1. Verify webhook header and IP origin
    webhook_handler.verify_webhook_request(request)

    # 2. Parse payload
    payload = await request.json()
    pix_list = payload.get("pix", [])

    results = []
    for pix_event in pix_list:
        txid = pix_event.get("txid")
        valor = pix_event.get("valor", "0.00")
        horario = pix_event.get("horario", "")
        if txid:
            res = await webhook_handler.handle_pix_payment_event(
                txid=txid,
                valor_str=valor,
                horario_str=horario,
            )
            results.append(res)

    logger.info("Processed {count} PIX webhook clearance events", count=len(results))
    return {
        "status": "ok",
        "processed_count": len(results),
        "events": results,
    }


# Mount MCP SSE app at root
sse_app = mcp_server.sse_app()
app.mount("/", sse_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.PAYMENT_PORT, reload=False)
