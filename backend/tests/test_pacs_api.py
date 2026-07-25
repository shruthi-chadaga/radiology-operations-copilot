from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.pacs import router as pacs_router
from app.pacs.models import PacsNode, PacsStudy
from app.pacs.router import get_pacs_adapters
from app.pacs.schemas import PacsHealth, PacsStudyMetadata, ReconciliationResponse, StoreResult


class ApiPacs:
    def health(self) -> PacsHealth:
        return PacsHealth(healthy=True, node_name="API PACS", version="test", latency_ms=2)

    def list_studies(self) -> list[PacsStudyMetadata]:
        return [
            PacsStudyMetadata(
                orthanc_study_id="study-source-api",
                study_instance_uid="1.2.3.api",
                accession_number="ACC-SYN-API",
                patient_id="SYN-API",
                study_date="20260719",
                study_description="Synthetic API transfer",
                series_count=1,
                instance_count=1,
            )
        ]

    def find_study(self, study_instance_uid: str) -> list[PacsStudyMetadata]:
        return self.list_studies()

    def upload_instance(self, dicom_bytes: bytes) -> str:
        return "instance-api"

    def send_study(self, orthanc_study_id: str, destination_name: str) -> StoreResult:
        return StoreResult(accepted=True, response_path="/jobs/api")


def test_pacs_api_lists_nodes_checks_health_syncs_and_queues_idempotent_transfer(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    admin = User(
        email="pacs@example.local",
        display_name="Synthetic PACS Admin",
        password_hash="unused-test-hash",
        role=Role.PACS_ADMIN,
    )
    with Session(engine) as session:
        source = PacsNode(
            name="Source Orthanc",
            node_type="source",
            base_url="http://source:8042",
            dicom_ae_title="SOURCE_PACS",
            dicom_host="orthanc-source",
            dicom_port=4242,
            adapter_key="source",
        )
        destination = PacsNode(
            name="Destination Orthanc",
            node_type="destination",
            base_url="http://destination:8042",
            dicom_ae_title="DEST_PACS",
            dicom_host="orthanc-destination",
            dicom_port=4242,
            adapter_key="destination",
        )
        session.add_all([admin, source, destination])
        session.flush()
        study = PacsStudy(
            node_id=source.id,
            orthanc_study_id="study-source-api",
            study_instance_uid="1.2.3.api",
            accession_number="ACC-SYN-API",
            patient_id="SYN-API",
            study_date="20260719",
            study_description="Synthetic API transfer",
            series_count=1,
            instance_count=1,
            metadata_json={"synthetic": True},
        )
        session.add(study)
        session.commit()
        source_id = str(source.id)
        destination_id = str(destination.id)
        study_id = str(study.id)
        session.refresh(admin)

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    queued: list[str] = []
    monkeypatch.setattr(
        pacs_router.execute_transfer_task, "delay", lambda value: queued.append(value)
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_pacs_adapters] = lambda: {
        "source": ApiPacs(),
        "destination": ApiPacs(),
    }
    client = TestClient(app)
    try:
        nodes = client.get("/api/v1/pacs/nodes")
        assert nodes.status_code == 200 and len(nodes.json()["items"]) == 2

        health = client.post(f"/api/v1/pacs/nodes/{source_id}/health-check")
        assert health.status_code == 200 and health.json()["status"] == "healthy"
        latest_health = client.get(f"/api/v1/pacs/nodes/{source_id}/health")
        assert latest_health.status_code == 200

        missing_sync_attestation = client.post(
            "/api/v1/pacs/studies/sync", json={"node_id": source_id}
        )
        assert missing_sync_attestation.status_code == 422
        synced = client.post(
            "/api/v1/pacs/studies/sync",
            json={"node_id": source_id, "synthetic_data_confirmed": True},
        )
        assert synced.status_code == 200 and synced.json()["study_count"] == 1
        study_detail = client.get(f"/api/v1/pacs/studies/{study_id}")
        assert study_detail.status_code == 200

        created = client.post(
            "/api/v1/pacs/transfers",
            json={
                "source_node_id": source_id,
                "destination_node_id": destination_id,
                "study_id": study_id,
            },
            headers={"Idempotency-Key": "api-transfer-key", "X-Correlation-ID": "corr-api"},
        )
        repeated = client.post(
            "/api/v1/pacs/transfers",
            json={
                "source_node_id": source_id,
                "destination_node_id": destination_id,
                "study_id": study_id,
            },
            headers={"Idempotency-Key": "api-transfer-key", "X-Correlation-ID": "corr-api"},
        )
        assert created.status_code == repeated.status_code == 202
        assert created.json()["id"] == repeated.json()["id"]
        assert queued == [created.json()["id"]]
        denied = client.post(
            "/api/v1/pacs/transfers",
            json={
                "source_node_id": source_id,
                "destination_node_id": source_id,
                "study_id": study_id,
            },
            headers={"Idempotency-Key": "unsafe-same-node-transfer"},
        )
        assert denied.status_code == 409
        transfer_detail = client.get(f"/api/v1/pacs/transfers/{created.json()['id']}")
        assert transfer_detail.status_code == 200
        assert transfer_detail.json()["attempts"] == []
        assert transfer_detail.json()["reconciliations"] == []
        with Session(engine) as session:
            assert (
                session.scalar(
                    select(AuditEvent).where(AuditEvent.action == "pacs.transfer.request_denied")
                )
                is not None
            )
    finally:
        app.dependency_overrides.clear()


def test_reconciliation_response_exposes_observed_instance_counts() -> None:
    response = ReconciliationResponse(
        id="reconciliation-id",
        transfer_job_id="transfer-id",
        outcome="matched",
        identifiers_match=True,
        instance_counts_match=True,
        source_instance_count=1,
        destination_instance_count=1,
    )

    assert response.model_dump()["source_instance_count"] == 1
    assert response.model_dump()["destination_instance_count"] == 1
