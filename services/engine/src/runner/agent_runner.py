"""Deterministic ReAct Agent Runner with telemetry extraction and circuit breaker (TC-020, TC-021, TC-038, TC-039)."""

import asyncio
import json
import os
import re
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
from src.services.pricing import get_model_pricing
from src.tools.registry import execute_tool, get_tool_definitions
from src.utils.security import mask_sensitive_data


class AgentProfile(BaseModel):
    """Pydantic model representing a declarative agent profile YAML."""

    agent_id: str
    name: str
    role: str
    model: str = "gemini/gemini-2.5-flash"
    temperature: float = 0.1
    allowed_tools: list[str] = Field(default_factory=list)
    system_prompt: str


def expand_env_vars(text: str) -> str:
    """Expands ${VAR:-default} and ${VAR} patterns using os.environ."""
    pattern = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")

    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    return pattern.sub(replace, text)


def load_agent_profile(agent_id: str, config_dir: Path | None = None) -> AgentProfile:
    """Loads and validates an agent YAML profile from pipeline/ directory (SEC-005)."""
    # SEC-005: Validate slug pattern to prevent directory traversal
    if not re.match(r"^[a-z0-9_\-]+$", agent_id):
        raise ValueError(
            f"Invalid agent_id '{agent_id}'. Slug must match pattern ^[a-z0-9_\\-]+$"
        )

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

    resolved_config_root = config_path.resolve()
    search_files = [
        config_path / "pipeline" / f"{agent_id}.yaml",
        config_path / f"{agent_id}.yaml",
    ]

    yaml_file = next((f for f in search_files if f.exists()), None)
    if yaml_file is None:
        raise FileNotFoundError(f"Agent profile '{agent_id}' not found in {config_path}.")

    # Verify canonical resolution stays within config directory
    try:
        yaml_file.resolve().relative_to(resolved_config_root)
    except ValueError:
        raise ValueError(f"Access denied: Profile for '{agent_id}' escapes authorized config root.")

    try:
        raw_text = yaml_file.read_text(encoding="utf-8")
        expanded_text = expand_env_vars(raw_text)
        data = yaml.safe_load(expanded_text)
        if not isinstance(data, dict):
            raise ValueError(f"Malformed YAML in agent profile '{agent_id}'.")

        # Direct environment overrides (Highest priority for model/temperature)
        env_model_variants = [
            f"MODEL_{agent_id.upper()}",
            f"AGENT_{agent_id.upper()}_MODEL",
            f"MODEL_AGENT_{agent_id.upper()}",
        ]
        for env_key in env_model_variants:
            if env_key in os.environ and os.environ[env_key].strip():
                data["model"] = os.environ[env_key].strip()
                break

        env_temp_variants = [
            f"TEMP_{agent_id.upper()}",
            f"AGENT_{agent_id.upper()}_TEMPERATURE",
        ]
        for env_key in env_temp_variants:
            if env_key in os.environ and os.environ[env_key].strip():
                try:
                    data["temperature"] = float(os.environ[env_key].strip())
                    break
                except ValueError:
                    pass

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
    """Computes exact costs in USD and BRL for a given LLM model via dynamic pricing catalog (SEC-016)."""
    pricing = get_model_pricing(model)
    return pricing.calculate_cost(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        usd_brl_rate=usd_brl_rate,
    )


