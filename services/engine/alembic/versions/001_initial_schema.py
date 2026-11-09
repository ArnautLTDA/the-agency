"""Initial database schema migration (SEC-019).

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agent_runs
    op.create_table(
        'agent_runs',
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('task', sa.String(), nullable=False),
        sa.Column('workspace_dir', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('iterations', sa.Integer(), nullable=False),
        sa.Column('max_iterations', sa.Integer(), nullable=False),
        sa.Column('result_summary', sa.String(), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('total_prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('total_completion_tokens', sa.Integer(), nullable=False),
        sa.Column('total_cached_tokens', sa.Integer(), nullable=False),
        sa.Column('total_cost_usd', sa.Float(), nullable=False),
        sa.Column('total_cost_brl', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('run_id'),
    )
    op.create_index(op.f('ix_agent_runs_run_id'), 'agent_runs', ['run_id'], unique=False)
    op.create_index(op.f('ix_agent_runs_agent_id'), 'agent_runs', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agent_runs_status'), 'agent_runs', ['status'], unique=False)
    op.create_index(op.f('ix_agent_runs_created_at'), 'agent_runs', ['created_at'], unique=False)

    # 2. agent_messages
    op.create_table(
        'agent_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('from_agent', sa.String(), nullable=False),
        sa.Column('to_agent', sa.String(), nullable=False),
        sa.Column('message_type', sa.String(), nullable=False),
        sa.Column('priority', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('correlation_id', sa.String(), nullable=True),
        sa.Column('requires_ack', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_messages_from_agent'), 'agent_messages', ['from_agent'], unique=False)
    op.create_index(op.f('ix_agent_messages_to_agent'), 'agent_messages', ['to_agent'], unique=False)
    op.create_index(op.f('ix_agent_messages_message_type'), 'agent_messages', ['message_type'], unique=False)
    op.create_index(op.f('ix_agent_messages_priority'), 'agent_messages', ['priority'], unique=False)
    op.create_index(op.f('ix_agent_messages_timestamp'), 'agent_messages', ['timestamp'], unique=False)
    op.create_index(op.f('ix_agent_messages_correlation_id'), 'agent_messages', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_agent_messages_status'), 'agent_messages', ['status'], unique=False)

    # 3. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_logs_run_id'), 'audit_logs', ['run_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_agent_id'), 'audit_logs', ['agent_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_action_type'), 'audit_logs', ['action_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)

    # 4. token_metrics
    op.create_table(
        'token_metrics',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False),
        sa.Column('completion_tokens', sa.Integer(), nullable=False),
        sa.Column('cached_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('cost_brl', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_token_metrics_run_id'), 'token_metrics', ['run_id'], unique=False)
    op.create_index(op.f('ix_token_metrics_agent_id'), 'token_metrics', ['agent_id'], unique=False)
    op.create_index(op.f('ix_token_metrics_model'), 'token_metrics', ['model'], unique=False)
    op.create_index(op.f('ix_token_metrics_timestamp'), 'token_metrics', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_table('token_metrics')
    op.drop_table('audit_logs')
    op.drop_table('agent_messages')
    op.drop_table('agent_runs')
