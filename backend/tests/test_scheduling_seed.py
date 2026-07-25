from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.scheduling.models import ImagingService, Location, Referral, Slot, SyntheticPatient
from app.scheduling.seed import seed_scheduling_demo


def test_scheduling_seed_meets_minimum_synthetic_data_counts_and_is_idempotent() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_scheduling_demo(session)
        seed_scheduling_demo(session)
        session.commit()

        assert session.scalar(select(func.count()).select_from(SyntheticPatient)) == 50
        assert session.scalar(select(func.count()).select_from(Referral)) == 40
        assert session.scalar(select(func.count()).select_from(Location)) == 5
        assert session.scalar(select(func.count()).select_from(ImagingService)) == 10
        assert session.scalar(select(func.count()).select_from(Slot)) == 300
        assert all(
            patient.synthetic for patient in session.scalars(select(SyntheticPatient).limit(50))
        )
