"""Idempotent seeded local demo accounts with operator-supplied passwords."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Role, User
from app.auth.security import hash_password, verify_password
from app.config import get_settings
from app.pacs.seed import seed_pacs_nodes
from app.scheduling.seed import seed_scheduling_demo


@dataclass(frozen=True)
class DemoUser:
    email: str
    display_name: str
    role: Role
    password_setting: str


DEMO_USERS = (
    DemoUser(
        "scheduler@example.local", "Synthetic Scheduler", Role.SCHEDULER, "scheduler_demo_password"
    ),
    DemoUser(
        "pacsadmin@example.local",
        "Synthetic PACS Admin",
        Role.PACS_ADMIN,
        "pacs_admin_demo_password",
    ),
    DemoUser(
        "manager@example.local",
        "Synthetic Operations Manager",
        Role.OPERATIONS_MANAGER,
        "operations_manager_demo_password",
    ),
    DemoUser("auditor@example.local", "Synthetic Auditor", Role.AUDITOR, "auditor_demo_password"),
    DemoUser(
        "admin@example.local",
        "Synthetic System Admin",
        Role.SYSTEM_ADMIN,
        "system_admin_demo_password",
    ),
)


def seed_demo_users(session: Session) -> None:
    settings = get_settings()
    for demo in DEMO_USERS:
        configured_password = getattr(settings, demo.password_setting)
        existing = session.scalar(select(User).where(User.email == demo.email))
        if existing is None:
            session.add(
                User(
                    email=demo.email,
                    display_name=demo.display_name,
                    role=demo.role,
                    password_hash=hash_password(configured_password),
                    is_active=True,
                )
            )
        elif not verify_password(configured_password, existing.password_hash):
            existing.password_hash = hash_password(configured_password)
    session.flush()


def main() -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        seed_demo_users(session)
        seed_scheduling_demo(session)
        seed_pacs_nodes(session)
        session.commit()
    print(f"Seeded {len(DEMO_USERS)} users and deterministic synthetic scheduling data.")


if __name__ == "__main__":
    main()
