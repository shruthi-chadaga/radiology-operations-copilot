"""document imaging worklist cancellation state

Revision ID: 0013_imaging_worklist_cancelled
Revises: 0012_imaging_worklist
Create Date: 2026-08-07
"""

from collections.abc import Sequence

revision: str = "0013_imaging_worklist_cancelled"
down_revision: str | None = "0012_imaging_worklist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ImagingWorklistStatus uses a non-native VARCHAR enum, so the new value
    # requires no DDL change. This revision records the contract change in the
    # migration chain for deployments that track schema heads.
    pass


def downgrade() -> None:
    pass
