from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.auth.models import Role, User
from app.auth.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app


def test_login_sets_http_only_cookie_and_me_returns_seeded_role() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            User(
                email="scheduler@example.local",
                display_name="Synthetic Scheduler",
                password_hash=hash_password("scheduler-demo"),
                role=Role.SCHEDULER,
            )
        )
        session.commit()

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "scheduler@example.local", "password": "scheduler-demo"},
        )
        assert login.status_code == 200
        assert "httponly" in login.headers["set-cookie"].lower()

        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["role"] == "scheduler"
        assert me.json()["email"] == "scheduler@example.local"

        untrusted_logout = client.post("/api/v1/auth/logout")
        assert untrusted_logout.status_code == 403
        assert untrusted_logout.json()["detail"] == "Untrusted origin"
        trusted_logout = client.post(
            "/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"}
        )
        assert trusted_logout.status_code == 204
        with Session(engine) as session:
            actions = list(
                session.scalars(select(AuditEvent.action).order_by(AuditEvent.timestamp))
            )
            assert "auth.access.denied" in actions
            assert "auth.logout" in actions
    finally:
        app.dependency_overrides.clear()


def test_invalid_login_is_rejected_without_disclosing_account_state() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        responses = [
            client.post(
                "/api/v1/auth/login",
                json={"email": "scheduler@example.local", "password": "wrong-password"},
            )
            for _ in range(6)
        ]

        assert [response.status_code for response in responses[:5]] == [401] * 5
        assert responses[5].status_code == 429
        assert responses[5].json()["detail"] == "Too many login attempts"
        with Session(engine) as session:
            actions = list(session.scalars(select(AuditEvent.action)))
            assert actions.count("auth.login") == 5
            assert actions.count("auth.login.rate_limited") == 1
    finally:
        app.dependency_overrides.clear()
