"""Tests for Banco Inter API Client (TC-114, TC-115, TC-120, TC-219)."""

import pytest
import respx

from inter_client import BancoInterClient


@pytest.mark.asyncio
async def test_get_access_token_success_tc114():
    """TC-114: Obtains OAuth 2.0 Bearer token with mTLS and caches it."""
    with respx.mock(base_url="https://cdpj-sandbox.inter.co") as mock:
        token_route = mock.post("/oauth/v2/token").respond(
            200,
            json={
                "access_token": "inter_mock_token_abc123",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "pix.read pix.write",
            },
        )

        client = BancoInterClient()
        token = await client.get_access_token()
        assert token == "inter_mock_token_abc123"

        # Cached token call should not hit network again
        cached = await client.get_access_token()
        assert cached == token
        assert token_route.call_count == 1


@pytest.mark.asyncio
async def test_create_pix_charge_success_tc115():
    """TC-115: Creates immediate PIX charge, returns Copia e Cola and base64 QR Code."""
    with respx.mock(base_url="https://cdpj-sandbox.inter.co") as mock:
        mock.post("/oauth/v2/token").respond(
            200,
            json={"access_token": "tok_123", "expires_in": 3600},
        )
        mock.put("/pix/v2/cob/AGY1234567890abcdef1234567890").respond(
            200,
            json={
                "status": "ATIVA",
                "calendario": {"expiracao": 3600},
                "txid": "AGY1234567890abcdef1234567890",
                "pixCopiaECola": "00020101021226580014br.gov.bcb.pix...",
            },
        )
        mock.get("/pix/v2/cob/AGY1234567890abcdef1234567890/qrcode").respond(
            200,
            json={
                "imagemQrCode": "iVBORw0KGgoAAAANSUhEUgAA...",
                "pixCopiaECola": "00020101021226580014br.gov.bcb.pix...",
            },
        )

        client = BancoInterClient()
        result = await client.create_pix_charge(
            txid="AGY1234567890abcdef1234567890",
            amount_reais=150.00,
            debtor_name="Barbearia Vintage",
            debtor_doc="12345678000199",
            description="Entrada Landing Page",
        )

        assert result.txid == "AGY1234567890abcdef1234567890"
        assert result.status == "ATIVA"
        assert result.amount_reais == 150.00
        assert "0002010102122658" in result.pix_copia_e_cola
        assert "iVBORw0KGgoAAA" in result.qr_code_base64


@pytest.mark.asyncio
async def test_get_pix_charge_status_tc120():
    """TC-120: Queries PIX charge status from Banco Inter."""
    with respx.mock(base_url="https://cdpj-sandbox.inter.co") as mock:
        mock.post("/oauth/v2/token").respond(
            200,
            json={"access_token": "tok_123", "expires_in": 3600},
        )
        mock.get("/pix/v2/cob/AGY_TEST_TXID").respond(
            200,
            json={"txid": "AGY_TEST_TXID", "status": "CONCLUIDA", "valor": {"original": "250.00"}},
        )

        client = BancoInterClient()
        cob = await client.get_pix_charge_status("AGY_TEST_TXID")
        assert cob["status"] == "CONCLUIDA"
        assert cob["valor"]["original"] == "250.00"


@pytest.mark.asyncio
async def test_get_account_balance_tc145():
    """TC-145: Queries current account balance via Banking API."""
    with respx.mock(base_url="https://cdpj-sandbox.inter.co") as mock:
        mock.post("/oauth/v2/token").respond(
            200,
            json={"access_token": "tok_123", "expires_in": 3600},
        )
        mock.get("/banking/v2/saldo").respond(
            200,
            json={"disponivel": 15420.50, "bloqueadoJudicialmente": 0.0},
        )

        client = BancoInterClient()
        balance = await client.get_account_balance()
        assert balance["disponivel"] == 15420.50


@pytest.mark.asyncio
async def test_get_billing_metrics_tc146():
    """TC-146: Consolidates billing metrics and average ticket."""
    with respx.mock(base_url="https://cdpj-sandbox.inter.co") as mock:
        mock.post("/oauth/v2/token").respond(
            200,
            json={"access_token": "tok_123", "expires_in": 3600},
        )
        mock.get("/banking/v2/extrato").respond(
            200,
            json={
                "transacoes": [
                    {"valor": "500.00", "tipoOperacao": "C"},
                    {"valor": "1500.00", "tipoOperacao": "C"},
                ]
            },
        )

        client = BancoInterClient()
        metrics = await client.get_billing_metrics("2026-11-01", "2026-11-13")
        assert metrics["total_reais"] == 2000.00
        assert metrics["transactions_count"] == 2
        assert metrics["average_ticket_reais"] == 1000.00


def test_certificate_validity_check_tc179():
    """TC-179: Checks mTLS certificate on disk."""
    from cert_monitor import check_certificate_validity
    status = check_certificate_validity()
    assert status.exists
    assert status.days_remaining is not None
    assert status.days_remaining > 0


@pytest.mark.asyncio
async def test_inter_api_error_handling_tc219():
    """TC-219: Handles Inter API errors (e.g. 503 Service Unavailable)."""
    with respx.mock(base_url="https://cdpj-sandbox.inter.co") as mock:
        mock.post("/oauth/v2/token").respond(503)

        client = BancoInterClient()
        with pytest.raises(Exception):
            await client.get_access_token()
