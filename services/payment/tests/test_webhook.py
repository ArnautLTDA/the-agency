"""Tests for PIX Webhook processing and security (TC-116, TC-117, TC-118, TC-119, TC-178)."""

from unittest.mock import AsyncMock, MagicMock
import aiosqlite
from fastapi import HTTPException, Request
import pytest

from webhook_handler import PaymentWebhookHandler, is_ip_allowed


def test_ip_whitelist_validation_tc178():
    """TC-178: Validates allowed Banco Inter IP ranges and rejects unauthorized origins."""
    # Allowed
    assert is_ip_allowed("127.0.0.1")
    assert is_ip_allowed("testclient")
    assert is_ip_allowed("54.232.10.5")  # In 54.232.0.0/16
    assert is_ip_allowed("54.207.254.1") # In 54.207.0.0/16

    # Rejected
    assert not is_ip_allowed("192.168.1.100")
    assert not is_ip_allowed("10.0.0.1")
    assert not is_ip_allowed("8.8.8.8")
    assert not is_ip_allowed(None)


def test_verify_webhook_request_rejects_missing_key_tc119():
    """TC-119: Rejects webhook missing x-webhook-key header with 403 Forbidden."""
    handler = PaymentWebhookHandler()
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.client = MagicMock()
    mock_request.client.host = "127.0.0.1"

    with pytest.raises(HTTPException) as exc:
        handler.verify_webhook_request(mock_request)
    assert exc.value.status_code == 403


def test_verify_webhook_request_rejects_unauthorized_ip():
    """Rejects webhook from untrusted IP address even with valid key."""
    handler = PaymentWebhookHandler()
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"x-webhook-key": "inter_webhook_secret_key_123"}
    mock_request.client = MagicMock()
    mock_request.client.host = "198.51.100.23"

    with pytest.raises(HTTPException) as exc:
        handler.verify_webhook_request(mock_request)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_handle_pix_payment_event_updates_db_and_lead_tc116_tc117_tc118(temp_db: str):
    """TC-116, TC-117, TC-118: Confirms PIX, updates pix_transactions to CONCLUIDA, advances lead to DEV, and publishes AMQP."""
    txid = "AGY_TEST_TXID_999"
    lead_id = "barbearia-vintage"

    # Pre-insert transaction in ATIVA state
    async with aiosqlite.connect(temp_db) as db:
        await db.execute(
            """
            INSERT INTO pix_transactions (txid, lead_id, amount_cents, status, created_at)
            VALUES (?, ?, 15000, 'ATIVA', '2026-11-13T12:00:00Z')
            """,
            (txid, lead_id),
        )
        await db.commit()

    handler = PaymentWebhookHandler(db_path=temp_db)
    mock_exchange = AsyncMock()

    result = await handler.handle_pix_payment_event(
        txid=txid,
        valor_str="150.00",
        horario_str="2026-11-13T14:30:00Z",
        exchange=mock_exchange,
    )

    assert result["status"] == "processed"
    assert result["lead_id"] == lead_id

    # TC-116: Verify pix_transactions updated
    async with aiosqlite.connect(temp_db) as db:
        async with db.execute("SELECT status, paid_at FROM pix_transactions WHERE txid = ?", (txid,)) as cursor:
            tx_row = await cursor.fetchone()
            assert tx_row[0] == "CONCLUIDA"
            assert tx_row[1] == "2026-11-13T14:30:00Z"

        # TC-117: Verify lead advanced to DEV stage
        async with db.execute("SELECT stage FROM leads WHERE id = ?", (lead_id,)) as cursor:
            lead_row = await cursor.fetchone()
            assert lead_row[0] == "DEV"

    # TC-118: Verify AMQP envelope published
    mock_exchange.publish.assert_called_once()
    _, kwargs = mock_exchange.publish.call_args
    assert kwargs["routing_key"] == "payment.webhooks"
    envelope = result["envelope"]
    assert envelope.from_service == "payment-gateway"
    assert envelope.to_service == "engine-core"
    assert envelope.payload["event"] == "pix_payment_confirmed"
    assert envelope.payload["txid"] == txid
