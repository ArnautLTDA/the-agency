"""Audit logging to SQLite pipeline.db git_audit_logs table."""

from datetime import datetime, timezone
from pathlib import Path
import aiosqlite
from loguru import logger

from config import settings


async def log_git_action(
    workspace_id: str,
    action: str,
    agent_role: str,
    branch: str,
    commit_hash: str | None = None,
    message: str | None = None,
) -> None:
    """Records git operation to git_audit_logs table asynchronously."""
    db_file = Path(settings.DB_PATH)
    if not db_file.exists():
        logger.debug("Database file {db} not found, skipping git audit log entry", db=db_file)
        return

    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(str(db_file)) as db:
            await db.execute(
                """
                INSERT INTO git_audit_logs (workspace_id, action, agent_role, branch, commit_hash, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (workspace_id, action, agent_role, branch, commit_hash, message, now),
            )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to record git audit log: {err}", err=exc)