def estimate_tokens(text: str) -> int:
    """Estimates token count (~4 characters per token)."""
    return max(1, len(text) // 4)


def prune_context_window(messages: list[Any], max_tokens: int = 32000) -> list[Any]:
    """Compacts intermediate conversation history if estimated token count exceeds max_tokens (SEC-012)."""
    total_tokens = sum(
        estimate_tokens(str(getattr(m, "content", "") if not isinstance(m, dict) else m.get("content", "")))
        for m in messages
    )
    if total_tokens <= max_tokens or len(messages) <= 4:
        return messages

    # Keep System Prompt (idx 0) and Initial User prompt (idx 1)
    preserved_prefix = messages[:2]
    # Keep the most recent 2 messages
    preserved_suffix = messages[-2:]

    pruned_msg = {
        "role": "user",
        "content": "[Histórico anterior compactado: mensagens intermediárias podadas para manter a janela de contexto dentro do limite seguro de 32k tokens.]",
    }
    return [*preserved_prefix, pruned_msg, *preserved_suffix]


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
        """Emits an event to the SSE stream callback if registered (SEC-007)."""
        if self.sse_callback is not None:
            try:
                sanitized_data = {}
                for k, v in data.items():
                    if isinstance(v, str):
                        sanitized_data[k] = mask_sensitive_data(v)
                    elif isinstance(v, dict):
                        sanitized_data[k] = {
                            sub_k: (mask_sensitive_data(sub_v) if isinstance(sub_v, str) else sub_v)
                            for sub_k, sub_v in v.items()
                        }
                    else:
                        sanitized_data[k] = v

                await self.sse_callback(event_type=event_type, data=sanitized_data)
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
        consecutive_tool_failures: list[tuple[str, str, str]] = []

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"Run {self.run_id} | Iteration {iteration}/{self.max_iterations}")

            # SEC-012: Prune context window if history exceeds 32k tokens
            messages = prune_context_window(messages, max_tokens=32000)

            # Call LLM via LiteLLM with transient error retries (503 / 429)
            max_llm_retries = 3
            response = None
            last_exc = None
            for attempt in range(1, max_llm_retries + 1):
                try:
                    response = await acompletion(
                        model=self.profile.model,
                        messages=messages,
                        tools=tool_schemas if tool_schemas else None,
                        temperature=self.profile.temperature,
                        api_key=os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY,
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc)
                    is_transient = "503" in err_str or "high demand" in err_str.lower() or "429" in err_str
                    if is_transient and attempt < max_llm_retries:
                        wait_sec = attempt * 3
                        logger.warning(
                            f"Transient LLM error on run {self.run_id} ({exc}). Retrying attempt {attempt}/{max_llm_retries} in {wait_sec}s..."
                        )
                        await asyncio.sleep(wait_sec)
                    else:
                        break

            if response is None:
                exc = last_exc or Exception("Failed to receive LLM response.")
                logger.error(f"LLM API Error on run {self.run_id}: {exc}")
                masked_err = mask_sensitive_data(str(exc))
                await self._emit_event("error", {"iteration": iteration, "error": masked_err})
                async with self.session_factory() as session:
                    stmt = select(AgentRun).where(AgentRun.run_id == self.run_id)
                    run_record = (await session.exec(stmt)).one()
                    run_record.status = RunStatus.FAILED
                    run_record.error_message = masked_err
                    run_record.completed_at = datetime.now(timezone.utc)
                    session.add(run_record)
                    await session.commit()
                return f"Error: LLM invocation failed: {masked_err}"

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
                            content=mask_sensitive_data(thought_text),
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
                                content=mask_sensitive_data(json.dumps({"tool": func_name, "arguments": args})),
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
                                content=mask_sensitive_data(tool_result),
                            )
                        )
                        await session.commit()

                    await self._emit_event(
                        "tool_result",
                        {"iteration": iteration, "tool": func_name, "result": tool_result},
                    )

                    # SEC-012: Circuit breaker for 3 identical consecutive failures
                    is_error = "error" in tool_result.lower()
                    if is_error:
                        consecutive_tool_failures.append((func_name, json.dumps(args, sort_keys=True), tool_result.strip()))
                        if (
                            len(consecutive_tool_failures) >= 3
                            and consecutive_tool_failures[-1] == consecutive_tool_failures[-2] == consecutive_tool_failures[-3]
                        ):
                            logger.warning(
                                f"Circuit Breaker tripped for run {self.run_id}: 3 consecutive identical tool failures on '{func_name}'."
                            )
                            result_summary = f"Execution aborted: Circuit breaker detected 3 identical consecutive failures on tool '{func_name}'."
                            async with self.session_factory() as session:
                                stmt = select(AgentRun).where(AgentRun.run_id == self.run_id)
                                run_record = (await session.exec(stmt)).one()
                                run_record.status = RunStatus.FAILED
                                run_record.error_message = mask_sensitive_data(result_summary)
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
                                "error",
                                {"iteration": iteration, "error": result_summary},
                            )
                            return result_summary
                    else:
                        consecutive_tool_failures.clear()

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
                            content=mask_sensitive_data(result_summary),
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
