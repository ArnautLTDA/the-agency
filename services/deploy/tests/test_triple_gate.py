"""Tests for Triple Gate Enforcement (TC-137, TC-138, TC-139, TC-140)."""

import aiosqlite
import pytest

from triple_gate import validate_triple_gate


@pytest.mark.asyncio
async def test_triple_gate_approved_when_all_pass_tc137(temp_db: str):
    """TC-137: Production deployment allowed when Finance, QA, and Security are all cleared."""
    lead_id = "lead_vintage"
    ws_id = "ws_vintage"

    async with aiosqlite.connect(temp_db) as db:
        # 1. Finance cleared (CONCLUIDA)
        await db.execute(
            "INSERT INTO pix_transactions (txid, lead_id, amount_cents, status, created_at) VALUES ('tx_1', ?, 50000, 'CONCLUIDA', '2026-11-13T10:00:00Z')",
            (lead_id,),
        )
        # 2. QA approved
        await db.execute(
            "INSERT INTO deployments (lead_id, workspace_id, deployment_type, qa_approved, created_at) VALUES (?, ?, 'PREVIEW', 1, '2026-11-13T11:00:00Z')",
            (lead_id, ws_id),
        )
        # 3. Security passed (0 critical, 0 high)
        await db.execute(
            "INSERT INTO security_audits (lead_id, workspace_id, scan_type, status, critical_count, high_count, created_at) VALUES (?, ?, 'FULL', 'PASSED', 0, 0, '2026-11-13T12:00:00Z')",
            (lead_id, ws_id),
        )
        await db.commit()

    gate = await validate_triple_gate(lead_id=lead_id, workspace_id=ws_id, db_path=temp_db)

    assert gate.allowed is True
    assert gate.finance_cleared is True
    assert gate.qa_approved is True
    assert gate.security_approved is True
    assert len(gate.reasons) == 0


@pytest.mark.asyncio
async def test_triple_gate_blocked_when_finance_pending_tc138(temp_db: str):
    """TC-138: Production deployment blocked when PIX payment is pending or missing."""
    lead_id = "lead_unpaid"
    ws_id = "ws_unpaid"

    async with aiosqlite.connect(temp_db) as db:
        # Finance pending (ATIVA)
        await db.execute(
            "INSERT INTO pix_transactions (txid, lead_id, amount_cents, status, created_at) VALUES ('tx_2', ?, 50000, 'ATIVA', '2026-11-13T10:00:00Z')",
            (lead_id,),
        )
        await db.execute(
            "INSERT INTO deployments (lead_id, workspace_id, qa_approved, created_at) VALUES (?, ?, 1, '2026-11-13T11:00:00Z')",
            (lead_id, ws_id),
        )
        await db.execute(
            "INSERT INTO security_audits (lead_id, workspace_id, status, critical_count, high_count, created_at) VALUES (?, ?, 'PASSED', 0, 0, '2026-11-13T12:00:00Z')",
            (lead_id, ws_id),
        )
        await db.commit()

    gate = await validate_triple_gate(lead_id=lead_id, workspace_id=ws_id, db_path=temp_db)

    assert gate.allowed is False
    assert gate.finance_cleared is False
    assert any("Finance Gate" in r for r in gate.reasons)


@pytest.mark.asyncio
async def test_triple_gate_blocked_when_security_audit_failed_tc139(temp_db: str):
    """TC-139: Production deployment blocked when security audit found critical vulnerabilities."""
    lead_id = "lead_vuln"
    ws_id = "ws_vuln"

    async with aiosqlite.connect(temp_db) as db:
        await db.execute(
            "INSERT INTO pix_transactions (txid, lead_id, amount_cents, status, created_at) VALUES ('tx_3', ?, 50000, 'CONCLUIDA', '2026-11-13T10:00:00Z')",
            (lead_id,),
        )
        await db.execute(
            "INSERT INTO deployments (lead_id, workspace_id, qa_approved, created_at) VALUES (?, ?, 1, '2026-11-13T11:00:00Z')",
            (lead_id, ws_id),
        )
        # Security audit failed with 1 critical leak
        await db.execute(
            "INSERT INTO security_audits (lead_id, workspace_id, status, critical_count, high_count, created_at) VALUES (?, ?, 'FAILED', 1, 0, '2026-11-13T12:00:00Z')",
            (lead_id, ws_id),
        )
        await db.commit()

    gate = await validate_triple_gate(lead_id=lead_id, workspace_id=ws_id, db_path=temp_db)

    assert gate.allowed is False
    assert gate.security_approved is False
    assert any("Security Gate" in r for r in gate.reasons)


@pytest.mark.asyncio
async def test_triple_gate_emergency_override_by_joao_tc140(temp_db: str):
    """TC-140: Joao's emergency override bypasses gate blockers with audit trail."""
    lead_id = "lead_emergency"
    ws_id = "ws_emergency"

    # No payment or QA records inserted
    gate = await validate_triple_gate(
        lead_id=lead_id,
        workspace_id=ws_id,
        db_path=temp_db,
        force_override=True,
    )

    assert gate.allowed is True
    assert gate.override_applied is True
    assert len(gate.reasons) > 0  # Still keeps record of what failed
