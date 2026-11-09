"""Tests for Database Hardening, Alembic Migrations, Audit Recovery and Retention Purge (TC-069, TC-070, TC-074)."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import text
from sqlmodel import select

from alembic import command
from alembic.config import Config
from src.models.database import create_db_and_tables, get_async_engine, get_session_factory
from src.models.entities import ActionType, AgentRun, AuditLog, RunStatus, TokenMetric
from src.services.maintenance import purge_old_records
from src.services.recovery import run_crash_recovery


def test_tc069_alembic_upgrade_head_on_boot():
    """TC-069 / SEC-019: Alembic migration upgrades schema cleanly creating alembic_version table."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "alembic_boot.db"
        alembic_ini_path = Path("alembic.ini") if Path("alembic.ini").exists() else Path("services/engine/alembic.ini")
        assert alembic_ini_path.exists(), "alembic.ini must exist in project"

        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

        # Run migration
        command.upgrade(alembic_cfg, "head")

        # Verify alembic_version and entities tables exist in database
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "alembic_version" in tables
        assert "agent_runs" in tables
        assert "audit_logs" in tables
        assert "token_metrics" in tables
        assert "agent_messages" in tables


@pytest.mark.asyncio
async def test_tc070_recovery_writes_audit_log():
    """TC-070 / SEC-020: Startup crash recovery records formal AuditLog record when marking task as interrupted."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "recovery_audit.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        session_factory = get_session_factory(engine)

        run_id = uuid.uuid4()
        async with session_factory() as session:
            session.add(
                AgentRun(
                    run_id=run_id,
                    agent_id="homologation_agent",
                    task="Orphaned crash task",
                    status=RunStatus.RUNNING,
                )
            )
            await session.commit()

        # Run recovery
        async with session_factory() as session:
            count = await run_crash_recovery(session)
            assert count == 1

        # Verify AuditLog has the recovery entry
        async with session_factory() as session:
            stmt = select(AuditLog).where(AuditLog.run_id == run_id)
            logs = (await session.exec(stmt)).all()
            assert len(logs) >= 1
            recovery_log = next(log for log in logs if log.action_type == ActionType.SYSTEM_EVENT)
            assert "crash" in recovery_log.content.lower()

        await engine.dispose()


@pytest.mark.asyncio
async def test_tc074_retention_purge_and_vacuum():
    """TC-074 / SEC-024: Purge deletes records older than RETENTION_DAYS and executes incremental vacuum."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "retention_test.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        session_factory = get_session_factory(engine)

        run_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        old_timestamp = now - timedelta(days=45)
        fresh_timestamp = now - timedelta(days=5)

        async with session_factory() as session:
            # Add old and fresh TokenMetrics
            session.add(
                TokenMetric(
                    id=uuid.uuid4(),
                    timestamp=old_timestamp,
                    run_id=run_id,
                    agent_id="agent",
                    model="model",
                    cost_usd=0.01,
                    cost_brl=0.05,
                )
            )
            session.add(
                TokenMetric(
                    id=uuid.uuid4(),
                    timestamp=fresh_timestamp,
                    run_id=run_id,
                    agent_id="agent",
                    model="model",
                    cost_usd=0.02,
                    cost_brl=0.10,
                )
            )

            # Add old and fresh AuditLogs
            session.add(
                AuditLog(
                    id=uuid.uuid4(),
                    timestamp=old_timestamp,
                    run_id=run_id,
                    agent_id="agent",
                    action_type=ActionType.THOUGHT,
                    content="Old thought",
                )
            )
            session.add(
                AuditLog(
                    id=uuid.uuid4(),
                    timestamp=fresh_timestamp,
                    run_id=run_id,
                    agent_id="agent",
                    action_type=ActionType.THOUGHT,
                    content="Fresh thought",
                )
            )
            await session.commit()

        # Run purge with 30 days retention
        async with session_factory() as session:
            stats = await purge_old_records(session=session, retention_days=30)
            assert stats["purged_metrics"] == 1
            assert stats["purged_audit_logs"] == 1
            assert stats["total_purged"] == 2

        # Verify only fresh records remain
        async with session_factory() as session:
            remaining_metrics = (await session.exec(select(TokenMetric))).all()
            assert len(remaining_metrics) == 1
            assert remaining_metrics[0].cost_usd == 0.02

            remaining_logs = (await session.exec(select(AuditLog))).all()
            assert len(remaining_logs) == 1
            assert remaining_logs[0].content == "Fresh thought"

        await engine.dispose()
