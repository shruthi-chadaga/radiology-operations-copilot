"""add persisted PACS incident evidence

Revision ID: 0010_pacs_incidents
Revises: 0009_pacs_study_enrichment
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_pacs_incidents"
down_revision: str | None = "0009_pacs_study_enrichment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CATEGORY_VALUES = (
    "'no_incident', 'connectivity', 'identity_mismatch', 'count_mismatch', "
    "'unauthorized', 'configuration', 'destructive_action', 'non_allowlisted_action', 'unknown'"
)


def upgrade() -> None:
    op.create_table(
        "pacs_incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_number", sa.String(64), nullable=False),
        sa.Column("transfer_job_id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("destination_node_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approval_state", sa.String(32), nullable=False),
        sa.Column("retry_candidate", sa.Boolean(), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rule_code", sa.String(80), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("redacted_summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(80), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("last_failure_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["transfer_job_id"], ["transfer_jobs.id"]),
        sa.ForeignKeyConstraint(["study_id"], ["pacs_studies.id"]),
        sa.ForeignKeyConstraint(["source_node_id"], ["pacs_nodes.id"]),
        sa.ForeignKeyConstraint(["destination_node_id"], ["pacs_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_number"),
        sa.UniqueConstraint("transfer_job_id", name="uq_pacs_incident_transfer_job"),
        sa.CheckConstraint(
            f"category IN ({_CATEGORY_VALUES})",
            name="ck_pacs_incident_category",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_pacs_incident_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'pending_approval', 'resolved')",
            name="ck_pacs_incident_status",
        ),
        sa.CheckConstraint(
            "approval_state IN ('pending', 'approved', 'rejected')",
            name="ck_pacs_incident_approval_state",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_pacs_incident_confidence",
        ),
        sa.CheckConstraint("last_failure_count >= 1", name="ck_pacs_incident_failure_count"),
    )
    for column in (
        "transfer_job_id",
        "study_id",
        "category",
        "severity",
        "status",
        "approval_state",
    ):
        op.create_index(f"ix_pacs_incidents_{column}", "pacs_incidents", [column], unique=False)


def downgrade() -> None:
    op.drop_table("pacs_incidents")
