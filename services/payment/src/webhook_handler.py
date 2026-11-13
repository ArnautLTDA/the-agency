"""Banco Inter PIX Webhook Handler (TC-116, TC-117, TC-118, TC-119, TC-178)."""

from datetime import datetime, timezone
import ipaddress
from typing import Any
import aio_pika
import aiosqlite
from fastapi import HTTPException, Request, status
from loguru import logger

from agency_common.amqp import AMQPMessageEnvelope
from config import settings


def is_ip_allowed(client_ip: str | None, whitelist: set[str] = settings.ip_whitelist_set) -> bool:
    """Validates incoming IP against Banco Inter CIDR blocks and localhost (TC-178)."""
    if not client_ip:
        return False
    if client_ip in whitelist:
        return True

    try:
        ip_obj = ipaddress.ip_address(client_ip)
        for net in whitelist:
            if "/" in net:
                if ip_obj in ipaddress.ip_network(net, strict=False):
                    return True
    except ValueError:
        pass
    return False


class PaymentWebhookHandler:
    """Processes PIX liquidation webhooks from Banco Inter."""

    def __init__(self, db_path: str = settings.DATABASE_PATH) -> None:
        self.db_path = db_path

    def verify_webhook_request(self, request: Request) -> None:
        """Enforces x-webhook-key header and IP whitelisting (TC-119, TC-178)."""
        webhook_key = request.headers.get("x-webhook-key")
        if not webhook_key or webhook_key != settings.INTER_WEBHOOK_KEY:
            logger.warning("Rejected webhook: missing or invalid x-webhook-key header")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing webhook key",
            )

        client_ip = request.client.host if request.client else None
        if not is_ip_allowed(client_ip):
            logger.warning("Rejected webhook from unauthorized IP: {ip}", ip=client_ip)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized IP address",
            )

    async def handle_pix_payment_event(
        self,
        txid: str,
        valor_str: str,
        horario_str: str,
        exchange: aio_pika.abc.AbstractExchange | None = None,
    ) -> dict[str, Any]:
        """Updates SQLite tables and publishes AMQP event for confirmed PIX payment (TC-116, TC-117, TC-118)."""
        paid_at = horario_str or datetime.now(timezone.utc).isoformat()
        lead_id: str | None = None

        # 1. Update pix_transactions in pipeline.db
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT lead_id, amount_cents FROM pix_transactions WHERE txid = ?", (txid,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    lead_id = row[0]

            await db.execute(
                "UPDATE pix_transactions SET status = 'CONCLUIDA', paid_at = ? WHERE txid = ?",
                (paid_at, txid),
            )

            # 2. Advance lead stage to 'DEV' (TC-117)
            if lead_id:
                await db.execute(
                    "UPDATE leads SET stage = 'DEV', updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), lead_id),
                )
                logger.info("Advanced lead {lid} to stage 'DEV' upon PIX clearance", lid=lead_id)

            await db.commit()

        # 3. Publish AMQP message envelope (TC-118)
        envelope = AMQPMessageEnvelope(
            from_service="payment-gateway",
            to_service="engine-core",
            payload={
                "event": "pix_payment_confirmed",
                "txid": txid,
                "lead_id": lead_id,
                "amount": valor_str,
                "paid_at": paid_at,
            },
        )

        if exchange:
            amqp_msg = aio_pika.Message(
                body=envelope.model_dump_json().encode(),
                content_type="application/json",
                correlation_id=str(envelope.correlation_id),
            )
            await exchange.publish(amqp_msg, routing_key="payment.webhooks")
            logger.info("Published PIX payment confirmation to payment.webhooks for txid {txid}", txid=txid)

        return {
            "status": "processed",
            "txid": txid,
            "lead_id": lead_id,
            "envelope": envelope,
        }
