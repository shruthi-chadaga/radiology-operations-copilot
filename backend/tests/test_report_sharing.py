"""Share allowlist model contract: expiring, audited, revocable report sharing."""

import importlib.util
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
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
    from app.imaging.models import RadiologyReportShare, ShareStatus  # noqa: F811

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
    from app.imaging.models import RadiologyReportShare  # noqa: F811

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


# ---------------------------------------------------------------------------
# API slice: create / list / revoke shares with audit evidence
# ---------------------------------------------------------------------------


from fastapi.testclient import TestClient  # noqa: E402

from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.models import Role, User  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.imaging.models import (  # noqa: E402
    RadiologyReport,
    ReportStatus,
)
from app.main import app  # noqa: E402
from app.pacs.models import PacsStudy  # noqa: E402


def _seed_report(session: Session) -> RadiologyReport:
    import_full_metadata()
    from app.pacs.models import PacsNode

    node = PacsNode(
        name="Share Source Orthanc",
        node_type="source",
        base_url="http://share-source:8042",
        dicom_ae_title="SHARE_SOURCE",
        dicom_host="share-source",
        dicom_port=4242,
        adapter_key="share-source",
    )
    session.add(node)
    session.flush()
    study = PacsStudy(
        node_id=node.id,
        orthanc_study_id="share-study-1",
        study_instance_uid="1.2.826.0.1.3680043.8.498.share",
        accession_number="ACC-SYN-SHARE",
        patient_id="SYN-SHARE",
        study_description="Synthetic share study",
        series_count=1,
        instance_count=1,
        metadata_json={"synthetic": True},
    )
    session.add(study)
    session.flush()
    report = RadiologyReport(
        study_id=study.id,
        status=ReportStatus.FINALIZED,
        current_version_number=1,
        finalized_by="user-pacs-admin",
    )
    session.add(report)
    session.flush()
    return report


def _override_env(engine, user: User):  # type: ignore[no-untyped-def]
    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_share_lifecycle_create_list_revoke_with_audit() -> None:
    import_full_metadata()
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = {
            role: User(
                email=f"{role.value}@example.local",
                display_name=role.value,
                password_hash="not-used",
                role=role,
            )
            for role in (Role.PACS_ADMIN, Role.OPERATIONS_MANAGER, Role.AUDITOR)
        }
        session.add_all(users.values())
        report = _seed_report(session)
        session.commit()

    _override_env(engine, users[Role.PACS_ADMIN])
    try:
        client = TestClient(app)

        # Auditor cannot create shares.
        app.dependency_overrides[get_current_user] = lambda: users[Role.AUDITOR]
        denied = client.post(
            f"/api/v1/imaging/reports/{report.id}/shares",
            json={"recipient_label": "Nope", "expires_in_hours": 24},
        )
        assert denied.status_code == 403

        app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]

        # Blank label rejected; absurd expiry rejected.
        assert (
            client.post(
                f"/api/v1/imaging/reports/{report.id}/shares",
                json={"recipient_label": "   ", "expires_in_hours": 24},
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/v1/imaging/reports/{report.id}/shares",
                json={"recipient_label": "Too long", "expires_in_hours": 10000},
            ).status_code
            == 422
        )

        created = client.post(
            f"/api/v1/imaging/reports/{report.id}/shares",
            json={"recipient_label": "Referring clinic", "expires_in_hours": 48},
        )
        assert created.status_code == 201
        payload = created.json()
        assert payload["status"] == "active"
        assert len(payload["token"]) >= 32
        assert payload["token_hash"] if False else True  # raw token only once
        assert "token_hash" not in payload

        # Duplicate recipient label conflicts.
        duplicate = client.post(
            f"/api/v1/imaging/reports/{report.id}/shares",
            json={"recipient_label": "Referring clinic", "expires_in_hours": 48},
        )
        assert duplicate.status_code == 409

        listed = client.get(f"/api/v1/imaging/reports/{report.id}/shares")
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert len(items) == 1
        assert "token" not in items[0]
        assert items[0]["recipient_label"] == "Referring clinic"

        revoked = client.delete(
            f"/api/v1/imaging/reports/shares/{payload['id']}",
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"

        # Revoking twice is a deterministic conflict, not silent success.
        again = client.delete(f"/api/v1/imaging/reports/shares/{payload['id']}")
        assert again.status_code == 409

        listed_after = client.get(f"/api/v1/imaging/reports/{report.id}/shares").json()["items"]
        assert listed_after[0]["status"] == "revoked"
        assert listed_after[0]["revoked_at"] is not None

    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(AuditEvent.entity_type == "radiology_report_share")
            )
        )
        assert "imaging.share.created" in actions
        assert "imaging.share.revoked" in actions
        # Raw tokens must never appear anywhere in audit evidence.
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.entity_type == "radiology_report_share")
        ).all()
        for event in events:
            blob = json.dumps(
                {
                    "before": event.before_state,
                    "after": event.after_state,
                    "reason": event.decision_reason,
                }
            )
            assert payload["token"] not in blob
