"""Native MCP Server registering financial PIX tools (:3006)."""

from datetime import datetime, timezone
from typing import Any
import uuid
import aiosqlite
from loguru import logger
from mcp.server.mcpserver import MCPServer

from config import settings
from inter_client import BancoInterClient


def create_payment_mcp_server(
    inter_client: BancoInterClient | None = None,
    db_path: str = settings.DATABASE_PATH,
) -> MCPServer:
    """Builds and configures the payment-gateway MCP server instance."""
    server = MCPServer(
        name="payment-gateway",
        version="0.1.0",
        instructions="Official Agency Banco Inter Payment Gateway MCP Server",
    )
    client = inter_client or BancoInterClient()

    @server.tool(
        name="create_pix_charge",
        description="Creates an immediate PIX charge via Banco Inter mTLS and returns Copia e Cola and QR Code (TC-115).",
    )
    async def create_pix_charge(
        lead_id: str,
        amount_reais: float,
        description: str = "Entrada do Projeto - The Agency",
        debtor_name: str = "Cliente Agency",
        debtor_doc: str = "00000000000",
    ) -> dict[str, Any]:
        # Generate valid 32-char alphanumeric txid
        txid = f"AGY{uuid.uuid4().hex[:29]}"

        charge = await client.create_pix_charge(
            txid=txid,
            amount_reais=amount_reais,
            debtor_name=debtor_name,
            debtor_doc=debtor_doc,
            description=description,
        )

        amount_cents = int(round(amount_reais * 100))
        now_iso = datetime.now(timezone.utc).isoformat()

        # Persist to database
        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    """
                    INSERT INTO pix_transactions (txid, lead_id, amount_cents, status, pix_copia_e_cola, qr_code_base64, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        txid,
                        lead_id,
                        amount_cents,
                        charge.status,
                        charge.pix_copia_e_cola,
                        charge.qr_code_base64,
                        now_iso,
                    ),
                )
                await db.commit()
            logger.info("Persisted PIX charge for lead {lid} with txid {txid}", lid=lead_id, txid=txid)
        except Exception as exc:
            logger.error("Failed to persist PIX transaction into database: {err}", err=exc)

        return {
            "txid": txid,
            "lead_id": lead_id,
            "status": charge.status,
            "amount_reais": amount_reais,
            "amount_cents": amount_cents,
            "pix_copia_e_cola": charge.pix_copia_e_cola,
            "qr_code_base64": charge.qr_code_base64,
        }

    @server.tool(
        name="check_pix_status",
        description="Queries the current status of a PIX charge by txid (TC-120).",
    )
    async def check_pix_status(txid: str) -> dict[str, Any]:
        status_info = {"txid": txid, "status": "DESCONHECIDO"}

        # Check DB first
        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    "SELECT status, amount_cents, paid_at FROM pix_transactions WHERE txid = ?",
                    (txid,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        status_info["status"] = row[0]
                        status_info["amount_cents"] = row[1]
                        status_info["paid_at"] = row[2]
        except Exception as exc:
            logger.debug("Database lookup error for txid {txid}: {err}", txid=txid, err=exc)

        # If still ATIVA, check with Inter API for latest status
        if status_info["status"] in ("ATIVA", "DESCONHECIDO"):
            try:
                cob_data = await client.get_pix_charge_status(txid)
                current_status = cob_data.get("status", status_info["status"])
                status_info["status"] = current_status
            except Exception as api_err:
                logger.debug("Inter API status check error for {txid}: {err}", txid=txid, err=api_err)

        return status_info

    @server.tool(
        name="get_account_balance",
        description="Returns current account balance in Banco Inter (TC-145).",
    )
    async def get_account_balance() -> dict[str, Any]:
        return await client.get_account_balance()

    @server.tool(
        name="get_billing_metrics",
        description="Consolidates billing metrics, transaction count and average ticket for period (TC-146).",
    )
    async def get_billing_metrics(start_date: str, end_date: str) -> dict[str, Any]:
        return await client.get_billing_metrics(start_date, end_date)

    return server
