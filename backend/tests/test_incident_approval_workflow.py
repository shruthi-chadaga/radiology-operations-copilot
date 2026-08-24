import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.incidents.classifier import IncidentClassificationInput, classify_incident
from app.incidents.models import (
    IncidentProposalStatus,
    IncidentRemediationApproval,
    IncidentRemediationProposal,
    PacsIncident,
    PacsIncidentApprovalState,
    PacsIncidentStatus,
)
from app.incidents.outbox import IncidentPersistenceOutbox
from app.incidents.recovery import drain_incident_persistence_outbox
from app.incidents.service import record_transfer_failure_incident
from app.main import app
from app.pacs.models import PacsNode, PacsStudy, TransferAttempt, TransferJob, TransferStatus


def make_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def add_users(session: Session) -> dict[Role, User]:
    users = {
        role: User(
            email=f"{role.value}@example.local",
            display_name=role.value,
            password_hash="not-used",
            role=role,
        )
        for role in (Role.PACS_ADMIN, Role.OPERATIONS_MANAGER, Role.AUDITOR, Role.SCHEDULER)
    }
    session.add_all(users.values())
    session.flush()
    return users


def setup_failed_transfer(session: Session) -> TransferJob:
    source = PacsNode(
        name="Source Approval Orthanc",
        node_type="source",
        base_url="http://source:8042",
        dicom_ae_title="SOURCE_APPROVAL",
        dicom_host="orthanc-source",
        dicom_port=4242,
        adapter_key="source-approval",
    )
    destination = PacsNode(
        name="Destination Approval Orthanc",
        node_type="destination",
        base_url="http://destination:8042",
        dicom_ae_title="DEST_APPROVAL",
        dicom_host="orthanc-destination",
        dicom_port=4242,
        adapter_key="destination-approval",
    )
    session.add_all([source, destination])
    session.flush()
    study = PacsStudy(
        node_id=source.id,
        orthanc_study_id="approval-study-1",
        study_instance_uid="1.2.826.0.1.3680043.8.498.approval",
        accession_number="ACC-SYN-APPROVAL",
        patient_id="SYN-APPROVAL",
        study_description="Synthetic approval study",
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
        status=TransferStatus.FAILED,
        retry_count=0,
        maximum_retries=1,
        idempotency_key="approval-transfer-idempotency",
        correlation_id="approval-correlation",
        last_error_code="DESTINATION_UNAVAILABLE",
    )
    session.add(job)
    session.flush()
    return job


def connectivity_classification():
    return classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="approval-transfer",
            error_code="DESTINATION_UNAVAILABLE",
            error_message="DestinationUnavailable: transfer request failed",
            transfer_status="failed",
        )
    )


def create_incident(session: Session):
    job = setup_failed_transfer(session)
    session.add(
        TransferAttempt(
            transfer_job_id=job.id,
            attempt_number=1,
            outcome="failed",
            request_evidence={},
            response_evidence={},
            redacted_error="DestinationUnavailable: transfer request failed",
        )
    )
    session.flush()
    incident = record_transfer_failure_incident(
        session,
        job,
        connectivity_classification(),
        redacted_error="DestinationUnavailable: transfer request failed",
        actor_id="worker",
    )
    return incident, job


def override_database(engine):
    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    return override_db


