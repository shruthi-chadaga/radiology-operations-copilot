"""allow stale incident remediation proposals to be superseded

Revision ID: 0017_incident_proposal_superseded
Revises: 0016_incident_approval_controls
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_supersede_proposals"
down_revision: str | None = "0016_incident_approval_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STATUS_CONSTRAINT = "ck_incident_proposal_status"
_TABLE = "incident_remediation_proposals"


def upgrade() -> None:
    op.drop_constraint(_STATUS_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        _TABLE,
        "status IN ('pending', 'approved', 'rejected', 'superseded')",
    )


def downgrade() -> None:
    op.drop_constraint(_STATUS_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        _TABLE,
        "status IN ('pending', 'approved', 'rejected')",
    )
