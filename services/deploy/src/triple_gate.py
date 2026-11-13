"""Triple Gate Validation Engine for Production Deployments (TC-137, TC-138, TC-139, TC-140)."""

from typing import Any
import aiosqlite
from loguru import logger
from pydantic import BaseModel, Field

from config import settings


class TripleGateCheck(BaseModel):
    """Evaluation result of the 3 cumulative deployment gates."""

    allowed: bool
    finance_cleared: bool
    qa_approved: bool
    security_approved: bool
    override_applied: bool = False
    reasons: list[str] = Field(default_factory=list)


async def validate_triple_gate(
    lead_id: str,
    workspace_id: str,
    db_path: str = settings.DATABASE_PATH,
    force_override: bool = False,
) -> TripleGateCheck:
    """Verifies Finance, QA, and Security gates against SQLite before releasing production deploy."""
    finance_cleared = False
    qa_approved = False
    security_approved = False
    reasons: list[str] = []

    try:
        async with aiosqlite.connect(db_path) as db:
            # 1. Finance Gate (TC-138): PIX transaction must be CONCLUIDA
            async with db.execute(
                "SELECT status FROM pix_transactions WHERE lead_id = ? ORDER BY id DESC LIMIT 1",
                (lead_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == "CONCLUIDA":
                    finance_cleared = True
                else:
                    status_found = row[0] if row else "NENHUMA"
                    reasons.append(f"Finance Gate: PIX payment not cleared (status: {status_found})")

            # 2. QA Gate (TC-137): Deployments QA approval flag must be True
            async with db.execute(
                "SELECT qa_approved FROM deployments WHERE lead_id = ? OR workspace_id = ? ORDER BY id DESC LIMIT 1",
                (lead_id, workspace_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row and (row[0] == 1 or row[0] is True):
                    qa_approved = True
                else:
                    reasons.append("QA Gate: QA homologation test suite not approved")

            # 3. Security Gate (TC-139): Security audit must be PASSED with 0 critical/high
            async with db.execute(
                "SELECT status, critical_count, high_count FROM security_audits WHERE lead_id = ? OR workspace_id = ? ORDER BY id DESC LIMIT 1",
                (lead_id, workspace_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == "PASSED" and row[1] == 0 and row[2] == 0:
                    security_approved = True
                else:
                    reasons.append("Security Gate: Security audit not passed or contains high/critical vulnerabilities")

    except Exception as exc:
        logger.error("Database gate verification error: {err}", err=exc)
        reasons.append(f"Gate lookup error: {str(exc)}")

    all_passed = finance_cleared and qa_approved and security_approved

    if all_passed:
        logger.info("Triple Gate APPROVED for lead {lid} on workspace {ws}", lid=lead_id, ws=workspace_id)
        return TripleGateCheck(
            allowed=True,
            finance_cleared=True,
            qa_approved=True,
            security_approved=True,
            override_applied=False,
            reasons=[],
        )

    # Emergency Override by Joao via Telegram (TC-140)
    if force_override:
        logger.warning(
            "Triple Gate EMERGENCY OVERRIDE applied by Joao for lead {lid} on workspace {ws}",
            lid=lead_id,
            ws=workspace_id,
        )
        return TripleGateCheck(
            allowed=True,
            finance_cleared=finance_cleared,
            qa_approved=qa_approved,
            security_approved=security_approved,
            override_applied=True,
            reasons=reasons,
        )

    logger.warning("Triple Gate BLOCKED deployment for lead {lid}: {reasons}", lid=lead_id, reasons=reasons)
    return TripleGateCheck(
        allowed=False,
        finance_cleared=finance_cleared,
        qa_approved=qa_approved,
        security_approved=security_approved,
        override_applied=False,
        reasons=reasons,
    )
