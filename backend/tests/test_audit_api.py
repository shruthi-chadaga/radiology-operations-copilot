from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.service import AuditActor, append_audit_event
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.db.base import Base
from app.db.session import get_db
from app.main import app


def test_auditor_can_read_append_only_audit_events() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    auditor = User(
        email="auditor@example.local",
        display_name="Synthetic Auditor",
        password_hash="not-used-by-dependency-override",
        role=Role.AUDITOR,
    )
    with Session(engine) as session:
        session.add(auditor)
        session.flush()
        append_audit_event(
            session,
            actor=AuditActor("system", None),
            action="foundation.ready",
            entity_type="system",
            entity_id="local",
            decision_reason="Foundation API test",
            correlation_id="corr-audit-api",
            request_id="req-audit-api",
            success=True,
        )
        session.commit()
        session.refresh(auditor)

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: auditor
    try:
        response = TestClient(app).get("/api/v1/audit")
        assert response.status_code == 200
        assert response.json()["items"][0]["action"] == "foundation.ready"
        assert response.json()["items"][0]["success"] is True
    finally:
        app.dependency_overrides.clear()
