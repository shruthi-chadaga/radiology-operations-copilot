"""snapshot immutable transfer intent

Revision ID: 0006_transfer_intent_snapshot
Revises: 0005_current_referral_fields
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_transfer_intent_snapshot"
down_revision: str | None = "0005_current_referral_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transfer_jobs", sa.Column("study_instance_uid", sa.String(128)))
    op.add_column("transfer_jobs", sa.Column("accession_number", sa.String(64)))
    op.add_column("transfer_jobs", sa.Column("patient_id", sa.String(64)))
    op.add_column("transfer_jobs", sa.Column("expected_instance_count", sa.Integer()))
    op.execute(
        """
        UPDATE transfer_jobs AS transfer
        SET study_instance_uid = study.study_instance_uid,
            accession_number = study.accession_number,
            patient_id = study.patient_id,
            expected_instance_count = study.instance_count
        FROM pacs_studies AS study
        WHERE transfer.study_id = study.id
        """
    )
    op.alter_column("transfer_jobs", "study_instance_uid", nullable=False)
    op.alter_column("transfer_jobs", "accession_number", nullable=False)
    op.alter_column("transfer_jobs", "patient_id", nullable=False)
    op.alter_column("transfer_jobs", "expected_instance_count", nullable=False)


def downgrade() -> None:
    op.drop_column("transfer_jobs", "expected_instance_count")
    op.drop_column("transfer_jobs", "patient_id")
    op.drop_column("transfer_jobs", "accession_number")
    op.drop_column("transfer_jobs", "study_instance_uid")
