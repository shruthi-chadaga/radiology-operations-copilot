"""enrich pacs_studies with modality and patient demographics

Revision ID: 0009_pacs_study_enrichment
Revises: 0008_transfer_dispatch_outbox
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_pacs_study_enrichment"
down_revision: str | None = "0008_transfer_dispatch_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pacs_studies", sa.Column("modality", sa.String(16), nullable=True))
    op.add_column("pacs_studies", sa.Column("patient_name", sa.String(120), nullable=True))
    op.add_column("pacs_studies", sa.Column("patient_birth_date", sa.String(16), nullable=True))
    op.add_column("pacs_studies", sa.Column("patient_sex", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column("pacs_studies", "patient_sex")
    op.drop_column("pacs_studies", "patient_birth_date")
    op.drop_column("pacs_studies", "patient_name")
    op.drop_column("pacs_studies", "modality")