def test_supersession_migration_revision_and_constraint_contract() -> None:
    migration_path = (
        Path(__file__).parents[1] / "alembic" / "versions" / "0017_supersede_proposals.py"
    )
    spec = importlib.util.spec_from_file_location("incident_proposal_superseded", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0017_supersede_proposals"
    assert migration.down_revision == "0016_incident_approval_controls"
    status_constraint = next(
        constraint
        for constraint in IncidentRemediationProposal.__table__.constraints
        if constraint.name == "ck_incident_proposal_status"
    )
    assert str(status_constraint.sqltext) == (
        "status IN ('pending', 'approved', 'rejected', 'superseded')"
    )


def test_proposal_and_rejection_are_persisted_and_audited() -> None:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = add_users(session)
        incident, _ = create_incident(session)
        session.commit()

    app.dependency_overrides[get_db] = override_database(engine)
    app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/v1/incidents/{incident.id}/proposals",
            json={"requested_action": "RETRY_TRANSFER", "rationale": "Review destination outage"},
        )
        assert response.status_code == 201
        proposal = response.json()
        assert proposal["status"] == "pending"
        assert proposal["policy_snapshot"]["approval_is_not_execution"] is True

        app.dependency_overrides[get_current_user] = lambda: users[Role.OPERATIONS_MANAGER]
        rejected = client.post(
            f"/api/v1/incidents/proposals/{proposal['id']}/reject",
            json={"decision_reason": "Wait for operator confirmation"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"
        assert rejected.json()["approval"]["decision"] == "rejected"
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        saved = session.get(PacsIncident, incident.id)
        assert saved is not None
        assert saved.status == PacsIncidentStatus.OPEN
        assert saved.approval_state == PacsIncidentApprovalState.REJECTED
        assert session.scalar(select(func.count()).select_from(IncidentRemediationApproval)) == 1
        actions = set(session.scalars(select(AuditEvent.action)))
        assert "pacs.incident.proposal.created" in actions
        assert "pacs.incident.proposal.rejected" in actions


def test_auditor_and_scheduler_cannot_propose_or_approve() -> None:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = add_users(session)
        incident, _ = create_incident(session)
        session.commit()

    app.dependency_overrides[get_db] = override_database(engine)
    app.dependency_overrides[get_current_user] = lambda: users[Role.AUDITOR]
    try:
        client = TestClient(app)
        assert (
            client.post(
                f"/api/v1/incidents/{incident.id}/proposals",
                json={"requested_action": "RETRY_TRANSFER", "rationale": "Not allowed"},
            ).status_code
            == 403
        )
        app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]
        proposal = client.post(
            f"/api/v1/incidents/{incident.id}/proposals",
            json={"requested_action": "RETRY_TRANSFER", "rationale": "Need review"},
        ).json()
        app.dependency_overrides[get_current_user] = lambda: users[Role.SCHEDULER]
        assert (
            client.post(
                f"/api/v1/incidents/proposals/{proposal['id']}/approve",
                json={"decision_reason": "Not allowed"},
            ).status_code
            == 403
        )
    finally:
        app.dependency_overrides.clear()


def test_approval_is_fail_closed_and_never_starts_a_transfer() -> None:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = add_users(session)
        incident, _ = create_incident(session)
        session.commit()

    app.dependency_overrides[get_db] = override_database(engine)
    app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]
    try:
        client = TestClient(app)
        proposal = client.post(
            f"/api/v1/incidents/{incident.id}/proposals",
            json={"requested_action": "RETRY_TRANSFER", "rationale": "Test approval gate"},
        ).json()
        app.dependency_overrides[get_current_user] = lambda: users[Role.OPERATIONS_MANAGER]
        response = client.post(
            f"/api/v1/incidents/proposals/{proposal['id']}/approve",
            json={"decision_reason": "Attempt approval under default kill switch"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "kill_switch_active"
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(IncidentRemediationApproval)) == 0
        assert session.scalar(select(func.count()).select_from(TransferAttempt)) == 1


def test_approved_record_requires_fresh_health_and_still_does_not_execute() -> None:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = add_users(session)
        incident, job = create_incident(session)
        destination_node = session.get(PacsNode, job.destination_node_id)
        assert destination_node is not None
        destination_node.last_health_status = "healthy"
        destination_node.last_health_at = datetime.now(UTC)
        session.commit()

    enabled_settings = get_settings().model_copy(update={"enable_auto_retry": True})
    app.dependency_overrides[get_db] = override_database(engine)
    app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]
    try:
        client = TestClient(app)
        proposal = client.post(
            f"/api/v1/incidents/{incident.id}/proposals",
            json={"requested_action": "RETRY_TRANSFER", "rationale": "Fresh health evidence"},
        ).json()
        app.dependency_overrides[get_current_user] = lambda: users[Role.OPERATIONS_MANAGER]
        with patch("app.incidents.workflow.get_settings", return_value=enabled_settings):
            response = client.post(
                f"/api/v1/incidents/proposals/{proposal['id']}/approve",
                json={"decision_reason": "Fresh destination health verified"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        assert response.json()["approval"]["decision"] == "approved"
        assert response.json()["approval"]["policy_snapshot"]["approval_is_not_execution"] is True
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(IncidentRemediationApproval)) == 1
        assert session.scalar(select(func.count()).select_from(TransferAttempt)) == 1


def test_new_failure_evidence_supersedes_pending_proposal_and_allows_fresh_proposal() -> None:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = add_users(session)
        incident, job = create_incident(session)
        session.commit()

    app.dependency_overrides[get_db] = override_database(engine)
    app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]
    try:
        client = TestClient(app)
        first_response = client.post(
            f"/api/v1/incidents/{incident.id}/proposals",
            json={"requested_action": "RETRY_TRANSFER", "rationale": "Review first outage"},
        )
        assert first_response.status_code == 201
        first_proposal_id = first_response.json()["id"]

        with Session(engine) as session:
            saved_job = session.get(TransferJob, job.id)
            assert saved_job is not None
            record_transfer_failure_incident(
                session,
                saved_job,
                connectivity_classification(),
                redacted_error="DestinationUnavailable: transfer request failed",
                actor_id="worker",
            )
            session.commit()
            stale = session.get(IncidentRemediationProposal, uuid.UUID(first_proposal_id))
            assert stale is not None
            assert stale.status == IncidentProposalStatus.SUPERSEDED
            supersession = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "pacs.incident.proposal.superseded",
                    AuditEvent.entity_id == first_proposal_id,
                )
            )
            assert supersession is not None
            assert supersession.before_state == {
                "incident_id": str(incident.id),
                "proposal_id": first_proposal_id,
                "status": "pending",
                "failure_count": 1,
            }
            assert supersession.after_state == {
                "incident_id": str(incident.id),
                "proposal_id": first_proposal_id,
                "status": "superseded",
                "failure_count": 2,
                "execution_authorized": False,
                "approval_is_not_execution": True,
            }

        app.dependency_overrides[get_current_user] = lambda: users[Role.OPERATIONS_MANAGER]
        for action in ("approve", "reject"):
            stale_decision = client.post(
                f"/api/v1/incidents/proposals/{first_proposal_id}/{action}",
                json={"decision_reason": "Stale proposal must remain inactive"},
            )
            assert stale_decision.status_code == 409
            assert stale_decision.json()["detail"] == "PROPOSAL_ALREADY_DECIDED"

        app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]
        fresh_response = client.post(
            f"/api/v1/incidents/{incident.id}/proposals",
            json={"requested_action": "RETRY_TRANSFER", "rationale": "Review latest outage"},
        )
        assert fresh_response.status_code == 201
        assert fresh_response.json()["status"] == IncidentProposalStatus.PENDING.value
    finally:
        app.dependency_overrides.clear()


