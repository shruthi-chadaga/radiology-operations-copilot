from datetime import datetime

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.imaging.viewer import find_prior_studies, first_instance_id, is_synthetic_study
from app.pacs.models import PacsNode, PacsStudy
from app.pacs.orthanc import OrthancAdapterError, OrthancClient


def test_prior_matching_is_same_patient_modality_and_earlier_date_only() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        node = PacsNode(
            name="Viewer Source",
            node_type="source",
            base_url="http://source:8042",
            dicom_ae_title="SOURCE_VIEWER",
            dicom_host="source",
            dicom_port=4242,
            adapter_key="source-viewer",
        )
        session.add(node)
        session.flush()
        current = PacsStudy(
            node_id=node.id,
            orthanc_study_id="current",
            study_instance_uid="uid-current",
            accession_number="ACC-CURRENT",
            patient_id="SYN-1",
            study_date="20260807",
            study_description="Synthetic CT",
            modality="CT",
            series_count=1,
            instance_count=1,
            metadata_json={"synthetic": True},
            last_seen_at=datetime(2026, 8, 7),
        )
        prior = PacsStudy(
            node_id=node.id,
            orthanc_study_id="prior",
            study_instance_uid="uid-prior",
            accession_number="ACC-PRIOR",
            patient_id="SYN-1",
            study_date="20260101",
            study_description="Synthetic CT",
            modality="CT",
            series_count=1,
            instance_count=1,
            metadata_json={"synthetic": True},
            last_seen_at=datetime(2026, 1, 1),
        )
        wrong_modality = PacsStudy(
            node_id=node.id,
            orthanc_study_id="wrong-modality",
            study_instance_uid="uid-wrong",
            accession_number="ACC-WRONG",
            patient_id="SYN-1",
            study_date="20250101",
            study_description="Synthetic MR",
            modality="MR",
            series_count=1,
            instance_count=1,
            metadata_json={"synthetic": True},
            last_seen_at=datetime(2025, 1, 1),
        )
        future = PacsStudy(
            node_id=node.id,
            orthanc_study_id="future",
            study_instance_uid="uid-future",
            accession_number="ACC-FUTURE",
            patient_id="SYN-1",
            study_date="20270101",
            study_description="Synthetic CT",
            modality="CT",
            series_count=1,
            instance_count=1,
            metadata_json={"synthetic": True},
            last_seen_at=datetime(2027, 1, 1),
        )
        session.add_all([current, prior, wrong_modality, future])
        session.commit()
        assert find_prior_studies(session, current) == [prior]


def test_missing_metadata_attestation_fails_closed_for_viewer() -> None:
    study = PacsStudy(metadata_json=None)

    assert is_synthetic_study(study) is False


def test_first_instance_id_is_deterministic() -> None:
    series = [
        {"instances": [{"orthanc_instance_id": "instance-1"}]},
        {"instances": [{"orthanc_instance_id": "instance-2"}]},
    ]
    assert first_instance_id(series) == "instance-1"
    assert first_instance_id([]) is None


def _client(content_type: str) -> OrthancClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/instances/image/preview"
        return httpx.Response(
            200,
            content=b"preview",
            headers={"content-type": content_type},
        )

    return OrthancClient(
        base_url="http://orthanc-source:8042",
        username="local",
        password="local",
        transport=httpx.MockTransport(handler),
    )


def test_orthanc_rendered_preview_returns_supported_images() -> None:
    content, media_type = _client("image/png").render_instance_preview("image")
    assert content == b"preview"
    assert media_type == "image/png"


def test_orthanc_rendered_preview_rejects_non_image_content() -> None:
    with pytest.raises(OrthancAdapterError, match="supported image"):
        _client("application/dicom").render_instance_preview("image")
