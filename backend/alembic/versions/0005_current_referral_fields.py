"""enforce one current extraction row per referral field

Revision ID: 0005_current_referral_fields
Revises: 0004_audit_identifier_lengths
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_current_referral_fields"
down_revision: str | None = "0004_audit_identifier_lengths"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM referral_field_extractions
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY referral_id, field_name
                        ORDER BY id
                    ) AS duplicate_number
                FROM referral_field_extractions
            ) AS ranked
            WHERE duplicate_number > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_referral_current_field",
        "referral_field_extractions",
        ["referral_id", "field_name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_referral_current_field",
        "referral_field_extractions",
        type_="unique",
    )
