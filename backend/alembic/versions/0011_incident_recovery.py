"""add incident persistence recovery outbox

Revision ID: 0011_incident_recovery
Revises: 0010_pacs_incidents
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_incident_recovery"
down_revision: str | None = "0010_pacs_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incident_persistence_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transfer_job_id", sa.Uuid(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=False),
        sa.Column("redacted_error", sa.String(200), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["transfer_job_id"], ["transfer_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transfer_job_id", name="uq_incident_outbox_transfer_job"),
    )
    op.create_index(
        "ix_incident_persistence_outbox_transfer_job",
        "incident_persistence_outbox",
        ["transfer_job_id"],
        unique=False,
    )
    op.create_index(
        "ix_incident_persistence_outbox_status",
        "incident_persistence_outbox",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("incident_persistence_outbox")
