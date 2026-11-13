"""Tests for Payment Gateway MCP Server (:3006)."""

from unittest.mock import AsyncMock, MagicMock
import aiosqlite
import pytest

from inter_client import BancoInterClient, PixChargeResult
from mcp_server import create_payment_mcp_server


@pytest.mark.asyncio
async def test_mcp_create_pix_charge_tool(temp_db: str):
    """Executes create_pix_charge via MCP server and verifies DB persistence."""
    mock_client = MagicMock(spec=BancoInterClient)
    mock_client.create_pix_charge = AsyncMock(
        return_value=PixChargeResult(
            txid="AGY_MCP_TEST_TXID",
            status="ATIVA",
            pix_copia_e_cola="00020126580014br.gov.bcb.pix...",
            qr_code_base64="mock_qr_base64_string",
            amount_reais=200.00,
            created_at="2026-11-13T12:00:00Z",
        )
    )

    server = create_payment_mcp_server(inter_client=mock_client, db_path=temp_db)

    res = await server.call_tool(
        "create_pix_charge",
        {
            "lead_id": "barbearia-vintage",
            "amount_reais": 200.00,
            "description": "Entrada Landing Page",
        },
    )

    assert res is not None
    assert len(res.content) > 0

    # Verify DB insertion
    async with aiosqlite.connect(temp_db) as db:
        async with db.execute("SELECT amount_cents, status FROM pix_transactions WHERE lead_id = 'barbearia-vintage'") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 20000
            assert row[1] == "ATIVA"


@pytest.mark.asyncio
async def test_mcp_check_pix_status_tool(temp_db: str):
    """Executes check_pix_status via MCP server querying DB and fallback to API."""
    txid = "AGY_STATUS_TEST"
    async with aiosqlite.connect(temp_db) as db:
        await db.execute(
            "INSERT INTO pix_transactions (txid, amount_cents, status, created_at) VALUES (?, 10000, 'ATIVA', '2026-11-13T10:00:00Z')",
            (txid,),
        )
        await db.commit()

    mock_client = MagicMock(spec=BancoInterClient)
    mock_client.get_pix_charge_status = AsyncMock(return_value={"txid": txid, "status": "CONCLUIDA"})

    server = create_payment_mcp_server(inter_client=mock_client, db_path=temp_db)
    res = await server.call_tool("check_pix_status", {"txid": txid})

    assert res is not None
    assert len(res.content) > 0


@pytest.mark.asyncio
async def test_mcp_balance_and_billing_tools(temp_db: str):
    """Executes get_account_balance and get_billing_metrics via MCP server."""
    mock_client = MagicMock(spec=BancoInterClient)
    mock_client.get_account_balance = AsyncMock(return_value={"disponivel": 50000.00})
    mock_client.get_billing_metrics = AsyncMock(
        return_value={"total_reais": 5000.00, "transactions_count": 5, "average_ticket_reais": 1000.00}
    )

    server = create_payment_mcp_server(inter_client=mock_client, db_path=temp_db)

    res_bal = await server.call_tool("get_account_balance", {})
    assert res_bal is not None

    res_met = await server.call_tool("get_billing_metrics", {"start_date": "2026-11-01", "end_date": "2026-11-13"})
    assert res_met is not None
