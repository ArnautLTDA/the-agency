"""Database Maintenance, Data Retention Purge and Vacuum routines (SEC-024)."""

from datetime import datetime, timedelta, timezone
from loguru import logger
from sqlalchemy import text
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import get_settings
from src.models.entities import AuditLog, TokenMetric


async def purge_old_records(
    session: AsyncSession,
    retention_days: int | None = None,
) -> dict[str, int]:
    """Purges historical token metrics and audit logs older than retention_days (SEC-024)."""
    settings = get_settings()
    days = retention_days if retention_days is not None else settings.RETENTION_DAYS

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    logger.info(f"Running maintenance purge for records older than {cutoff_date.isoformat()} ({days} days)...")

    # 1. Purge TokenMetrics
    stmt_metrics = delete(TokenMetric).where(TokenMetric.timestamp < cutoff_date)
    res_metrics = await session.exec(stmt_metrics)
    purged_metrics = res_metrics.rowcount if hasattr(res_metrics, "rowcount") else 0

    # 2. Purge AuditLogs
    stmt_logs = delete(AuditLog).where(AuditLog.timestamp < cutoff_date)
    res_logs = await session.exec(stmt_logs)
    purged_logs = res_logs.rowcount if hasattr(res_logs, "rowcount") else 0

    await session.commit()

    # 3. Incremental vacuum to reclaim pages and defragment SQLite file
    try:
        await session.exec(text("PRAGMA incremental_vacuum;"))
    except Exception as exc:
        logger.debug(f"Incremental vacuum notice: {exc}")

    stats = {
        "retention_days": days,
        "purged_metrics": purged_metrics,
        "purged_audit_logs": purged_logs,
        "total_purged": purged_metrics + purged_logs,
    }
    logger.info(f"Database maintenance complete: {stats}")
    return stats