def test_new_failure_evidence_supersedes_approved_proposal_without_rewriting_approval() -> None:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = add_users(session)
        incident, job = create_incident(session)
        destination_node = session.get(PacsNode, job.destination_node_id)
        assert destination_node is not None
        destination_node.last_health_status = "healthy"
        destination_node.last_health_at = datetime.now(UTC)
        session.commit()

    enabled_settings = get_settings().model_copy(update={"enable_auto_retry": True})
    app.dependency_overrides[get_db] = override_database(engine)
    app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]
    try:
        client = TestClient(app)
        proposal_response = client.post(
            f"/api/v1/incidents/{incident.id}/proposals",
            json={"requested_action": "RETRY_TRANSFER", "rationale": "Review approved outage"},
        )
        assert proposal_response.status_code == 201
        proposal_id = proposal_response.json()["id"]

        app.dependency_overrides[get_current_user] = lambda: users[Role.OPERATIONS_MANAGER]
        with patch("app.incidents.workflow.get_settings", return_value=enabled_settings):
            approval_response = client.post(
                f"/api/v1/incidents/proposals/{proposal_id}/approve",
                json={"decision_reason": "Synthetic fresh health evidence"},
            )
        assert approval_response.status_code == 200
        assert approval_response.json()["status"] == IncidentProposalStatus.APPROVED.value

        with Session(engine) as session:
            saved_job = session.get(TransferJob, job.id)
            assert saved_job is not None
            approval = session.scalar(
                select(IncidentRemediationApproval).where(
                    IncidentRemediationApproval.proposal_id == uuid.UUID(proposal_id)
                )
            )
            assert approval is not None
            approval_snapshot = {
                "id": approval.id,
                "approver_id": approval.approver_id,
                "approver_role": approval.approver_role,
                "decision": approval.decision,
                "decision_reason": approval.decision_reason,
                "policy_snapshot": dict(approval.policy_snapshot),
                "created_at": approval.created_at,
            }
            transfer_attempt_count = session.scalar(
                select(func.count()).select_from(TransferAttempt)
            )
            record_transfer_failure_incident(
                session,
                saved_job,
                connectivity_classification(),
                redacted_error="DestinationUnavailable: transfer request failed",
                actor_id="worker",
            )
            session.commit()
            stale = session.get(IncidentRemediationProposal, uuid.UUID(proposal_id))
            assert stale is not None
            assert stale.status == IncidentProposalStatus.SUPERSEDED
            approval = session.scalar(
                select(IncidentRemediationApproval).where(
                    IncidentRemediationApproval.proposal_id == stale.id
                )
            )
            assert approval is not None
            assert {
                "id": approval.id,
                "approver_id": approval.approver_id,
                "approver_role": approval.approver_role,
                "decision": approval.decision,
                "decision_reason": approval.decision_reason,
                "policy_snapshot": dict(approval.policy_snapshot),
                "created_at": approval.created_at,
            } == approval_snapshot
            assert (
                session.scalar(select(func.count()).select_from(IncidentRemediationApproval)) == 1
            )
            assert (
                session.scalar(select(func.count()).select_from(TransferAttempt))
                == transfer_attempt_count
            )
            supersession = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "pacs.incident.proposal.superseded",
                    AuditEvent.entity_id == proposal_id,
                )
            )
            assert supersession is not None
            assert supersession.before_state == {
                "incident_id": str(incident.id),
                "proposal_id": proposal_id,
                "status": "approved",
                "failure_count": 1,
            }
            assert supersession.after_state == {
                "incident_id": str(incident.id),
                "proposal_id": proposal_id,
                "status": "superseded",
                "failure_count": 2,
                "execution_authorized": False,
                "approval_is_not_execution": True,
            }

        app.dependency_overrides[get_current_user] = lambda: users[Role.PACS_ADMIN]
        fresh_response = client.post(
            f"/api/v1/incidents/{incident.id}/proposals",
            json={"requested_action": "RETRY_TRANSFER", "rationale": "Review changed evidence"},
        )
        assert fresh_response.status_code == 201
        assert fresh_response.json()["status"] == IncidentProposalStatus.PENDING.value
    finally:
        app.dependency_overrides.clear()


