from datetime import datetime

import pytest
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
    save_draft,
)
from app.pacs.models import PacsNode, PacsStudy


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
            select(RadiologyReportVersion).order_by(
                RadiologyReportVersion.version_number
            )
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

    report, _ = finalize_report(session, report_id=report.id, author_id="reader-1")
    session.commit()
    assert report.status == ReportStatus.FINALIZED
    assert [version.version_number for version in _versions(session)] == [1, 2]

    with pytest.raises(ReportWorkflowError, match="finalized report cannot be edited"):
        save_draft(
            session,
            study_id=study.id,
            author_id="reader-1",
            indication="changed",
            findings="changed",
            impression="changed",
        )

    report, correction = create_correction(
        session,
        report_id=report.id,
        author_id="reader-2",
        correction_reason="Synthetic correction reason",
        indication="new indication",
        findings="new findings",
        impression="new impression",
    )
    session.commit()
    assert report.status == ReportStatus.CORRECTION_PENDING
    assert [version.version_number for version in _versions(session)] == [1, 2, 3]
    assert correction.correction_reason == "Synthetic correction reason"

    report, corrected_final = finalize_report(
        session, report_id=report.id, author_id="reader-2"
    )
    assert report.status == ReportStatus.FINALIZED
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
