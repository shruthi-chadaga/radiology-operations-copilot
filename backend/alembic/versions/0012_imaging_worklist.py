"""add imaging workspace worklist projection

Revision ID: 0012_imaging_worklist
Revises: 0011_incident_recovery
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_imaging_worklist"
down_revision: str | None = "0011_incident_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "imaging_worklist_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=True),
        sa.Column("pacs_patient_id", sa.String(64), nullable=False),
        sa.Column("pacs_study_id", sa.Uuid(), nullable=True),
        sa.Column("appointment_id", sa.Uuid(), nullable=True),
        sa.Column("accession_number", sa.String(64), nullable=False),
        sa.Column("modality", sa.String(16), nullable=True),
        sa.Column("study_description", sa.String(240), nullable=True),
        sa.Column("workflow_status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("assigned_reader_id", sa.String(64), nullable=True),
        sa.Column("report_status", sa.String(24), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.ForeignKeyConstraint(["pacs_study_id"], ["pacs_studies.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["synthetic_patients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id", name="uq_imaging_worklist_appointment"),
        sa.UniqueConstraint("pacs_study_id", name="uq_imaging_worklist_pacs_study"),
    )
    for column in (
        "patient_id",
        "pacs_patient_id",
        "pacs_study_id",
        "appointment_id",
        "accession_number",
        "modality",
        "workflow_status",
        "priority",
        "assigned_reader_id",
    ):
        op.create_index(
            f"ix_imaging_worklist_items_{column}",
            "imaging_worklist_items",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("imaging_worklist_items")
