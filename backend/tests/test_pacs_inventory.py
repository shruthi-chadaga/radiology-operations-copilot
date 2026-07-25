import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.db.base import Base
from app.pacs.inventory import UnsafePacsMetadata, check_node_health, sync_inventory
from app.pacs.models import PacsHealthCheck, PacsNode, PacsStudy
from app.pacs.schemas import PacsHealth, PacsStudyMetadata, StoreResult


class InventoryPacs:
    def __init__(self) -> None:
        self.instance_count = 1

    def health(self) -> PacsHealth:
        return PacsHealth(healthy=True, node_name="Synthetic Source", version="test", latency_ms=4)

    def list_studies(self) -> list[PacsStudyMetadata]:
        return [
            PacsStudyMetadata(
                orthanc_study_id="orthanc-1",
                study_instance_uid="1.2.3.synthetic.1",
                accession_number="ACC-SYN-1",
                patient_id="SYN-0001",
                study_date="20260719",
                study_description="Synthetic non-clinical object",
                series_count=1,
                instance_count=self.instance_count,
            )
        ]

    def find_study(self, study_instance_uid: str) -> list[PacsStudyMetadata]:
        return self.list_studies()

    def upload_instance(self, dicom_bytes: bytes) -> str:
        return "instance-1"

    def send_study(self, orthanc_study_id: str, destination_name: str) -> StoreResult:
        return StoreResult(accepted=True, response_path="/jobs/1")


class UnsafeInventoryPacs(InventoryPacs):
    def list_studies(self) -> list[PacsStudyMetadata]:
        study = super().list_studies()[0]
        return [study.model_copy(update={"patient_id": "UNMARKED-001"})]


def test_health_and_inventory_are_persisted_audited_and_upserted_without_deletion() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        node = PacsNode(
            name="Source Orthanc",
            node_type="source",
            base_url="http://source:8042",
            dicom_ae_title="SOURCE_PACS",
            dicom_host="orthanc-source",
            dicom_port=4242,
            adapter_key="source",
        )
        session.add(node)
        session.commit()
        adapter = InventoryPacs()

        health = check_node_health(session, node, adapter, actor_id="pacs-admin-test")
        first_count = sync_inventory(session, node, adapter, actor_id="pacs-admin-test")
        adapter.instance_count = 2
        second_count = sync_inventory(session, node, adapter, actor_id="pacs-admin-test")
        session.commit()

        study = session.scalar(select(PacsStudy))
        assert health.status == "healthy"
        assert first_count == second_count == 1
        assert study is not None and study.instance_count == 2
        assert session.scalar(select(func.count()).select_from(PacsStudy)) == 1
        assert session.scalar(select(func.count()).select_from(PacsHealthCheck)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 3


def test_inventory_rejects_entire_batch_when_metadata_is_not_conspicuously_synthetic() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        node = PacsNode(
            name="Source Orthanc",
            node_type="source",
            base_url="http://source:8042",
            dicom_ae_title="SOURCE_PACS",
            dicom_host="orthanc-source",
            dicom_port=4242,
            adapter_key="source",
        )
        session.add(node)
        session.flush()

        with pytest.raises(UnsafePacsMetadata):
            sync_inventory(session, node, UnsafeInventoryPacs(), actor_id="pacs-admin-test")

        assert session.scalar(select(func.count()).select_from(PacsStudy)) == 0
