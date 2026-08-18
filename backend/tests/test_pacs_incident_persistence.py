from dataclasses import dataclass
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.db.base import Base
from app.incidents.classifier import (
    IncidentCategory,
    IncidentClassificationInput,
    IncidentSeverity,
    classify_incident,
)
from app.incidents.models import PacsIncident, PacsIncidentStatus
from app.incidents.outbox import IncidentPersistenceOutbox
from app.incidents.service import record_transfer_failure_incident
from app.pacs import transfer as transfer_module
from app.pacs.models import (
    PacsNode,
    PacsStudy,
    TransferAttempt,
    TransferJob,
    TransferStatus,
)
from app.pacs.transfer import DestinationUnavailable, execute_transfer


@dataclass
class FailingAdapter:
    error: Exception
    calls: int = 0

    def send_study(self, orthanc_study_id: str, destination_name: str) -> object:
        self.calls += 1
        raise self.error


def setup_failed_transfer(session: Session) -> TransferJob:
    source = PacsNode(
        name="Source Incident Orthanc",
        node_type="source",
        base_url="http://source:8042",
        dicom_ae_title="SOURCE_INCIDENT",
        dicom_host="orthanc-source",
        dicom_port=4242,
        adapter_key="source",
    )
    destination = PacsNode(
        name="Destination Incident Orthanc",
        node_type="destination",
        base_url="http://destination:8042",
        dicom_ae_title="DEST_INCIDENT",
        dicom_host="orthanc-destination",
        dicom_port=4242,
        adapter_key="destination",
    )
    session.add_all([source, destination])
    session.flush()
    study = PacsStudy(
        node_id=source.id,
        orthanc_study_id="incident-study-1",
        study_instance_uid="1.2.826.0.1.3680043.8.498.incident",
        accession_number="ACC-SYN-INCIDENT",
        patient_id="SYN-INCIDENT",
        study_description="Synthetic incident study",
        series_count=1,
        instance_count=1,
        metadata_json={"synthetic": True},
    )
    session.add(study)
    session.flush()
    job = TransferJob(
        source_node_id=source.id,
        destination_node_id=destination.id,
        study_id=study.id,
        study_instance_uid=study.study_instance_uid,
        accession_number=study.accession_number,
        patient_id=study.patient_id,
        expected_instance_count=study.instance_count,
        status=TransferStatus.PENDING,
        retry_count=0,
        maximum_retries=1,
        idempotency_key="incident-transfer-idempotency",
        correlation_id="incident-correlation",
    )
    session.add(job)
    session.flush()
    return job


def connectivity_classification():
    return classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-incident",
            error_code="DESTINATION_UNAVAILABLE",
            error_message="Transfer adapter rejected the synthetic destination request",
            transfer_status="failed",
        )
    )


def test_execute_transfer_persists_failure_incident_without_retry_execution() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        adapter = FailingAdapter(DestinationUnavailable("synthetic destination unavailable"))

        execute_transfer(session, job.id, adapter, actor_id="celery-worker")
        session.commit()
        session.refresh(job)

        assert adapter.calls == 1
        assert job.status == TransferStatus.FAILED
        assert job.last_error_code == "DESTINATION_UNAVAILABLE"
        assert session.scalar(select(func.count()).select_from(TransferAttempt)) == 1
        incident = session.scalar(
            select(PacsIncident).where(PacsIncident.transfer_job_id == job.id)
        )
        assert incident is not None
        assert incident.status == PacsIncidentStatus.OPEN
        assert incident.category == IncidentCategory.CONNECTIVITY.value
        assert session.scalar(
            select(AuditEvent).where(AuditEvent.action == "pacs.incident.created")
        )


def test_final_attempt_audit_failure_preserves_failed_attempt_and_incident_evidence() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        adapter = FailingAdapter(DestinationUnavailable("synthetic destination unavailable"))
        original_append_audit_event = transfer_module.append_audit_event

        def fail_final_attempt_audit(*args: object, **kwargs: object) -> object:
            if kwargs.get("action") == "pacs.transfer.attempted":
                raise RuntimeError("synthetic final audit failure")
            return original_append_audit_event(*args, **kwargs)

        with (
            patch(
                "app.pacs.transfer.append_audit_event",
                side_effect=fail_final_attempt_audit,
            ),
            pytest.raises(RuntimeError, match="finalization requires recovery"),
        ):
            execute_transfer(session, job.id, adapter, actor_id="celery-worker")

        assert adapter.calls == 1
        session.expire_all()
        persisted_job = session.get(TransferJob, job.id)
        assert persisted_job is not None
        assert persisted_job.status == TransferStatus.FAILED
        assert session.scalar(select(func.count()).select_from(TransferAttempt)) == 1
        attempt = session.scalar(select(TransferAttempt))
        assert attempt is not None
        assert attempt.outcome == "failed"
        incident = session.scalar(
            select(PacsIncident).where(PacsIncident.transfer_job_id == job.id)
        )
        outbox = session.scalar(
            select(IncidentPersistenceOutbox).where(
                IncidentPersistenceOutbox.transfer_job_id == job.id
            )
        )
        assert incident is not None or outbox is not None
        if outbox is not None:
            assert outbox.status == "pending"
            assert outbox.attempt_count == 1
            assert outbox.evidence_json["attempt_number"] == 1


