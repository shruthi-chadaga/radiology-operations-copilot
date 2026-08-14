from datetime import datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.imaging.models import (
    ImagingWorklistItem,
    ImagingWorklistStatus,
    RadiologyReportVersion,
    ReportStatus,
)
from app.imaging.reporting import (
    ReportWorkflowError,
    create_correction,
    finalize_report,
    get_report,
    save_draft,
)
from app.imaging.schemas import ReportCorrectionRequest, ReportDraftRequest
from app.pacs.models import PacsNode, PacsStudy
from app.scheduling.models import SyntheticPatient  # noqa: F401


def _session() -> tuple[Session, PacsStudy]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    node = PacsNode(
        name="Report Node",
        node_type="source",
        base_url="http://source",
        dicom_ae_title="REPORT",
        dicom_host="source",
        dicom_port=4242,
        adapter_key="report-node",
    )
    session.add(node)
    session.flush()
    study = PacsStudy(
        node_id=node.id,
        orthanc_study_id="report-study",
        study_instance_uid="uid-report",
        accession_number="ACC-REPORT",
        patient_id="SYN-REPORT",
        study_date="20260807",
        modality="CT",
        series_count=1,
        instance_count=1,
        metadata_json={"synthetic": True},
        last_seen_at=datetime(2026, 8, 7),
    )
    session.add(study)
    session.commit()
    return session, study


def _versions(session: Session) -> list[RadiologyReportVersion]:
    return list(
        session.scalars(
            select(RadiologyReportVersion).order_by(RadiologyReportVersion.version_number)
        )
    )


def test_report_versions_are_immutable_and_correction_is_append_only() -> None:
    session, study = _session()
    report, draft = save_draft(
        session,
        study_id=study.id,
        author_id="reader-1",
        indication="Synthetic indication",
        findings="Synthetic findings",
        impression="Synthetic impression",
    )
    session.commit()
    assert draft.version_number == 1

    report, _ = finalize_report(
        session,
        report_id=report.id,
        author_id="reader-1",
        expected_version_number=1,
    )
    session.commit()
    assert report.status == ReportStatus.FINALIZED
    assert report.finalized_by == "reader-1"
    assert [version.version_number for version in _versions(session)] == [1, 2]

    with pytest.raises(ReportWorkflowError, match="finalized report cannot be edited"):
        save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="changed",
            findings="changed",
            impression="changed",
            expected_version_number=2,
        )

    report, correction = create_correction(
        session,
        report_id=report.id,
        author_id="reader-2",
        correction_reason="Synthetic correction reason",
        indication="new indication",
        findings="new findings",
        impression="new impression",
        expected_version_number=2,
    )
    session.commit()
    assert report.status == ReportStatus.CORRECTION_PENDING
    assert [version.version_number for version in _versions(session)] == [1, 2, 3]
    assert correction.correction_reason == "Synthetic correction reason"

    report, corrected_final = finalize_report(
        session,
        report_id=report.id,
        author_id="reader-2",
        expected_version_number=3,
    )
    assert report.status == ReportStatus.FINALIZED
    assert report.finalized_by == "reader-2"
    session.commit()
    assert [version.version_number for version in _versions(session)] == [1, 2, 3, 4]
    assert corrected_final.kind.value == "final"
    session.close()


def test_correction_pending_worklist_state_is_persistable() -> None:
    session, study = _session()
    item = ImagingWorklistItem(
        pacs_patient_id=study.patient_id,
        pacs_study_id=study.id,
        accession_number=study.accession_number,
        workflow_status=ImagingWorklistStatus.CORRECTION_PENDING,
        report_status="correction_pending",
    )
    session.add(item)
    session.commit()
    loaded = session.get(ImagingWorklistItem, item.id)
    assert loaded is not None
    assert loaded.workflow_status == ImagingWorklistStatus.CORRECTION_PENDING
    session.close()


@pytest.mark.parametrize("field", ["indication", "findings", "impression"])
def test_report_draft_schema_rejects_whitespace_only_authored_content(field: str) -> None:
    values = {
        "indication": "Synthetic indication",
        "findings": "Synthetic findings",
        "impression": "Synthetic impression",
    }
    values[field] = " \t\n"

    with pytest.raises(ValidationError):
        ReportDraftRequest(**values)


@pytest.mark.parametrize("field", ["indication", "findings", "impression", "correction_reason"])
def test_report_correction_schema_rejects_whitespace_only_authored_content(field: str) -> None:
    values = {
        "indication": "Synthetic indication",
        "findings": "Synthetic findings",
        "impression": "Synthetic impression",
        "correction_reason": "Synthetic correction reason",
        "expected_version_number": 1,
    }
    values[field] = " \t\n"

    with pytest.raises(ValidationError):
        ReportCorrectionRequest(**values)


def test_report_draft_schema_normalizes_surrounding_whitespace() -> None:
    payload = ReportDraftRequest(
        indication="  Synthetic indication  ",
        findings="\tSynthetic findings\n",
        impression=" Synthetic impression ",
    )
    assert payload.indication == "Synthetic indication"
    assert payload.findings == "Synthetic findings"
    assert payload.impression == "Synthetic impression"


def test_save_draft_persists_normalized_authored_content() -> None:
    session, study = _session()
    try:
        _, version = save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="  Synthetic indication  ",
            findings="\tSynthetic findings\n",
            impression=" Synthetic impression ",
        )
        assert version.indication == "Synthetic indication"
        assert version.findings == "Synthetic findings"
        assert version.impression == "Synthetic impression"
    finally:
        session.close()