def test_outbox_drain_persists_evidence_with_bounded_retry_and_no_adapter_call() -> None:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        outbox = IncidentPersistenceOutbox(
            transfer_job_id=job.id,
            error_code="DESTINATION_UNAVAILABLE",
            redacted_error="DestinationUnavailable: transfer request failed",
            evidence_json={"classification_rule": "CONNECTIVITY_RETRY_REQUIRES_APPROVAL"},
            status="pending",
            attempt_count=0,
        )
        session.add(outbox)
        session.commit()
        result = drain_incident_persistence_outbox(session, limit=10)
        assert result.selected == 1
        assert result.completed == 1
        assert result.failed == 0
        saved_outbox = session.get(IncidentPersistenceOutbox, outbox.id)
        assert saved_outbox is not None
        assert saved_outbox.status == "completed"
        assert saved_outbox.completed_at is not None
        assert session.scalar(select(func.count()).select_from(IncidentRemediationProposal)) == 0


def test_outbox_drain_does_not_process_stale_preselected_row_after_rollback(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'outbox-race.db'}")
    Base.metadata.create_all(engine)
    created_at = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as session:
        first_job = setup_failed_transfer(session)
        second_job = TransferJob(
            source_node_id=first_job.source_node_id,
            destination_node_id=first_job.destination_node_id,
            study_id=first_job.study_id,
            study_instance_uid=first_job.study_instance_uid,
            accession_number=first_job.accession_number,
            patient_id=first_job.patient_id,
            expected_instance_count=first_job.expected_instance_count,
            status=TransferStatus.FAILED,
            retry_count=0,
            maximum_retries=1,
            idempotency_key="approval-transfer-idempotency-2",
            correlation_id="approval-correlation-2",
            last_error_code="DESTINATION_UNAVAILABLE",
        )
        session.add(second_job)
        session.flush()
        first = IncidentPersistenceOutbox(
            transfer_job_id=first_job.id,
            error_code="DESTINATION_UNAVAILABLE",
            redacted_error="DestinationUnavailable: first request failed",
            evidence_json={},
            status="pending",
            attempt_count=0,
            created_at=created_at,
        )
        second = IncidentPersistenceOutbox(
            transfer_job_id=second_job.id,
            error_code="DESTINATION_UNAVAILABLE",
            redacted_error="DestinationUnavailable: second request failed",
            evidence_json={},
            status="pending",
            attempt_count=0,
            created_at=created_at + timedelta(seconds=1),
        )
        session.add_all([first, second])
        session.commit()

        persistence_calls: list[str] = []

        def fail_first_after_other_worker_completes_second(*args, **kwargs):  # type: ignore[no-untyped-def]
            persistence_calls.append(str(args[1].id))
            if len(persistence_calls) == 1:
                with Session(engine) as concurrent_session:
                    concurrently_completed = concurrent_session.get(
                        IncidentPersistenceOutbox, second.id
                    )
                    assert concurrently_completed is not None
                    concurrently_completed.status = "completed"
                    concurrently_completed.completed_at = datetime.now(UTC)
                    concurrent_session.commit()
                raise RuntimeError("synthetic persistence failure")
            return None

        with patch(
            "app.incidents.recovery.record_transfer_failure_incident",
            side_effect=fail_first_after_other_worker_completes_second,
        ):
            result = drain_incident_persistence_outbox(session, limit=2, max_attempts=2)

        assert result.selected == 1
        assert result.deferred == 1
        assert persistence_calls == [str(first_job.id)]
        session.expire_all()
        saved_second = session.get(IncidentPersistenceOutbox, second.id)
        assert saved_second is not None
        assert saved_second.status == "completed"
        assert saved_second.attempt_count == 0


def test_outbox_drain_fails_exhausted_pending_row_without_persistence_call() -> None:
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = setup_failed_transfer(session)
        outbox = IncidentPersistenceOutbox(
            transfer_job_id=job.id,
            error_code="DESTINATION_UNAVAILABLE",
            redacted_error="DestinationUnavailable: transfer request failed",
            evidence_json={},
            status="pending",
            attempt_count=3,
        )
        session.add(outbox)
        session.commit()

        with patch("app.incidents.recovery.record_transfer_failure_incident") as persist:
            result = drain_incident_persistence_outbox(session, limit=1, max_attempts=3)

        persist.assert_not_called()
        assert result.selected == 1
        assert result.failed == 1
        saved = session.get(IncidentPersistenceOutbox, outbox.id)
        assert saved is not None
        assert saved.status == "failed"
        assert saved.attempt_count == 3
