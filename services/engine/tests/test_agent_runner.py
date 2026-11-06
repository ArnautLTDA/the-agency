"""Tests for Agent Runner, ReAct Loop, Circuit Breaker, and Metrics Extraction (TC-009, TC-010, TC-020, TC-021, TC-038, TC-039)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlmodel import select

from src.models.database import create_db_and_tables, get_async_engine, get_session_factory
from src.models.entities import ActionType, AgentRun, AuditLog, RunStatus, TokenMetric
from src.runner.agent_runner import AgentProfile, AgentRunner, load_agent_profile


def test_tc009_load_valid_agent_profile():
    """TC-009: Loads valid agent YAML profiles correctly into memory."""
    profile = load_agent_profile("homologation_agent")
    assert profile.agent_id == "homologation_agent"
    assert profile.model == "gemini/gemini-2.5-flash"
    assert "write_file" in profile.allowed_tools
    assert "patch_file" in profile.allowed_tools


def test_tc010_load_invalid_agent_profile():
    """TC-010: Attempting to load missing or malformed agent profile raises FileNotFoundError or ValueError."""
    with pytest.raises((FileNotFoundError, ValueError)):
        load_agent_profile("non_existent_ghost_agent")


@pytest.mark.asyncio
async def test_tc020_tc038_tc039_react_loop_and_metrics():
    """TC-020, TC-038, TC-039: Full ReAct loop executing tool, capturing tokens, and computing USD/BRL costs."""
    with TemporaryDirectory() as tmp_dir:
        workspace_dir = Path(tmp_dir) / "workspace"
        workspace_dir.mkdir()
        db_path = Path(tmp_dir) / "test_react.db"
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
                    task="Create hello.txt file",
                    workspace_dir=str(workspace_dir),
                    status=RunStatus.QUEUED,
                )
            )
            await session.commit()

        # Mock LiteLLM responses for Turn 1 (Tool Call) and Turn 2 (Final Response)
        mock_func_1 = MagicMock()
        mock_func_1.name = "write_file"
        mock_func_1.arguments = '{"path": "hello.txt", "content": "Hello from Agent"}'
        mock_choice_1 = MagicMock()
        mock_choice_1.message.content = "I will create hello.txt using write_file."
        mock_choice_1.message.tool_calls = [
            MagicMock(
                id="call_1",
                function=mock_func_1,
            )
        ]
        mock_resp_1 = MagicMock()
        mock_resp_1.choices = [mock_choice_1]
        mock_resp_1._hidden_params = {
            "original_response": {
                "usage_metadata": {
                    "prompt_token_count": 1500,
                    "cached_content_token_count": 1000,
                    "candidates_token_count": 350,
                }
            }
        }

        mock_choice_2 = MagicMock()
        mock_choice_2.message.content = "File hello.txt has been created successfully."
        mock_choice_2.message.tool_calls = None
        mock_resp_2 = MagicMock()
        mock_resp_2.choices = [mock_choice_2]
        mock_resp_2._hidden_params = {
            "original_response": {
                "usage_metadata": {
                    "prompt_token_count": 1800,
                    "cached_content_token_count": 1000,
                    "candidates_token_count": 50,
                }
            }
        }

        runner = AgentRunner(
            run_id=run_id,
            agent_id="homologation_agent",
            task="Create hello.txt file",
            workspace_dir=workspace_dir,
            session_factory=session_factory,
            max_iterations=10,
        )

        with patch("src.runner.agent_runner.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = [mock_resp_1, mock_resp_2]
            summary = await runner.run()

            assert "created successfully" in summary.lower()
            assert (workspace_dir / "hello.txt").exists()
            assert (workspace_dir / "hello.txt").read_text(encoding="utf-8") == "Hello from Agent"

        # Verify DB state
        async with session_factory() as session:
            # 1. Run completed
            run_record = (await session.exec(select(AgentRun).where(AgentRun.run_id == run_id))).one()
            assert run_record.status == RunStatus.COMPLETED
            assert run_record.iterations == 2
            assert run_record.total_prompt_tokens == 3300
            assert run_record.total_completion_tokens == 400
            assert run_record.total_cost_usd > 0
            assert run_record.total_cost_brl > 0

            # 2. Token metrics recorded
            metrics = (await session.exec(select(TokenMetric).where(TokenMetric.run_id == run_id))).all()
            assert len(metrics) == 2

            # 3. Audit logs recorded
            audits = (await session.exec(select(AuditLog).where(AuditLog.run_id == run_id))).all()
            action_types = [a.action_type for a in audits]
            assert ActionType.THOUGHT in action_types
            assert ActionType.TOOL_CALL in action_types
            assert ActionType.TOOL_RESULT in action_types
            assert ActionType.FINAL_RESPONSE in action_types

        await engine.dispose()


@pytest.mark.asyncio
async def test_tc021_circuit_breaker():
    """TC-021: Loop halts safely with PAUSED_CIRCUIT_BREAKER when max_iterations is reached."""
    with TemporaryDirectory() as tmp_dir:
        workspace_dir = Path(tmp_dir) / "workspace"
        workspace_dir.mkdir()
        db_path = Path(tmp_dir) / "test_cb.db"
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
                    task="Infinite loop task",
                    workspace_dir=str(workspace_dir),
                    status=RunStatus.QUEUED,
                )
            )
            await session.commit()

        # Mock an LLM that keeps calling list_directory in an infinite loop
        mock_func_cb = MagicMock()
        mock_func_cb.name = "list_directory"
        mock_func_cb.arguments = '{"path": "."}'
        mock_choice = MagicMock()
        mock_choice.message.content = "Still thinking..."
        mock_choice.message.tool_calls = [
            MagicMock(
                id="call_loop",
                function=mock_func_cb,
            )
        ]
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp._hidden_params = {"original_response": {}}

        runner = AgentRunner(
            run_id=run_id,
            agent_id="homologation_agent",
            task="Infinite loop task",
            workspace_dir=workspace_dir,
            session_factory=session_factory,
            max_iterations=3,  # Circuit breaker threshold set to 3 for testing
        )

        with patch("src.runner.agent_runner.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_resp
            summary = await runner.run()

            assert "circuit breaker" in summary.lower()

        async with session_factory() as session:
            run_record = (await session.exec(select(AgentRun).where(AgentRun.run_id == run_id))).one()
            assert run_record.status == RunStatus.PAUSED_CIRCUIT_BREAKER
            assert run_record.iterations == 3

        await engine.dispose()
