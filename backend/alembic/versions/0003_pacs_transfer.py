"""PACS inventory transfer and reconciliation

Revision ID: 0003_pacs_transfer
Revises: 0002_scheduling
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_pacs_transfer"
down_revision: str | None = "0002_scheduling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pacs_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("node_type", sa.String(24), nullable=False),
        sa.Column("base_url", sa.String(300), nullable=False),
        sa.Column("dicom_ae_title", sa.String(32), nullable=False),
        sa.Column("dicom_host", sa.String(160), nullable=False),
        sa.Column("dicom_port", sa.Integer(), nullable=False),
        sa.Column("adapter_key", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_health_status", sa.String(24), nullable=True),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("adapter_key"),
    )
    op.create_index("ix_pacs_nodes_node_type", "pacs_nodes", ["node_type"], unique=False)

    op.create_table(
        "pacs_health_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("redacted_error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["pacs_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pacs_health_checks_node_id", "pacs_health_checks", ["node_id"], unique=False
    )

    op.create_table(
        "pacs_studies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("orthanc_study_id", sa.String(80), nullable=False),
        sa.Column("study_instance_uid", sa.String(128), nullable=False),
        sa.Column("accession_number", sa.String(64), nullable=False),
        sa.Column("patient_id", sa.String(64), nullable=False),
        sa.Column("study_date", sa.String(16), nullable=True),
        sa.Column("study_description", sa.String(240), nullable=True),
        sa.Column("series_count", sa.Integer(), nullable=False),
        sa.Column("instance_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["pacs_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "orthanc_study_id", name="uq_pacs_study_node_orthanc"),
    )
    for column in ("node_id", "study_instance_uid", "accession_number", "patient_id"):
        op.create_index(f"ix_pacs_studies_{column}", "pacs_studies", [column], unique=False)

    op.create_table(
        "transfer_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("destination_node_id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("maximum_retries", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.ForeignKeyConstraint(["source_node_id"], ["pacs_nodes.id"]),
        sa.ForeignKeyConstraint(["destination_node_id"], ["pacs_nodes.id"]),
        sa.ForeignKeyConstraint(["study_id"], ["pacs_studies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    for column in ("study_id", "status", "correlation_id"):
        op.create_index(f"ix_transfer_jobs_{column}", "transfer_jobs", [column], unique=False)

    op.create_table(
        "transfer_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transfer_job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("request_evidence", sa.JSON(), nullable=False),
        sa.Column("response_evidence", sa.JSON(), nullable=False),
        sa.Column("redacted_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["transfer_job_id"], ["transfer_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transfer_job_id", "attempt_number", name="uq_transfer_attempt_number"),
    )
    op.create_index(
        "ix_transfer_attempts_transfer_job_id",
        "transfer_attempts",
        ["transfer_job_id"],
        unique=False,
    )

    op.create_table(
        "reconciliation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transfer_job_id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("destination_node_id", sa.Uuid(), nullable=False),
        sa.Column("study_uid_match", sa.Boolean(), nullable=False),
        sa.Column("accession_match", sa.Boolean(), nullable=False),
        sa.Column("patient_id_match", sa.Boolean(), nullable=False),
        sa.Column("identifiers_match", sa.Boolean(), nullable=False),
        sa.Column("instance_counts_match", sa.Boolean(), nullable=False),
        sa.Column("source_instance_count", sa.Integer(), nullable=False),
        sa.Column("destination_instance_count", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transfer_job_id"], ["transfer_jobs.id"]),
        sa.ForeignKeyConstraint(["study_id"], ["pacs_studies.id"]),
        sa.ForeignKeyConstraint(["source_node_id"], ["pacs_nodes.id"]),
        sa.ForeignKeyConstraint(["destination_node_id"], ["pacs_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reconciliation_results_transfer_job_id",
        "reconciliation_results",
        ["transfer_job_id"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_results_outcome",
        "reconciliation_results",
        ["outcome"],
        unique=False,
    )


def downgrade() -> None:
    for table in (
        "reconciliation_results",
        "transfer_attempts",
        "transfer_jobs",
        "pacs_studies",
        "pacs_health_checks",
        "pacs_nodes",
    ):
        op.drop_table(table)
