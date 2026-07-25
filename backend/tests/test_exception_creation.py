from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.exceptions.models import ExceptionCase
from app.exceptions.service import sync_referral_exception
from app.scheduling.validation import ValidationIssue, ValidationResult


def test_referral_validation_exception_is_persisted_idempotently_and_resolved() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    source_id = "synthetic-referral-1"
    blocked = ValidationResult(
        is_complete=False,
        requires_human_review=True,
        issues=[
            ValidationIssue(
                "AUTHORIZATION_INCOMPLETE", "Administrative authorization is incomplete"
            )
        ],
    )
    with Session(engine) as session:
        first = sync_referral_exception(session, source_id, blocked)
        second = sync_referral_exception(session, source_id, blocked)
        session.commit()
        assert first.id == second.id
        assert session.scalar(select(func.count()).select_from(ExceptionCase)) == 1
        assert first.status == "open"
        assert first.category == "AUTHORIZATION_INCOMPLETE"

        cleared = ValidationResult(is_complete=True, requires_human_review=False, issues=[])
        resolved = sync_referral_exception(session, source_id, cleared)
        session.commit()
        assert resolved is None
        assert first.status == "resolved"
        assert first.resolution == "Deterministic referral validation passed"
