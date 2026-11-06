"""Deterministic ReAct Agent Runner with telemetry extraction and circuit breaker (TC-020, TC-021, TC-038, TC-039)."""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from litellm import acompletion
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import get_settings
from src.models.entities import ActionType, AgentRun, AuditLog, RunStatus, TokenMetric
from src.services.currency import get_currency_service
from src.tools.registry import execute_tool, get_tool_definitions


class AgentProfile(BaseModel):
    """Pydantic model representing a declarative agent profile YAML."""

    agent_id: str
    name: str
    role: str
    model: str = "gemini/gemini-2.5-flash"
    temperature: float = 0.1
    allowed_tools: list[str] = Field(default_factory=list)
    system_prompt: str


def load_agent_profile(agent_id: str, config_dir: Path | None = None) -> AgentProfile:
    """Loads and validates an agent YAML profile from council/ or pipeline/ directory."""
    if config_dir is None:
        # Search relative to project root or services/engine
        candidates = [
            Path("config/agents"),
            Path("services/engine/config/agents"),
            Path(__file__).resolve().parent.parent.parent / "config" / "agents",
        ]
        config_path = next((c for c in candidates if c.exists()), Path("config/agents"))
    else:
        config_path = config_dir

    search_files = [
        config_path / "pipeline" / f"{agent_id}.yaml",
        config_path / "council" / f"{agent_id}.yaml",
        config_path / f"{agent_id}.yaml",
    ]

    yaml_file = next((f for f in search_files if f.exists()), None)
    if yaml_file is None:
        raise FileNotFoundError(f"Agent profile '{agent_id}' not found in {config_path}.")

    try:
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Malformed YAML in agent profile '{agent_id}'.")
        return AgentProfile(**data)
    except Exception as exc:
        logger.error(f"Failed to load agent profile '{agent_id}': {exc}")
        raise ValueError(f"Invalid agent profile schema for '{agent_id}': {exc}") from exc


def calculate_token_costs(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int,
    usd_brl_rate: float,
) -> tuple[float, float]:
    """Computes exact costs in USD and BRL for a given LLM model."""
    # Gemini Flash pricing baseline:
    # Prompt: $0.075 / 1M tokens ($0.000000075 / token)
    # Cached: $0.01875 / 1M tokens ($0.00000001875 / token)
    # Completion: $0.30 / 1M tokens ($0.00000030 / token)
    non_cached_prompt = max(0, prompt_tokens - cached_tokens)
    cost_prompt = non_cached_prompt * 0.000000075
    cost_cached = cached_tokens * 0.00000001875
    cost_completion = completion_tokens * 0.00000030

    cost_usd = round(cost_prompt + cost_cached + cost_completion, 8)
    cost_brl = round(cost_usd * usd_brl_rate, 8)
    return cost_usd, cost_brl


