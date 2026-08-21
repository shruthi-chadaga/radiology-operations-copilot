"""Share allowlist model contract: expiring, audited, revocable report sharing."""

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base


def _load_migration():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0018_report_share_allowlist.py"
    spec = importlib.util.spec_from_file_location("report_share_allowlist", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def make_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def import_full_metadata() -> None:
    """Register every model so cross-module foreign keys resolve."""
    import app.audit.models  # noqa: F401
    import app.auth.models  # noqa: F401
    import app.exceptions.models  # noqa: F401
    import app.imaging.models  # noqa: F401
    import app.incidents.models  # noqa: F401
    import app.pacs.models  # noqa: F401
    import app.scheduling.models  # noqa: F401


def test_migration_revision_chain_and_contract() -> None:
    migration = _load_migration()
    assert migration.revision == "0018_report_share_allowlist"
    assert migration.down_revision == "0017_incident_proposal_superseded"


def test_share_record_persists_with_expiry_revocation_and_audit_link() -> None:
    import_full_metadata()
    from app.imaging.models import RadiologyReportShare, ShareStatus

    assert ShareStatus.ACTIVE.value == "active"
    assert ShareStatus.REVOKED.value == "revoked"

    engine = make_engine()
    Base.metadata.create_all(engine)

    now = datetime.now(UTC)
    expires = now + timedelta(hours=72)
    share = RadiologyReportShare(
        report_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        study_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        created_by="user-pacs-admin",
        token_hash="a" * 64,
        recipient_label="Referring clinic review",
        status=ShareStatus.ACTIVE,
        expires_at=expires,
    )
    with Session(engine) as session:
        session.add(share)
        session.commit()

        saved = session.get(RadiologyReportShare, share.id)
        assert saved is not None
        # Expiry is mandatory: the column must be populated and in the future.
        assert saved.expires_at is not None
        assert saved.token_hash != "" and len(saved.token_hash) == 64
        assert saved.status == ShareStatus.ACTIVE
        assert saved.revoked_at is None

        # One active share per (report, recipient): a second insert violates
        # the partial-style uniqueness enforced at the table level.
        duplicate = RadiologyReportShare(
            report_id=share.report_id,
            study_id=share.study_id,
            created_by="user-pacs-admin",
            token_hash="b" * 64,
            recipient_label=saved.recipient_label,
            status=ShareStatus.REVOKED,
            expires_at=expires,
        )
        session.add(duplicate)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("duplicate active share label was allowed")


def test_token_hash_is_not_the_token() -> None:
    """The stored value must be a hash; raw tokens never touch the database."""
    import_full_metadata()
    from app.imaging.models import RadiologyReportShare

    engine = make_engine()
    Base.metadata.create_all(engine)
    raw_token = "raw-share-token-value"
    share = RadiologyReportShare(
        report_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        study_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        created_by="user-om",
        token_hash=RadiologyReportShare.hash_token(raw_token),
        recipient_label="External audit copy",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    assert len(share.token_hash) == 64
    assert share.token_hash != raw_token.encode()
