import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.db.base import Base
from app.incidents.classifier import IncidentCategory
from app.incidents.models import (
    IncidentRemediationProposal,
    PacsIncident,
    PacsIncidentStatus,
)
from app.pacs.dispatch import publish_pending_transfer_dispatches
from app.pacs.models import (
    PacsNode,
    PacsStudy,
    ReconciliationResult,
    TransferAttempt,
    TransferDispatch,
    TransferJob,
    TransferStatus,
)
from app.pacs.schemas import PacsHealth, PacsStudyMetadata, StoreResult
from app.pacs.transfer import (
    TransferConflict,
    TransferCreate,
    create_transfer,
    execute_transfer,
    reconcile_transfer,
)


class FakePacs:
    def __init__(self, studies: list[PacsStudyMetadata], *, accepts_transfer: bool = True) -> None:
        self.studies = studies
        self.accepts_transfer = accepts_transfer
        self.sent: list[tuple[str, str]] = []

    def health(self) -> PacsHealth:
        return PacsHealth(healthy=True, node_name="fake", version="test", latency_ms=1)

    def list_studies(self) -> list[PacsStudyMetadata]:
        return self.studies

    def find_study(self, study_instance_uid: str) -> list[PacsStudyMetadata]:
        return [item for item in self.studies if item.study_instance_uid == study_instance_uid]

    def upload_instance(self, dicom_bytes: bytes) -> str:
        return "instance-test"

    def send_study(self, orthanc_study_id: str, destination_name: str) -> StoreResult:
        self.sent.append((orthanc_study_id, destination_name))
        return StoreResult(accepted=self.accepts_transfer, response_path="/jobs/test")


def metadata(*, patient_id: str = "SYN-0001", instances: int = 2) -> PacsStudyMetadata:
    return PacsStudyMetadata(
        orthanc_study_id="study-source-1",
        study_instance_uid="1.2.826.0.1.3680043.8.498.1",
        accession_number="ACC-SYN-0001",
        patient_id=patient_id,
        study_date="20260719",
        study_description="Synthetic transfer study",
        series_count=1,
        instance_count=instances,
    )


def setup_transfer(session: Session) -> tuple[TransferJob, PacsStudy]:
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
    session.add_all([source, destination])
    session.flush()
    study = PacsStudy(
        node_id=source.id,
        orthanc_study_id="study-source-1",
        study_instance_uid="1.2.826.0.1.3680043.8.498.1",
        accession_number="ACC-SYN-0001",
        patient_id="SYN-0001",
        study_date="20260719",
        study_description="Synthetic transfer study",
        series_count=1,
        instance_count=2,
        metadata_json={"synthetic": True},
    )
    session.add(study)
    session.flush()
    request = TransferCreate(
        source_node_id=source.id,
        destination_node_id=destination.id,
        study_id=study.id,
        idempotency_key="transfer:SYN-0001:destination",
        correlation_id="corr-transfer-1",
        actor_id="pacs-admin-test",
    )
    first = create_transfer(session, request)
    second = create_transfer(session, request)
    assert first.id == second.id
    session.commit()
    return first, study


def test_transfer_is_idempotent_executes_once_and_reconciles_matching_metadata() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)
        source = FakePacs([metadata()])
        destination = FakePacs([metadata()])

        execute_transfer(session, job.id, source, actor_id="pacs-admin-test")
        session.commit()
        result = reconcile_transfer(
            session,
            job.id,
            source,
            destination,
            actor_id="pacs-admin-test",
        )
        session.commit()
        session.refresh(job)

        assert source.sent == [("study-source-1", "destination")]
        assert job.status == TransferStatus.COMPLETED
        assert result.outcome == "matched"
        assert result.identifiers_match is True
        assert result.instance_counts_match is True
        assert session.scalar(select(func.count()).select_from(TransferJob)) == 1
        assert session.scalar(select(func.count()).select_from(TransferAttempt)) == 1
        assert session.scalar(select(func.count()).select_from(ReconciliationResult)) == 1
        assert session.scalar(select(func.count()).select_from(PacsIncident)) == 0
        assert session.scalar(select(func.count()).select_from(IncidentRemediationProposal)) == 0


def test_identity_mismatch_never_completes_transfer() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)
        source = FakePacs([metadata()])
        destination = FakePacs([metadata(patient_id="SYN-DIFFERENT")])
        execute_transfer(session, job.id, source, actor_id="pacs-admin-test")
        session.commit()

        result = reconcile_transfer(
            session,
            job.id,
            source,
            destination,
            actor_id="pacs-admin-test",
        )
        session.commit()
        session.refresh(job)

        assert result.outcome == "identity_mismatch"
        assert result.identifiers_match is False
        assert job.status == TransferStatus.RECONCILIATION_FAILED


