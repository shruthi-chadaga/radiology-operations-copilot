"""add incident approval controls and bounded outbox evidence

Revision ID: 0016_incident_approval_controls
Revises: 0015_imaging_correction_pending
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_incident_approval_controls"
down_revision: str | None = "0015_imaging_correction_pending"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "incident_persistence_outbox",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "incident_persistence_outbox",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_table(
        "incident_remediation_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("requested_action", sa.String(64), nullable=False),
        sa.Column("proposer_id", sa.String(64), nullable=False),
        sa.Column("proposer_role", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["incident_id"], ["pacs_incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "requested_action = 'RETRY_TRANSFER'",
            name="ck_incident_proposal_action",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_incident_proposal_status",
        ),
    )
    op.create_index(
        "ix_incident_remediation_proposals_incident_id",
        "incident_remediation_proposals",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_incident_remediation_proposals_proposer_id",
        "incident_remediation_proposals",
        ["proposer_id"],
        unique=False,
    )
    op.create_index(
        "ix_incident_remediation_proposals_status",
        "incident_remediation_proposals",
        ["status"],
        unique=False,
    )
    op.create_table(
        "incident_remediation_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("approver_id", sa.String(64), nullable=False),
        sa.Column("approver_role", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["incident_remediation_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", name="uq_incident_approval_proposal"),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_incident_approval_decision",
        ),
    )
    op.create_index(
        "ix_incident_remediation_approvals_proposal_id",
        "incident_remediation_approvals",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        "ix_incident_remediation_approvals_approver_id",
        "incident_remediation_approvals",
        ["approver_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("incident_remediation_approvals")
    op.drop_table("incident_remediation_proposals")
    op.drop_column("incident_persistence_outbox", "last_error")
    op.drop_column("incident_persistence_outbox", "completed_at")
