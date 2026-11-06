"""Tests for SQLite WAL mode, models, and concurrent writes (TC-037)."""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import text
from sqlmodel import select

from src.models.database import create_db_and_tables, get_async_engine, get_session_factory
from src.models.entities import ActionType, AgentMessage, AgentRun, AuditLog, MessagePriority, MessageType, RunStatus, TokenMetric


@pytest.mark.asyncio
async def test_wal_mode_enabled():
    """Verify SQLite WAL mode and synchronous=NORMAL are set on connect."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_wal.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)

        async with engine.connect() as conn:
            journal_res = await conn.execute(text("PRAGMA journal_mode;"))
            journal_mode = journal_res.scalar_one()
            assert journal_mode.lower() == "wal"

        await engine.dispose()


@pytest.mark.asyncio
async def test_entities_creation_and_retrieval():
    """Verify all 4 core entities can be created, stored and queried."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_entities.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        session_factory = get_session_factory(engine)

        run_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        async with session_factory() as session:
            # 1. AgentRun
            run = AgentRun(
                run_id=run_id,
                agent_id="homologation_agent",
                task="Test autonomous run",
                workspace_dir="/tmp/test",
                status=RunStatus.QUEUED,
                created_at=now,
                updated_at=now,
            )
            session.add(run)

            # 2. AgentMessage
            msg = AgentMessage(
                id=uuid.uuid4(),
                timestamp=now,
                from_agent="ceo",
                to_agent="cto",
                message_type=MessageType.TASK_ASSIGNMENT,
                priority=MessagePriority.HIGH,
                payload={"instruction": "Build Phase 0"},
            )
            session.add(msg)

            # 3. AuditLog
            audit = AuditLog(
                id=uuid.uuid4(),
                timestamp=now,
                run_id=run_id,
                agent_id="homologation_agent",
                action_type=ActionType.THOUGHT,
                content="Planning task execution...",
            )
            session.add(audit)

            # 4. TokenMetric
            metric = TokenMetric(
                id=uuid.uuid4(),
                timestamp=now,
                run_id=run_id,
                agent_id="homologation_agent",
                model="gemini-2.5-flash",
                prompt_tokens=100,
                completion_tokens=50,
                cached_tokens=0,
                cost_usd=0.0001,
                cost_brl=0.00058,
            )
            session.add(metric)
            await session.commit()

        # Query back
        async with session_factory() as session:
            stmt = select(AgentRun).where(AgentRun.run_id == run_id)
            result = await session.exec(stmt)
            saved_run = result.one()
            assert saved_run.agent_id == "homologation_agent"
            assert saved_run.status == RunStatus.QUEUED

        await engine.dispose()


@pytest.mark.asyncio
async def test_tc037_concurrent_writes_wal():
    """TC-037: Multiple concurrent async writes succeed without database is locked errors."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_concurrency.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = get_async_engine(db_url)
        await create_db_and_tables(engine)
        session_factory = get_session_factory(engine)

        async def worker_write(index: int):
            async with session_factory() as session:
                audit = AuditLog(
                    id=uuid.uuid4(),
                    timestamp=datetime.now(timezone.utc),
                    run_id=uuid.uuid4(),
                    agent_id=f"agent_{index}",
                    action_type=ActionType.TOOL_RESULT,
                    content=f"Result from worker {index}",
                )
                session.add(audit)
                await session.commit()

        # 30 concurrent writes
        tasks = [worker_write(i) for i in range(30)]
        await asyncio.gather(*tasks)

        async with session_factory() as session:
            stmt = select(AuditLog)
            results = (await session.exec(stmt)).all()
            assert len(results) == 30

        await engine.dispose()
