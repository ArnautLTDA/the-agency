"""Phase 1 microservices and gateways database schema migration.

Revision ID: 002_phase_1_schemas
Revises: 001_initial_schema
Create Date: 2026-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_phase_1_schemas'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. leads
    op.create_table(
        'leads',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('niche', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=False),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('reviews_count', sa.Integer(), nullable=True),
        sa.Column('instagram_url', sa.String(), nullable=True),
        sa.Column('extracted_data', sa.JSON(), nullable=True),
        sa.Column('stage', sa.String(), nullable=False, server_default='MINED'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone'),
    )
    op.create_index(op.f('ix_leads_phone'), 'leads', ['phone'], unique=True)
    op.create_index(op.f('ix_leads_niche'), 'leads', ['niche'], unique=False)
    op.create_index(op.f('ix_leads_stage'), 'leads', ['stage'], unique=False)
    op.create_index(op.f('ix_leads_created_at'), 'leads', ['created_at'], unique=False)

    # 2. security_incidents
    op.create_table(
        'security_incidents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('sender_jid', sa.String(), nullable=False),
        sa.Column('raw_message', sa.String(), nullable=False),
        sa.Column('threat_category', sa.String(), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('action_taken', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_security_incidents_sender_jid'), 'security_incidents', ['sender_jid'], unique=False)
    op.create_index(op.f('ix_security_incidents_threat_category'), 'security_incidents', ['threat_category'], unique=False)
    op.create_index(op.f('ix_security_incidents_created_at'), 'security_incidents', ['created_at'], unique=False)

    # 3. pix_transactions
    op.create_table(
        'pix_transactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('txid', sa.String(), nullable=False),
        sa.Column('lead_id', sa.String(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='ATIVA'),
        sa.Column('pix_copia_e_cola', sa.String(), nullable=False),
        sa.Column('qr_code_base64', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('txid'),
    )
    op.create_index(op.f('ix_pix_transactions_txid'), 'pix_transactions', ['txid'], unique=True)
    op.create_index(op.f('ix_pix_transactions_lead_id'), 'pix_transactions', ['lead_id'], unique=False)
    op.create_index(op.f('ix_pix_transactions_status'), 'pix_transactions', ['status'], unique=False)
    op.create_index(op.f('ix_pix_transactions_created_at'), 'pix_transactions', ['created_at'], unique=False)

    # 4. telegram_audit_logs
    op.create_table(
        'telegram_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('command', sa.String(), nullable=True),
        sa.Column('payload', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_telegram_audit_logs_direction'), 'telegram_audit_logs', ['direction'], unique=False)
    op.create_index(op.f('ix_telegram_audit_logs_command'), 'telegram_audit_logs', ['command'], unique=False)
    op.create_index(op.f('ix_telegram_audit_logs_created_at'), 'telegram_audit_logs', ['created_at'], unique=False)

    # 5. telegram_approvals
    op.create_table(
        'telegram_approvals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.String(), nullable=True),
        sa.Column('decision_type', sa.String(), nullable=False),
        sa.Column('details', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_telegram_approvals_lead_id'), 'telegram_approvals', ['lead_id'], unique=False)
    op.create_index(op.f('ix_telegram_approvals_decision_type'), 'telegram_approvals', ['decision_type'], unique=False)
    op.create_index(op.f('ix_telegram_approvals_status'), 'telegram_approvals', ['status'], unique=False)
    op.create_index(op.f('ix_telegram_approvals_requested_at'), 'telegram_approvals', ['requested_at'], unique=False)

    # 6. git_audit_logs
    op.create_table(
        'git_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('agent_role', sa.String(), nullable=False),
        sa.Column('branch', sa.String(), nullable=False),
        sa.Column('commit_hash', sa.String(), nullable=True),
        sa.Column('message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_git_audit_logs_workspace_id'), 'git_audit_logs', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_git_audit_logs_action'), 'git_audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_git_audit_logs_agent_role'), 'git_audit_logs', ['agent_role'], unique=False)
    op.create_index(op.f('ix_git_audit_logs_created_at'), 'git_audit_logs', ['created_at'], unique=False)

    # 7. deployments
    op.create_table(
        'deployments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('deployment_type', sa.String(), nullable=False),
        sa.Column('deployment_url', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('qa_approved', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('security_approved', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('payment_cleared', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_deployments_lead_id'), 'deployments', ['lead_id'], unique=False)
    op.create_index(op.f('ix_deployments_workspace_id'), 'deployments', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_deployments_deployment_type'), 'deployments', ['deployment_type'], unique=False)
    op.create_index(op.f('ix_deployments_status'), 'deployments', ['status'], unique=False)
    op.create_index(op.f('ix_deployments_created_at'), 'deployments', ['created_at'], unique=False)

    # 8. security_audits
    op.create_table(
        'security_audits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('scan_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('critical_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('high_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('report_summary', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_security_audits_lead_id'), 'security_audits', ['lead_id'], unique=False)
    op.create_index(op.f('ix_security_audits_workspace_id'), 'security_audits', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_security_audits_scan_type'), 'security_audits', ['scan_type'], unique=False)
    op.create_index(op.f('ix_security_audits_status'), 'security_audits', ['status'], unique=False)
    op.create_index(op.f('ix_security_audits_created_at'), 'security_audits', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('security_audits')
    op.drop_table('deployments')
    op.drop_table('git_audit_logs')
    op.drop_table('telegram_approvals')
    op.drop_table('telegram_audit_logs')
    op.drop_table('pix_transactions')
    op.drop_table('security_incidents')
    op.drop_table('leads')
