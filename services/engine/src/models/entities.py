"""SQLModel database entities for The Agency Engine."""

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Column, JSON, String
from sqlmodel import Field, SQLModel


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    INTERRUPTED_BY_CRASH = "INTERRUPTED_BY_CRASH"
    PAUSED_CIRCUIT_BREAKER = "PAUSED_CIRCUIT_BREAKER"


class MessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    TASK_COMPLETED = "task_completed"
    IMPROVEMENT_REQUEST = "improvement_request"
    QA_FAILURE = "qa_failure"
    PENTEST_REPORT = "pentest_report"
    STATUS_UPDATE = "status_update"
    ESCALATION = "escalation"
    METRIC_REPORT = "metric_report"
    CONTEXT_SHARE = "context_share"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"


class MessagePriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MessageStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionType(str, Enum):
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FINAL_RESPONSE = "final_response"
    ERROR = "error"


class AgentRun(SQLModel, table=True):
    """Tracks an agent execution run lifecycle and accumulated telemetry."""

    __tablename__ = "agent_runs"

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    agent_id: str = Field(index=True, description="Agent profile identifier slug")
    task: str = Field(description="Task prompt or instruction")
    workspace_dir: str = Field(default="workspaces/clients/default")
    status: RunStatus = Field(default=RunStatus.QUEUED, index=True)
    iterations: int = Field(default=0)
    max_iterations: int = Field(default=25)
    result_summary: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    total_prompt_tokens: int = Field(default=0)
    total_completion_tokens: int = Field(default=0)
    total_cached_tokens: int = Field(default=0)
    total_cost_usd: float = Field(default=0.0)
    total_cost_brl: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = Field(default=None)


class AgentMessage(SQLModel, table=True):
    """Inter-agent message protocol queue and archive."""

    __tablename__ = "agent_messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    from_agent: str = Field(index=True)
    to_agent: str = Field(index=True)  # agent_id or 'broadcast'
    message_type: MessageType = Field(index=True)
    priority: MessagePriority = Field(default=MessagePriority.MEDIUM, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    correlation_id: str | None = Field(default=None, index=True)
    requires_ack: bool = Field(default=False)
    status: MessageStatus = Field(default=MessageStatus.PENDING, index=True)


class AuditLog(SQLModel, table=True):
    """Immutable traceability log for agent reasoning and tool usage."""

    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    run_id: uuid.UUID = Field(index=True)
    agent_id: str = Field(index=True)
    action_type: ActionType = Field(index=True)
    content: str = Field(description="Content, payload, thought or error details")


class TokenMetric(SQLModel, table=True):
    """Detailed financial telemetry for every LLM turn in USD and BRL."""

    __tablename__ = "token_metrics"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    run_id: uuid.UUID = Field(index=True)
    agent_id: str = Field(index=True)
    model: str = Field(index=True)
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    cached_tokens: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    cost_brl: float = Field(default=0.0)
