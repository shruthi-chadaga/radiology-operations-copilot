"""document correction-pending imaging worklist state

Revision ID: 0015_imaging_correction_pending
Revises: 0014_radiology_reports
Create Date: 2026-08-07
"""

from collections.abc import Sequence

revision: str = "0015_imaging_correction_pending"
down_revision: str | None = "0014_radiology_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ImagingWorklistStatus uses a non-native VARCHAR enum. This revision
    # records the correction-pending contract without changing table DDL.
    pass


def downgrade() -> None:
    pass