@pytest.mark.parametrize("field", ["indication", "findings", "impression"])
def test_save_draft_rejects_whitespace_only_authored_content(field: str) -> None:
    session, study = _session()
    try:
        values = {
            "indication": "Synthetic indication",
            "findings": "Synthetic findings",
            "impression": "Synthetic impression",
        }
        values[field] = " \t\n"

        with pytest.raises(ReportWorkflowError, match=f"{field} must not be blank") as error:
            save_draft(session, study_id=study.id, author_id="reader-1", **values)
        assert error.value.status_code == 422
    finally:
        session.close()


def test_report_correction_schema_normalizes_surrounding_whitespace() -> None:
    payload = ReportCorrectionRequest(
        indication="  Synthetic indication  ",
        findings="\tSynthetic findings\n",
        impression=" Synthetic impression ",
        correction_reason=" Synthetic correction reason ",
        expected_version_number=1,
    )
    assert payload.indication == "Synthetic indication"
    assert payload.findings == "Synthetic findings"
    assert payload.impression == "Synthetic impression"
    assert payload.correction_reason == "Synthetic correction reason"


@pytest.mark.parametrize("field", ["indication", "findings", "impression", "correction_reason"])
def test_correction_rejects_whitespace_only_authored_content(field: str) -> None:
    session, study = _session()
    try:
        report, _ = save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="Synthetic indication",
            findings="Synthetic findings",
            impression="Synthetic impression",
        )
        session.commit()
        report, _ = finalize_report(
            session,
            report_id=report.id,
            author_id="reader-1",
            expected_version_number=1,
        )
        session.commit()
        values = {
            "indication": "Synthetic corrected indication",
            "findings": "Synthetic corrected findings",
            "impression": "Synthetic corrected impression",
            "correction_reason": "Synthetic correction reason",
            "expected_version_number": 2,
        }
        values[field] = " \t\n"

        with pytest.raises(ReportWorkflowError, match=f"{field} must not be blank"):
            create_correction(
                session,
                report_id=report.id,
                author_id="reader-2",
                **values,
            )
        assert len(_versions(session)) == 2
    finally:
        session.close()


def test_report_access_fails_closed_for_missing_metadata_attestation() -> None:
    session, study = _session()
    try:
        study.metadata_json = None
        session.commit()
        assert get_report(session, study.id) is None
    finally:
        session.close()


# SQLite verifies the stale-version path; live PostgreSQL lock behavior remains a later gate.
def test_stale_draft_save_is_rejected_with_shared_sessions() -> None:
    session, study = _session()
    other_session = Session(session.get_bind())
    try:
        report, _ = save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="Synthetic indication",
            findings="Synthetic findings",
            impression="Synthetic impression",
        )
        session.commit()

        save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="Synthetic revised indication",
            findings="Synthetic revised findings",
            impression="Synthetic revised impression",
            expected_version_number=1,
        )
        session.commit()

        with pytest.raises(ReportWorkflowError, match="stale report version") as error:
            save_draft(
                other_session,
                study_id=study.id,
                author_id="reader-2",
                indication="Synthetic stale indication",
                findings="Synthetic stale findings",
                impression="Synthetic stale impression",
                expected_version_number=1,
            )
        assert error.value.status_code == 409
        assert len(_versions(other_session)) == 2
        assert other_session.get(type(report), report.id).current_version_number == 2
    finally:
        other_session.close()
        session.close()


def test_stale_correction_creation_is_rejected() -> None:
    session, study = _session()
    try:
        report, _ = save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="Synthetic indication",
            findings="Synthetic findings",
            impression="Synthetic impression",
        )
        session.commit()
        report, _ = finalize_report(
            session,
            report_id=report.id,
            author_id="reader-1",
            expected_version_number=1,
        )
        session.commit()
        create_correction(
            session,
            report_id=report.id,
            author_id="reader-1",
            correction_reason="Synthetic correction reason",
            indication="Synthetic corrected indication",
            findings="Synthetic corrected findings",
            impression="Synthetic corrected impression",
            expected_version_number=2,
        )
        session.commit()

        with pytest.raises(ReportWorkflowError, match="stale report version") as error:
            create_correction(
                session,
                report_id=report.id,
                author_id="reader-2",
                correction_reason="Synthetic stale correction reason",
                indication="Synthetic stale indication",
                findings="Synthetic stale findings",
                impression="Synthetic stale impression",
                expected_version_number=2,
            )
        assert error.value.status_code == 409
        assert [version.version_number for version in _versions(session)] == [1, 2, 3]

    finally:
        session.close()


def test_stale_finalization_is_rejected() -> None:
    session, study = _session()
    try:
        report, _ = save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="Synthetic indication",
            findings="Synthetic findings",
            impression="Synthetic impression",
        )
        session.commit()
        save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="Synthetic revised indication",
            findings="Synthetic revised findings",
            impression="Synthetic revised impression",
            expected_version_number=1,
        )
        session.commit()

        with pytest.raises(ReportWorkflowError, match="stale report version") as error:
            finalize_report(
                session,
                report_id=report.id,
                author_id="reader-2",
                expected_version_number=1,
            )
        assert error.value.status_code == 409
        assert [version.version_number for version in _versions(session)] == [1, 2]

    finally:
        session.close()
