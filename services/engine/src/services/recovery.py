"""Startup Crash Recovery routine for orphaned running tasks (TC-006, SEC-020)."""

import uuid
from datetime import datetime, timezone
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.entities import ActionType, AgentRun, AuditLog, RunStatus


async def run_crash_recovery(session: AsyncSession) -> int:
    """Scans for runs left in 'running' state and updates them to INTERRUPTED_BY_CRASH with AuditLog (SEC-020)."""
    stmt = select(AgentRun).where(AgentRun.status == RunStatus.RUNNING)
    result = await session.exec(stmt)
    orphaned_runs = result.all()

    now = datetime.now(timezone.utc)
    count = 0
    for run in orphaned_runs:
        run.status = RunStatus.INTERRUPTED_BY_CRASH
        run.completed_at = now
        run.updated_at = now
        run.error_message = (
            "Task was interrupted unexpectedly by server shutdown or crash."
        )
        session.add(run)

        # SEC-020: Register formal AuditLog entry for recovered crash
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            timestamp=now,
            run_id=run.run_id,
            agent_id=run.agent_id,
            action_type=ActionType.SYSTEM_EVENT,
            content=f"Crash Recovery: Task was marked as {RunStatus.INTERRUPTED_BY_CRASH} after unexpected server restart.",
        )
        session.add(audit_entry)

        count += 1
        logger.warning(
            f"Crash Recovery: Run {run.run_id} marked as {RunStatus.INTERRUPTED_BY_CRASH}"
        )

    if count > 0:
        await session.commit()
        logger.info(f"Crash Recovery complete: {count} orphaned runs updated.")
    else:
        logger.info("Crash Recovery sweep complete: 0 orphaned runs found.")

    return count