def test_reconciliation_identity_mismatch_creates_one_open_incident() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)
        source = FakePacs([metadata()])
        destination = FakePacs([metadata(patient_id="SYN-DIFFERENT")])
        execute_transfer(session, job.id, source, actor_id="pacs-admin-test")
        session.commit()

        reconcile_transfer(
            session,
            job.id,
            source,
            destination,
            actor_id="pacs-admin-test",
        )
        session.commit()
        reconcile_transfer(
            session,
            job.id,
            source,
            destination,
            actor_id="pacs-admin-test",
        )
        session.commit()

        incident = session.scalar(
            select(PacsIncident).where(PacsIncident.transfer_job_id == job.id)
        )
        assert incident is not None
        assert incident.category == IncidentCategory.IDENTITY_MISMATCH.value
        assert incident.severity == "critical"
        assert incident.status == PacsIncidentStatus.OPEN
        assert incident.approval_state.value == "pending"
        assert incident.requires_human_review is True
        assert incident.retry_candidate is False
        assert incident.rule_code == "IDENTITY_MISMATCH_REQUIRES_HUMAN"
        assert incident.last_failure_count == 2
        assert incident.evidence_json["reconciliation_outcome"] == "identity_mismatch"
        assert incident.evidence_json["reconciliation_identifiers_match"] is False
        assert incident.evidence_json["reconciliation_instance_counts_match"] is True
        assert incident.evidence_json["reconciliation_source_instance_count"] == 2
        assert incident.evidence_json["reconciliation_destination_instance_count"] == 2
        assert "patient_id" not in incident.evidence_json
        assert "study_instance_uid" not in incident.evidence_json
        assert "pixel_data" not in incident.evidence_json
        assert session.scalar(select(func.count()).select_from(PacsIncident)) == 1
        assert session.scalar(select(func.count()).select_from(IncidentRemediationProposal)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "pacs.incident.created")
            )
            == 1
        )


def test_reconciliation_count_mismatch_creates_one_open_incident() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)
        source = FakePacs([metadata()])
        destination = FakePacs([metadata(instances=3)])
        execute_transfer(session, job.id, source, actor_id="pacs-admin-test")
        session.commit()

        result = reconcile_transfer(
            session,
            job.id,
            source,
            destination,
            actor_id="pacs-admin-test",
        )
        session.commit()

        assert result.outcome == "count_mismatch"
        incident = session.scalar(
            select(PacsIncident).where(PacsIncident.transfer_job_id == job.id)
        )
        assert incident is not None
        assert incident.category == IncidentCategory.COUNT_MISMATCH.value
        assert incident.severity == "high"
        assert incident.status == PacsIncidentStatus.OPEN
        assert incident.requires_human_review is True
        assert incident.retry_candidate is False
        assert incident.rule_code == "COUNT_MISMATCH_REQUIRES_HUMAN"
        assert incident.evidence_json["reconciliation_outcome"] == "count_mismatch"
        assert incident.evidence_json["reconciliation_identifiers_match"] is True
        assert incident.evidence_json["reconciliation_instance_counts_match"] is False
        assert session.scalar(select(func.count()).select_from(PacsIncident)) == 1
        assert session.scalar(select(func.count()).select_from(IncidentRemediationProposal)) == 0


def test_reconciliation_missing_or_ambiguous_evidence_creates_one_open_unknown_incident() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)
        source = FakePacs([metadata()])
        destination = FakePacs([])
        execute_transfer(session, job.id, source, actor_id="pacs-admin-test")
        session.commit()

        result = reconcile_transfer(
            session,
            job.id,
            source,
            destination,
            actor_id="pacs-admin-test",
        )
        session.commit()

        assert result.outcome == "missing_or_ambiguous"
        incident = session.scalar(
            select(PacsIncident).where(PacsIncident.transfer_job_id == job.id)
        )
        assert incident is not None
        assert incident.category == IncidentCategory.UNKNOWN.value
        assert incident.severity == "high"
        assert incident.status == PacsIncidentStatus.OPEN
        assert incident.requires_human_review is True
        assert incident.retry_candidate is False
        assert incident.rule_code == "UNKNOWN_FAILURE_REQUIRES_HUMAN"
        assert incident.evidence_json["reconciliation_outcome"] == "missing_or_ambiguous"
        assert incident.evidence_json["reconciliation_identifiers_match"] is False
        assert incident.evidence_json["reconciliation_instance_counts_match"] is False
        assert session.scalar(select(func.count()).select_from(PacsIncident)) == 1
        assert session.scalar(select(func.count()).select_from(IncidentRemediationProposal)) == 0


