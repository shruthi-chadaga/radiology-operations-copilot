"""enforce one active appointment per referral

Revision ID: 0007_active_appointment_unique
Revises: 0006_transfer_intent_snapshot
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_active_appointment_unique"
down_revision: str | None = "0006_transfer_intent_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_PREDICATE = sa.text("status IN ('BOOKED', 'CONFIRMED')")


def upgrade() -> None:
    op.create_index(
        "uq_appointment_active_referral",
        "appointments",
        ["referral_id"],
        unique=True,
        postgresql_where=_ACTIVE_PREDICATE,
        sqlite_where=_ACTIVE_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index("uq_appointment_active_referral", table_name="appointments")