class AgentRunner:
    """Async ReAct loop runner with telemetry extraction, sandbox execution and circuit breaker."""

    def __init__(
        self,
        run_id: uuid.UUID,
        agent_id: str,
        task: str,
        workspace_dir: Path,
        session_factory: sessionmaker,
        max_iterations: int = 25,
        sse_callback: Any = None,
    ):
        self.run_id = run_id
        self.agent_id = agent_id
        self.task = task
        self.workspace_dir = Path(workspace_dir).resolve()
        self.session_factory = session_factory
        self.max_iterations = max_iterations
        self.sse_callback = sse_callback
        self.profile = load_agent_profile(agent_id)

    async def _emit_event(self, event_type: str, data: dict[str, Any]):
        """Emits an event to the SSE stream callback if registered."""
        if self.sse_callback is not None:
            try:
                await self.sse_callback(event_type=event_type, data=data)
            except Exception as exc:
                logger.warning(f"SSE event emission failed: {exc}")

    async def run(self) -> str:
        """Executes the deterministic ReAct reasoning loop."""
        settings = get_settings()
        currency_service = get_currency_service()
        usd_brl_rate = await currency_service.get_usd_brl_rate()
        tool_schemas = get_tool_definitions(self.profile.allowed_tools)

        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            stmt = select(AgentRun).where(AgentRun.run_id == self.run_id)
            run_record = (await session.exec(stmt)).one_or_none()
            if run_record:
                run_record.status = RunStatus.RUNNING
                run_record.updated_at = now
                session.add(run_record)
                await session.commit()

        # Build initial messages
        system_prompt = (
            f"{self.profile.system_prompt}\n\n"
            f"Context:\n"
            f"- Workspace Directory: {self.workspace_dir}\n"
            f"- Current Date (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- Maximum Iterations Allowed: {self.max_iterations}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.task},
        ]

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0
        total_cost_usd = 0.0
        total_cost_brl = 0.0
        result_summary = "Execution finished without final message."

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"Run {self.run_id} | Iteration {iteration}/{self.max_iterations}")

            # Call LLM via LiteLLM
            try:
                response = await acompletion(
                    model=self.profile.model,
                    messages=messages,
                    tools=tool_schemas if tool_schemas else None,
                    temperature=self.profile.temperature,
                    api_key=settings.GEMINI_API_KEY,
                )
            except Exception as exc:
                logger.error(f"LLM API Error on run {self.run_id}: {exc}")
                await self._emit_event("error", {"iteration": iteration, "error": str(exc)})
                async with self.session_factory() as session:
                    stmt = select(AgentRun).where(AgentRun.run_id == self.run_id)
                    run_record = (await session.exec(stmt)).one()
                    run_record.status = RunStatus.FAILED
                    run_record.error_message = str(exc)
                    run_record.completed_at = datetime.now(timezone.utc)
                    session.add(run_record)
                    await session.commit()
                return f"Error: LLM invocation failed: {exc}"

            # TC-038 & TC-039: Extract authentic token metrics
            prompt_tokens = 0
            completion_tokens = 0
            cached_tokens = 0

            hidden_params = getattr(response, "_hidden_params", {}) or {}
            orig_resp = hidden_params.get("original_response") if isinstance(hidden_params, dict) else None
            if isinstance(orig_resp, dict) and "usage_metadata" in orig_resp:
                meta = orig_resp["usage_metadata"]
                prompt_tokens = meta.get("prompt_token_count", 0)
                cached_tokens = meta.get("cached_content_token_count", 0)
                completion_tokens = meta.get("candidates_token_count", 0)
            elif hasattr(response, "usage") and response.usage:
                p_val = getattr(response.usage, "prompt_tokens", 0)
                c_val = getattr(response.usage, "completion_tokens", 0)
                prompt_tokens = p_val if isinstance(p_val, (int, float)) else 0
                completion_tokens = c_val if isinstance(c_val, (int, float)) else 0
                details = getattr(response.usage, "prompt_tokens_details", None)
                if isinstance(details, dict):
                    cached_tokens = details.get("cached_tokens", 0)

            # Ensure all values are genuine ints
            prompt_tokens = int(prompt_tokens) if isinstance(prompt_tokens, (int, float)) else 0
            completion_tokens = int(completion_tokens) if isinstance(completion_tokens, (int, float)) else 0
            cached_tokens = int(cached_tokens) if isinstance(cached_tokens, (int, float)) else 0

            cost_usd, cost_brl = calculate_token_costs(
                model=self.profile.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                usd_brl_rate=usd_brl_rate,
            )

            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens
            total_cached_tokens += cached_tokens
            total_cost_usd += cost_usd
            total_cost_brl += cost_brl

            # Record turn metric and telemetry
            turn_now = datetime.now(timezone.utc)
            async with self.session_factory() as session:
                session.add(
                    TokenMetric(
                        id=uuid.uuid4(),
                        timestamp=turn_now,
                        run_id=self.run_id,
                        agent_id=self.agent_id,
                        model=self.profile.model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cached_tokens=cached_tokens,
                        cost_usd=cost_usd,
                        cost_brl=cost_brl,
                    )
                )
                await session.commit()

            await self._emit_event(
                "token_usage",
                {
                    "iteration": iteration,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost_usd,
                    "cost_brl": cost_brl,
                },
            )

            choice = response.choices[0]
            message = choice.message
            thought_text = message.content or ""

            if thought_text:
                async with self.session_factory() as session:
                    session.add(
                        AuditLog(
                            id=uuid.uuid4(),
                            timestamp=turn_now,
                            run_id=self.run_id,
                            agent_id=self.agent_id,
                            action_type=ActionType.THOUGHT,
                            content=thought_text,
                        )
                    )
                    await session.commit()
                await self._emit_event("thought", {"iteration": iteration, "thought": thought_text})

            # Check for tool calls
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                # Append assistant tool call message to history
                messages.append(message)

                for tc in tool_calls:
                    func_name = str(tc.function.name)
                    raw_args = tc.function.arguments
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args = {}

                    logger.info(f"Tool call on run {self.run_id}: {func_name}({args})")
                    await self._emit_event(
                        "tool_call",
                        {"iteration": iteration, "tool": func_name, "arguments": args},
                    )

                    async with self.session_factory() as session:
                        session.add(
                            AuditLog(
                                id=uuid.uuid4(),
                                timestamp=datetime.now(timezone.utc),
                                run_id=self.run_id,
                                agent_id=self.agent_id,
                                action_type=ActionType.TOOL_CALL,
                                content=json.dumps({"tool": func_name, "arguments": args}),
                            )
                        )
                        # Execute tool
                        tool_result = await execute_tool(
                            name=func_name,
                            arguments=args,
                            workspace_dir=self.workspace_dir,
                            session=session,
                            from_agent=self.agent_id,
                        )
                        logger.info(f"Tool {func_name} result: {tool_result}")
                        session.add(
                            AuditLog(
                                id=uuid.uuid4(),
                                timestamp=datetime.now(timezone.utc),
                                run_id=self.run_id,
                                agent_id=self.agent_id,
                                action_type=ActionType.TOOL_RESULT,
                                content=tool_result,
                            )
                        )
                        await session.commit()

                    await self._emit_event(
                        "tool_result",
                        {"iteration": iteration, "tool": func_name, "result": tool_result},
                    )

                    # Append tool result to conversation history for next turn
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": func_name,
                        "content": tool_result,
                    })

                # Check circuit breaker before next loop iteration
                if iteration >= self.max_iterations:
                    logger.warning(
                        f"Circuit Breaker tripped for run {self.run_id} after {iteration} iterations."
                    )
                    result_summary = "Execution paused: Circuit breaker limit reached."
                    async with self.session_factory() as session:
                        stmt = select(AgentRun).where(AgentRun.run_id == self.run_id)
                        run_record = (await session.exec(stmt)).one()
                        run_record.status = RunStatus.PAUSED_CIRCUIT_BREAKER
                        run_record.iterations = iteration
                        run_record.total_prompt_tokens = total_prompt_tokens
                        run_record.total_completion_tokens = total_completion_tokens
                        run_record.total_cached_tokens = total_cached_tokens
                        run_record.total_cost_usd = total_cost_usd
                        run_record.total_cost_brl = total_cost_brl
                        run_record.result_summary = result_summary
                        run_record.completed_at = datetime.now(timezone.utc)
                        session.add(run_record)
                        await session.commit()
                    return result_summary

            else:
                # No tool calls: final response received!
                result_summary = thought_text or "Task completed."
                logger.info(f"Run {self.run_id} completed successfully in {iteration} turns.")

                async with self.session_factory() as session:
                    session.add(
                        AuditLog(
                            id=uuid.uuid4(),
                            timestamp=datetime.now(timezone.utc),
                            run_id=self.run_id,
                            agent_id=self.agent_id,
                            action_type=ActionType.FINAL_RESPONSE,
                            content=result_summary,
                        )
                    )
                    stmt = select(AgentRun).where(AgentRun.run_id == self.run_id)
                    run_record = (await session.exec(stmt)).one()
                    run_record.status = RunStatus.COMPLETED
                    run_record.iterations = iteration
                    run_record.total_prompt_tokens = total_prompt_tokens
                    run_record.total_completion_tokens = total_completion_tokens
                    run_record.total_cached_tokens = total_cached_tokens
                    run_record.total_cost_usd = total_cost_usd
                    run_record.total_cost_brl = total_cost_brl
                    run_record.result_summary = result_summary
                    run_record.completed_at = datetime.now(timezone.utc)
                    session.add(run_record)
                    await session.commit()

                await self._emit_event(
                    "task_completed",
                    {"result": result_summary, "iterations": iteration},
                )
                return result_summary

        return result_summary