def test_failed_transfer_creates_one_audited_open_incident() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        job.status = TransferStatus.FAILED
        job.last_error_code = "DESTINATION_UNAVAILABLE"
        session.add(
            TransferAttempt(
                transfer_job_id=job.id,
                attempt_number=1,
                outcome="failed",
                request_evidence={},
                response_evidence={},
                redacted_error="TransferConflict: transfer request failed",
            )
        )
        session.flush()
        classification = connectivity_classification()

        incident = record_transfer_failure_incident(
            session,
            job,
            classification,
            redacted_error="TransferConflict: transfer request failed",
            actor_id="celery-worker",
        )
        session.commit()
        assert incident.category == IncidentCategory.CONNECTIVITY.value
        assert incident.severity == IncidentSeverity.MEDIUM.value
        assert incident.status == PacsIncidentStatus.OPEN
        assert incident.approval_state.value == "pending"
        assert incident.retry_candidate is True
        assert incident.requires_human_review is True
        assert incident.transfer_job_id == job.id
        assert incident.study_id == job.study_id
        assert session.scalar(select(func.count()).select_from(PacsIncident)) == 1
        audit = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "pacs.incident.created")
        )
        assert audit is not None
        assert audit.entity_id == str(incident.id)
        assert audit.correlation_id == job.correlation_id
        assert audit.after_state is not None
        assert audit.after_state["attempt_number"] == 1
        assert audit.after_state["rule_code"] == classification.rule_code
        assert audit.after_state["error_code"] == job.last_error_code


