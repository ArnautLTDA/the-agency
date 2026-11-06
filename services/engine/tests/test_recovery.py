"""Tests for Startup Crash Recovery of Orphaned Tasks (TC-006, BDD-02)."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlmodel import select

from src.models.database import create_db_and_tables, get_async_engine, get_session_factory
from src.models.entities import AgentRun, RunStatus
from src.services.recovery import run_crash_recovery


@pytest.mark.asyncio
async def test_tc006_crash_recovery_orphaned_tasks():
    """TC-006: Identifies tasks left in 'running' state and marks them as INTERRUPTED_BY_CRASH."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_recovery.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        session_factory = get_session_factory(engine)

        run_id_orphaned = uuid.uuid4()
        run_id_completed = uuid.uuid4()
        run_id_queued = uuid.uuid4()
        now = datetime.now(timezone.utc)

        async with session_factory() as session:
            # Task that was running when server crashed
            session.add(
                AgentRun(
                    run_id=run_id_orphaned,
                    agent_id="homologation_agent",
                    task="Orphaned job",
                    status=RunStatus.RUNNING,
                    created_at=now,
                    updated_at=now,
                )
            )
            # Normal completed task
            session.add(
                AgentRun(
                    run_id=run_id_completed,
                    agent_id="homologation_agent",
                    task="Completed job",
                    status=RunStatus.COMPLETED,
                    created_at=now,
                    updated_at=now,
                )
            )
            # Normal queued task
            session.add(
                AgentRun(
                    run_id=run_id_queued,
                    agent_id="homologation_agent",
                    task="Queued job",
                    status=RunStatus.QUEUED,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

        # Run recovery routine
        async with session_factory() as session:
            recovered_count = await run_crash_recovery(session)
            assert recovered_count == 1

        # Verify state in database
        async with session_factory() as session:
            res_orphaned = (await session.exec(select(AgentRun).where(AgentRun.run_id == run_id_orphaned))).one()
            assert res_orphaned.status == RunStatus.INTERRUPTED_BY_CRASH
            assert res_orphaned.completed_at is not None
            assert "interrupted" in res_orphaned.error_message.lower()

            res_completed = (await session.exec(select(AgentRun).where(AgentRun.run_id == run_id_completed))).one()
            assert res_completed.status == RunStatus.COMPLETED

            res_queued = (await session.exec(select(AgentRun).where(AgentRun.run_id == run_id_queued))).one()
            assert res_queued.status == RunStatus.QUEUED

        await engine.dispose()
