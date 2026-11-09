"""Tests for Cognitive Hardening, Context Pruning, Loop Circuit Breakers and Masking (TC-060 to TC-063)."""

import json
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from src.models.database import create_db_and_tables, get_async_engine, get_session_factory
from src.models.entities import ActionType, AgentRun, AuditLog, RunStatus
from src.runner.agent_runner import (
    AgentRunner,
    calculate_token_costs,
    estimate_tokens,
    prune_context_window,
)
from src.services.pricing import get_model_pricing
from src.utils.security import mask_sensitive_data


def test_tc060_sliding_window_context_pruning():
    """TC-060 / SEC-012: Context is pruned when exceeding 32k tokens, preserving prompt and user goal."""
    system_msg = {"role": "system", "content": "You are a software engineer."}
    user_goal = {"role": "user", "content": "Implement auth middleware."}

    # Generate massive intermediate messages (~40,000 tokens)
    middle_msgs = [
        {"role": "assistant", "content": "Thinking step " + "x" * 40000},
        {"role": "tool", "content": "Tool output " + "y" * 40000},
        {"role": "assistant", "content": "Thinking step 2 " + "z" * 40000},
        {"role": "tool", "content": "Tool output 2 " + "w" * 40000},
    ]
    recent_msgs = [
        {"role": "assistant", "content": "Recent thought."},
        {"role": "tool", "content": "Recent output."},
    ]

    all_messages = [system_msg, user_goal, *middle_msgs, *recent_msgs]
    assert sum(estimate_tokens(str(m["content"])) for m in all_messages) > 32000

    pruned = prune_context_window(all_messages, max_tokens=32000)

    # Must preserve System Prompt at index 0 and Goal at index 1
    assert pruned[0]["role"] == "system"
    assert pruned[0]["content"] == "You are a software engineer."
    assert pruned[1]["role"] == "user"
    assert pruned[1]["content"] == "Implement auth middleware."

    # Index 2 should be the compaction notice
    assert "compactado" in pruned[2]["content"].lower()

    # Suffix should preserve most recent messages
    assert pruned[-1]["content"] == "Recent output."
    assert pruned[-2]["content"] == "Recent thought."


@pytest.mark.asyncio
async def test_tc061_loop_repetition_circuit_breaker(temp_workspace: Path):
    """TC-061 / SEC-012: Loop with 3 consecutive identical tool failures trips circuit breaker with status FAILED."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "cb_test.db"
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
                    task="Repetitive loop test",
                    workspace_dir=str(temp_workspace),
                    status=RunStatus.QUEUED,
                )
            )
            await session.commit()

        # Mock acompletion to return identical tool call to read non-existent file
        mock_tc = MagicMock()
        mock_tc.id = "call_123"
        mock_tc.function.name = "read_file"
        mock_tc.function.arguments = json.dumps({"path": "non_existent.txt"})

        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_choice.message.tool_calls = [mock_tc]

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 20

        runner = AgentRunner(
            run_id=run_id,
            agent_id="homologation_agent",
            task="Repetitive loop test",
            workspace_dir=temp_workspace,
            session_factory=session_factory,
            max_iterations=10,
        )

        with patch("src.runner.agent_runner.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            result = await runner.run()

            assert "circuit breaker" in result.lower()

            async with session_factory() as session:
                stmt = select(AgentRun).where(AgentRun.run_id == run_id)
                run_rec = (await session.exec(stmt)).one()
                assert run_rec.status == RunStatus.FAILED
                assert "circuit breaker" in run_rec.error_message.lower()

        await engine.dispose()


def test_tc062_api_key_masking_in_errors_and_logs():
    """TC-062 / SEC-007: API keys from Gemini, OpenAI and Anthropic are sanitized."""
    # Test Google Gemini Key
    gemini_raw = "Error 400: API_KEY_INVALID AIzaSyD9xYZ1234567890abcdefghijklmnopqrst uvw"
    masked_gemini = mask_sensitive_data(gemini_raw)
    assert "AIza" in masked_gemini
    assert "...***..." in masked_gemini
    assert "SyD9xYZ" not in masked_gemini

    # Test OpenAI Key
    openai_raw = "AuthenticationError: sk-proj1234567890abcdefghijklmnopqrstuvw"
    masked_openai = mask_sensitive_data(openai_raw)
    assert "sk-p...***..." in masked_openai
    assert "1234567890abcdef" not in masked_openai

    # Test Anthropic Key
    anthropic_raw = "401 Unauthorized sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456"
    masked_anthropic = mask_sensitive_data(anthropic_raw)
    assert "sk-a...***..." in masked_anthropic


def test_tc063_dynamic_model_pricing_lookup():
    """TC-063 / SEC-016: Precision rates for Gemini Pro, Flash and Claude reflect official price schedules."""
    usd_brl_rate = 5.80

    # Gemini Flash pricing ($0.075 / 1M prompt, $0.30 / 1M completion)
    flash_usd, flash_brl = calculate_token_costs(
        model="gemini/gemini-2.5-flash",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        cached_tokens=0,
        usd_brl_rate=usd_brl_rate,
    )
    assert flash_usd == pytest.approx(0.375, rel=1e-3)
    assert flash_brl == pytest.approx(0.375 * 5.80, rel=1e-3)

    # Gemini Pro pricing ($1.25 / 1M prompt, $5.00 / 1M completion)
    pro_usd, pro_brl = calculate_token_costs(
        model="gemini-2.5-pro",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        cached_tokens=0,
        usd_brl_rate=usd_brl_rate,
    )
    assert pro_usd == pytest.approx(6.25, rel=1e-3)
    assert pro_brl == pytest.approx(6.25 * 5.80, rel=1e-3)

    # Claude 3.5 Sonnet pricing ($3.00 / 1M prompt, $15.00 / 1M completion)
    claude_usd, _ = calculate_token_costs(
        model="claude-3-5-sonnet",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        cached_tokens=0,
        usd_brl_rate=usd_brl_rate,
    )
    assert claude_usd == pytest.approx(18.00, rel=1e-3)
