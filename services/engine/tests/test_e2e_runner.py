"""End-to-End Real Live Homologation Test against Google Gemini API (Phase 0 Acceptance Criteria 5.2)."""

import os
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlmodel import select

from src.config import Settings
from src.models.database import create_db_and_tables, get_async_engine, get_session_factory
from src.models.entities import ActionType, AgentRun, AuditLog, RunStatus, TokenMetric
from src.runner.agent_runner import AgentRunner


@pytest.mark.asyncio
async def test_live_e2e_homologation_agent_with_gemini():
    """Live E2E test verifying homologation agent with real Gemini API and Docker sandbox."""
    # Read real key from .env directly, overriding conftest placeholder
    env_file = Path(".env") if Path(".env").exists() else Path("services/engine/.env")
    real_key = None
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                real_key = line.split("=", 1)[1].strip()
                break

    if not real_key or real_key.startswith("test_"):
        pytest.skip("Valid GEMINI_API_KEY not configured for live E2E test.")

    os.environ["GEMINI_API_KEY"] = real_key
    from src.config import get_settings
    get_settings.cache_clear()

    with TemporaryDirectory() as tmp_dir:
        workspace_dir = Path(tmp_dir) / "client_workspace"
        workspace_dir.mkdir()
        db_path = Path(tmp_dir) / "live_e2e.db"
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
                    task=(
                        "Siga rigorosamente estes 2 passos no workspace:\n"
                        "1. Use a ferramenta 'write_file' para criar um arquivo 'calc.py' contendo exatamente:\n"
                        "def somar(a, b):\n"
                        "    return a + b\n"
                        "2. Use a ferramenta 'patch_file' para alterar cirurgicamente 'return a + b' para 'return a * b'.\n"
                        "3. Responda com a palavra 'CONCLUIDO'."
                    ),
                    workspace_dir=str(workspace_dir),
                    status=RunStatus.QUEUED,
                    max_iterations=10,
                )
            )
            await session.commit()

        events_stream = []

        async def sse_callback(event_type: str, data: dict):
            events_stream.append((event_type, data))

        runner = AgentRunner(
            run_id=run_id,
            agent_id="homologation_agent",
            task=(
                "Siga rigorosamente estes 2 passos no workspace:\n"
                "1. Use a ferramenta 'write_file' para criar um arquivo 'calc.py' contendo exatamente:\n"
                "def somar(a, b):\n"
                "    return a + b\n"
                "2. Use a ferramenta 'patch_file' para alterar cirurgicamente 'return a + b' para 'return a * b'.\n"
                "3. Responda com a palavra 'CONCLUIDO'."
            ),
            workspace_dir=workspace_dir,
            session_factory=session_factory,
            max_iterations=10,
            sse_callback=sse_callback,
        )

        try:
            summary = await runner.run()
        except Exception as exc:
            # If the provided key is restricted or encounters quota/network issues, report cleanly
            pytest.fail(f"Live Gemini E2E execution failed: {exc}")

        # 1. Verification of created and patched file
        target_file = workspace_dir / "calc.py"
        assert target_file.exists(), "calc.py should have been created by agent"
        file_content = target_file.read_text(encoding="utf-8")
        assert "return a * b" in file_content, "calc.py should have been surgically patched"

        # 2. Verification of Database Records
        async with session_factory() as session:
            run_record = (await session.exec(select(AgentRun).where(AgentRun.run_id == run_id))).one()
            assert run_record.status == RunStatus.COMPLETED
            assert run_record.iterations >= 2
            assert run_record.total_prompt_tokens > 0
            assert run_record.total_completion_tokens > 0
            assert run_record.total_cost_usd > 0
            assert run_record.total_cost_brl > 0

            # Token metrics
            metrics = (await session.exec(select(TokenMetric).where(TokenMetric.run_id == run_id))).all()
            assert len(metrics) >= 2

            # Audit logs
            audits = (await session.exec(select(AuditLog).where(AuditLog.run_id == run_id))).all()
            action_types = [a.action_type for a in audits]
            assert ActionType.TOOL_CALL in action_types
            assert ActionType.TOOL_RESULT in action_types

        # 3. Verification of SSE stream events
        event_names = [e[0] for e in events_stream]
        assert "tool_call" in event_names
        assert "tool_result" in event_names
        assert "task_completed" in event_names

        await engine.dispose()
