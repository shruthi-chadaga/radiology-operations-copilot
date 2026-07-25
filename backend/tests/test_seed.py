from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.models import Role, User
from app.auth.security import hash_password, verify_password
from app.config import get_settings
from app.db.base import Base
from app.db.seed import DEMO_USERS, seed_demo_users


def test_seed_creates_all_roles_and_is_idempotent() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_demo_users(session)
        scheduler = session.scalar(select(User).where(User.email == "scheduler@example.local"))
        assert scheduler is not None
        scheduler.password_hash = hash_password("stale-password")
        session.flush()
        seed_demo_users(session)
        session.commit()
        users = list(session.scalars(select(User)))

    assert len(users) == len(DEMO_USERS) == 5
    assert {user.role for user in users} == set(Role)
    assert all(user.email.endswith("@example.local") for user in users)
    assert all("$argon2" in user.password_hash for user in users)
    settings = get_settings()
    assert all(
        verify_password(getattr(settings, demo.password_setting), user.password_hash)
        for demo in DEMO_USERS
        for user in users
        if user.email == demo.email
    )
