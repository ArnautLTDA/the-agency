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
    SYSTEM_EVENT = "system_event"


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


# =============================================================================
# Fase 1: Entidades Soberanas de Microsserviços e Borda
# =============================================================================

class LeadStage(str, Enum):
    MINED = "MINED"
    DEMO_READY = "DEMO_READY"
    OUTREACH = "OUTREACH"
    NEGOTIATING = "NEGOTIATING"
    CONTRATO_ASSINADO = "CONTRATO_ASSINADO"
    DEV = "DEV"
    QA = "QA"
    HOMOLOGATING = "HOMOLOGATING"
    PROD = "PROD"


class Lead(SQLModel, table=True):
    """Lead central business entity discovered and progressed through the agency funnel."""

    __tablename__ = "leads"

    id: str = Field(primary_key=True, description="Unique lead slug or UUID")
    name: str = Field(nullable=False, description="Commercial name")
    niche: str = Field(nullable=False, index=True, description="Market vertical")
    phone: str = Field(nullable=False, unique=True, index=True, description="Normalized E.164 phone")
    address: str | None = Field(default=None)
    rating: float | None = Field(default=None)
    reviews_count: int | None = Field(default=None)
    instagram_url: str | None = Field(default=None)
    extracted_data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    stage: str = Field(default=LeadStage.MINED.value, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SecurityIncident(SQLModel, table=True):
    """Audit log of malicious, prompt injection, or jailbreak attempts intercepted at edge."""

    __tablename__ = "security_incidents"

    id: int | None = Field(default=None, primary_key=True)
    sender_jid: str = Field(nullable=False, index=True)
    raw_message: str = Field(nullable=False)
    threat_category: str = Field(nullable=False, index=True)
    risk_score: float = Field(nullable=False)
    action_taken: str = Field(nullable=False)  # SILENT_DROP, BLOCKED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class PixStatus(str, Enum):
    ATIVA = "ATIVA"
    CONCLUIDA = "CONCLUIDA"
    EXPIRADA = "EXPIRADA"
    CANCELADA = "CANCELADA"
    LIQUIDACAO_DIVERGENTE = "LIQUIDACAO_DIVERGENTE"


class PixTransaction(SQLModel, table=True):
    """Dynamic PIX charges and settlement confirmations via Banco Inter mTLS."""

    __tablename__ = "pix_transactions"

    id: int | None = Field(default=None, primary_key=True)
    txid: str = Field(nullable=False, unique=True, index=True)
    lead_id: str = Field(nullable=False, index=True)
    amount_cents: int = Field(nullable=False)
    status: str = Field(default=PixStatus.ATIVA.value, index=True)
    pix_copia_e_cola: str = Field(nullable=False)
    qr_code_base64: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    paid_at: datetime | None = Field(default=None)


class TelegramAuditLog(SQLModel, table=True):
    """Auditing of all inbound commands from Joao and outbound alerts."""

    __tablename__ = "telegram_audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    direction: str = Field(nullable=False, index=True)  # OUTBOUND_ALERT, INBOUND_COMMAND
    command: str | None = Field(default=None, index=True)
    payload: str = Field(nullable=False)
    status: str = Field(nullable=False)  # SENT, EXECUTED, REJECTED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TelegramApproval(SQLModel, table=True):
    """Traceability for interactive human decisions with 24-hour expiration timeout."""

    __tablename__ = "telegram_approvals"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: str | None = Field(default=None, index=True)
    decision_type: str = Field(nullable=False, index=True)  # DEPLOY_PRODUCTION, BUDGET_OVERRIDE, CALIBRATION_STEP
    details: str = Field(nullable=False)
    status: str = Field(default=ApprovalStatus.PENDING.value, index=True)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    decided_at: datetime | None = Field(default=None)


class GitAuditLog(SQLModel, table=True):
    """Version control and commit audit trail with granular agent author attribution."""

    __tablename__ = "git_audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    workspace_id: str = Field(nullable=False, index=True)
    action: str = Field(nullable=False, index=True)  # COMMIT, BRANCH_CREATE, PR_CREATE, PUSH
    agent_role: str = Field(nullable=False, index=True)  # dev, qa, security
    branch: str = Field(nullable=False)
    commit_hash: str | None = Field(default=None)
    message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class Deployment(SQLModel, table=True):
    """Cloud deployments history, Preview URLs and Production Triple Gate verification."""

    __tablename__ = "deployments"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: str = Field(nullable=False, index=True)
    workspace_id: str = Field(nullable=False, index=True)
    deployment_type: str = Field(nullable=False, index=True)  # PREVIEW_DEMO, PRODUCTION
    deployment_url: str = Field(nullable=False)
    status: str = Field(nullable=False, index=True)  # BUILDING, READY, FAILED, BLOCKED_BY_GATE
    qa_approved: bool = Field(default=False)
    security_approved: bool = Field(default=False)
    payment_cleared: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class SecurityAudit(SQLModel, table=True):
    """Static and dynamic security scan results (SonarQube, Gitleaks, Semgrep, Trivy, Nuclei)."""

    __tablename__ = "security_audits"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: str = Field(nullable=False, index=True)
    workspace_id: str = Field(nullable=False, index=True)
    scan_type: str = Field(nullable=False, index=True)  # SONARQUBE, GITLEAKS, SEMGREP, TRIVY, NUCLEI
    status: str = Field(nullable=False, index=True)  # PASSED, FAILED, WARNING
    critical_count: int = Field(default=0)
    high_count: int = Field(default=0)
    report_summary: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

