from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.audit.service import AuditActor, append_audit_event
from app.db.base import Base


def test_audit_service_appends_complete_event() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        event = append_audit_event(
            session,
            actor=AuditActor(actor_type="system", actor_id=None),
            action="foundation.verified",
            entity_type="system",
            entity_id="local",
            decision_reason="Phase 1 smoke evidence",
            correlation_id="corr-test-001",
            request_id="req-test-001",
            success=True,
            after_state={"synthetic_only": True},
        )
        session.commit()

        saved = session.get(AuditEvent, event.id)
        assert saved is not None
        assert saved.action == "foundation.verified"
        assert saved.after_state == {"synthetic_only": True}
        assert saved.correlation_id == "corr-test-001"
        assert saved.success is True


def test_audit_service_exposes_no_update_or_delete_operation() -> None:
    from app.audit import service

    assert not hasattr(service, "update_audit_event")
    assert not hasattr(service, "delete_audit_event")


def test_audit_identifiers_accept_public_idempotency_key_limit() -> None:
    assert AuditEvent.__table__.c.request_id.type.length == 160
    assert AuditEvent.__table__.c.correlation_id.type.length == 160