def test_repeated_failure_recording_is_idempotent_and_updates_evidence() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        job.status = TransferStatus.FAILED
        job.last_error_code = "DESTINATION_UNAVAILABLE"
        session.add(
            TransferAttempt(
                transfer_job_id=job.id,
                attempt_number=1,
                outcome="failed",
                request_evidence={},
                response_evidence={},
                redacted_error="first redacted failure",
            )
        )
        session.flush()
        classification = connectivity_classification()
        first = record_transfer_failure_incident(
            session,
            job,
            classification,
            redacted_error="first redacted failure",
            actor_id="celery-worker",
        )
        second = record_transfer_failure_incident(
            session,
            job,
            classification,
            redacted_error="second redacted failure SECRET=hidden",
            actor_id="celery-worker",
        )
        session.commit()

        assert first.id == second.id
        assert second.evidence_json["failure_count"] == 2
        assert second.evidence_json["latest_redacted_error"] == "redacted transfer failure"
        assert session.scalar(select(func.count()).select_from(PacsIncident)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


def test_resolved_incident_is_reopened_without_creating_a_second_number() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        job.status = TransferStatus.FAILED
        job.last_error_code = "DESTINATION_UNAVAILABLE"
        session.add(
            TransferAttempt(
                transfer_job_id=job.id,
                attempt_number=1,
                outcome="failed",
                request_evidence={},
                response_evidence={},
                redacted_error="first failure",
            )
        )
        session.flush()
        classification = connectivity_classification()
        first = record_transfer_failure_incident(
            session,
            job,
            classification,
            redacted_error="first failure",
            actor_id="celery-worker",
        )
        first.status = PacsIncidentStatus.RESOLVED
        session.commit()

        reopened = record_transfer_failure_incident(
            session,
            job,
            classification,
            redacted_error="later failure",
            actor_id="celery-worker",
        )
        session.commit()

        assert reopened.id == first.id
        assert reopened.incident_number == first.incident_number
        assert reopened.status == PacsIncidentStatus.OPEN
        assert reopened.last_failure_count == 2
        assert session.scalar(select(func.count()).select_from(PacsIncident)) == 1


def test_incident_persistence_never_authorizes_or_executes_a_retry() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        job.status = TransferStatus.FAILED
        job.last_error_code = "DESTINATION_UNAVAILABLE"
        session.add(
            TransferAttempt(
                transfer_job_id=job.id,
                attempt_number=1,
                outcome="failed",
                request_evidence={},
                response_evidence={},
                redacted_error="synthetic failure",
            )
        )
        session.flush()
        classification = connectivity_classification()
        record_transfer_failure_incident(
            session,
            job,
            classification,
            redacted_error="synthetic failure",
            actor_id="celery-worker",
        )
        session.commit()

        assert job.status == TransferStatus.FAILED
        assert classification.execution_authorized is False
        assert classification.category == IncidentCategory.CONNECTIVITY
        assert session.scalar(select(func.count()).select_from(TransferAttempt)) == 1


@dataclass
class HttpErrorAdapter:
    http_status: int
    calls: int = 0

    def send_study(self, orthanc_study_id: str, destination_name: str) -> object:
        self.calls += 1
        error = RuntimeError("synthetic HTTP error")
        error.http_status = self.http_status  # type: ignore[attr-defined]
        raise error


def test_http_401_finalization_rollback_preserves_unauthorized_classification() -> None:
    """Regression: HTTP 401 through finalization rollback must remain UNAUTHORIZED/critical."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        adapter = HttpErrorAdapter(http_status=401)
        original_append_audit_event = transfer_module.append_audit_event

        def fail_final_audit(*args: object, **kwargs: object) -> object:
            if kwargs.get("action") == "pacs.transfer.attempted":
                raise RuntimeError("synthetic final audit failure")
            return original_append_audit_event(*args, **kwargs)

        with (
            patch(
                "app.pacs.transfer.append_audit_event",
                side_effect=fail_final_audit,
            ),
            pytest.raises(RuntimeError, match="finalization requires recovery"),
        ):
            execute_transfer(session, job.id, adapter, actor_id="celery-worker")

        assert adapter.calls == 1
        session.expire_all()
        outbox = session.scalar(
            select(IncidentPersistenceOutbox).where(
                IncidentPersistenceOutbox.transfer_job_id == job.id
            )
        )
        assert outbox is not None
        assert outbox.status == "pending"
        assert outbox.evidence_json.get("http_status") == 401
        assert outbox.evidence_json.get("recovery") == "transfer_finalization"

        # Drain the outbox and verify incident classification is UNAUTHORIZED/critical
        from app.incidents.recovery import drain_incident_persistence_outbox

        result = drain_incident_persistence_outbox(session, actor_id="outbox-worker")
        assert result.completed == 1
        session.commit()

        incident = session.scalar(
            select(PacsIncident).where(PacsIncident.transfer_job_id == job.id)
        )
        assert incident is not None
        assert incident.category == IncidentCategory.UNAUTHORIZED.value
        assert incident.severity == IncidentSeverity.CRITICAL.value
        assert incident.rule_code == "UNAUTHORIZED_ACTION_REQUIRES_HUMAN"


def test_http_403_finalization_rollback_preserves_unauthorized_classification() -> None:
    """Regression: HTTP 403 through finalization rollback must remain UNAUTHORIZED/critical."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        adapter = HttpErrorAdapter(http_status=403)
        original_append_audit_event = transfer_module.append_audit_event

        def fail_final_audit(*args: object, **kwargs: object) -> object:
            if kwargs.get("action") == "pacs.transfer.attempted":
                raise RuntimeError("synthetic final audit failure")
            return original_append_audit_event(*args, **kwargs)

        with (
            patch(
                "app.pacs.transfer.append_audit_event",
                side_effect=fail_final_audit,
            ),
            pytest.raises(RuntimeError, match="finalization requires recovery"),
        ):
            execute_transfer(session, job.id, adapter, actor_id="celery-worker")

        assert adapter.calls == 1
        session.expire_all()
        outbox = session.scalar(
            select(IncidentPersistenceOutbox).where(
                IncidentPersistenceOutbox.transfer_job_id == job.id
            )
        )
        assert outbox is not None
        assert outbox.status == "pending"
        assert outbox.evidence_json.get("http_status") == 403

        # Drain the outbox and verify incident classification is UNAUTHORIZED/critical
        from app.incidents.recovery import drain_incident_persistence_outbox

        result = drain_incident_persistence_outbox(session, actor_id="outbox-worker")
        assert result.completed == 1
        session.commit()

        incident = session.scalar(
            select(PacsIncident).where(PacsIncident.transfer_job_id == job.id)
        )
        assert incident is not None
        assert incident.category == IncidentCategory.UNAUTHORIZED.value
        assert incident.severity == IncidentSeverity.CRITICAL.value