def test_reconciliation_rejects_matching_nodes_that_drift_from_transfer_intent() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)
        drifted = metadata(patient_id="SYN-CHANGED", instances=0)
        source = FakePacs([drifted])
        destination = FakePacs([drifted])
        execute_transfer(session, job.id, source, actor_id="pacs-admin-test")
        session.commit()

        result = reconcile_transfer(
            session,
            job.id,
            source,
            destination,
            actor_id="pacs-admin-test",
        )
        session.commit()
        session.refresh(job)

        assert result.outcome == "identity_mismatch"
        assert result.identifiers_match is False
        assert result.instance_counts_match is False
        assert job.status == TransferStatus.RECONCILIATION_FAILED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_active", False),
        ("destination_active", False),
        ("source_node_type", "destination"),
        ("destination_node_type", "source"),
        ("source_adapter_key", "unexpected-source"),
        ("destination_adapter_key", "unexpected-destination"),
    ],
)
def test_transfer_rejects_unsafe_or_misconfigured_node_topology(field: str, value: object) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = PacsNode(
            name="Source Orthanc",
            node_type="source",
            base_url="http://source:8042",
            dicom_ae_title="SOURCE_PACS",
            dicom_host="orthanc-source",
            dicom_port=4242,
            adapter_key="source",
            active=True,
        )
        destination = PacsNode(
            name="Destination Orthanc",
            node_type="destination",
            base_url="http://destination:8042",
            dicom_ae_title="DEST_PACS",
            dicom_host="orthanc-destination",
            dicom_port=4242,
            adapter_key="destination",
            active=True,
        )
        target_name, attribute = field.split("_", 1)
        setattr(source if target_name == "source" else destination, attribute, value)
        session.add_all([source, destination])
        session.flush()
        study = PacsStudy(
            node_id=source.id,
            orthanc_study_id="unsafe-topology-study",
            study_instance_uid="1.2.826.0.1.3680043.8.498.99",
            accession_number="ACC-SYN-TOPOLOGY",
            patient_id="SYN-TOPOLOGY",
            series_count=1,
            instance_count=1,
            metadata_json={"synthetic": True},
        )
        session.add(study)
        session.flush()

        with pytest.raises(TransferConflict, match="topology"):
            create_transfer(
                session,
                TransferCreate(
                    source_node_id=source.id,
                    destination_node_id=destination.id,
                    study_id=study.id,
                    idempotency_key=f"unsafe-topology-{field}",
                    correlation_id="corr-unsafe-topology",
                    actor_id="pacs-admin-test",
                ),
            )

        assert session.scalar(select(func.count()).select_from(TransferJob)) == 0


def test_transfer_rechecks_topology_immediately_before_execution() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)
        source_node = session.get(PacsNode, job.source_node_id)
        assert source_node is not None
        source_node.active = False
        session.commit()
        source_adapter = FakePacs([metadata()])

        with pytest.raises(TransferConflict, match="topology"):
            execute_transfer(session, job.id, source_adapter, actor_id="pacs-admin-test")

        assert source_adapter.sent == []
        assert session.scalar(select(func.count()).select_from(TransferAttempt)) == 0


def test_duplicate_delivery_never_retries_a_failed_external_transfer() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)
        source = FakePacs([metadata()], accepts_transfer=False)

        execute_transfer(session, job.id, source, actor_id="celery-worker")
        session.commit()
        execute_transfer(session, job.id, source, actor_id="celery-worker")
        session.commit()
        session.refresh(job)

        assert job.status == TransferStatus.FAILED
        assert source.sent == [("study-source-1", "destination")]
        assert session.scalar(select(func.count()).select_from(TransferAttempt)) == 1


def test_transfer_outbox_recovers_after_broker_publication_failure() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, _ = setup_transfer(session)

        def unavailable(_: str) -> None:
            raise ConnectionError("synthetic broker outage")

        assert publish_pending_transfer_dispatches(session, unavailable) == 0
        session.commit()
        dispatch = session.get(TransferDispatch, job.id)
        assert dispatch is not None
        assert dispatch.status == "pending"
        assert dispatch.attempt_count == 1

        published: list[str] = []
        assert publish_pending_transfer_dispatches(session, published.append) == 1
        session.commit()
        session.refresh(dispatch)
        assert dispatch.status == "published"
        assert dispatch.attempt_count == 2
        assert published == [str(job.id)]
