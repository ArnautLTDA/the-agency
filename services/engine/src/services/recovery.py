"""Startup Crash Recovery routine for orphaned running tasks (TC-006, BDD-02)."""

from datetime import datetime, timezone
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.entities import AgentRun, RunStatus


async def run_crash_recovery(session: AsyncSession) -> int:
    """Scans for runs left in 'running' state and updates them to INTERRUPTED_BY_CRASH."""
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
