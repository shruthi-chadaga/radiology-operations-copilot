from io import BytesIO

import pydicom

from app.pacs.schemas import PacsHealth, PacsStudyMetadata, StoreResult
from app.pacs.seed_dicom import seed_source_studies


class UploadPacs:
    def __init__(self) -> None:
        self.datasets: list[object] = []

    def health(self) -> PacsHealth:
        return PacsHealth(healthy=True, node_name="source", version="test", latency_ms=1)

    def list_studies(self) -> list[PacsStudyMetadata]:
        return []

    def find_study(self, study_instance_uid: str) -> list[PacsStudyMetadata]:
        return []

    def upload_instance(self, dicom_bytes: bytes) -> str:
        dataset = pydicom.dcmread(BytesIO(dicom_bytes))
        self.datasets.append(dataset)
        return str(dataset.SOPInstanceUID)

    def send_study(self, orthanc_study_id: str, destination_name: str) -> StoreResult:
        return StoreResult(accepted=True, response_path=None)


def test_source_seed_uses_stable_synthetic_uids_and_no_pixels() -> None:
    first = UploadPacs()
    second = UploadPacs()

    first_ids = seed_source_studies(first, count=3)
    second_ids = seed_source_studies(second, count=3)

    assert first_ids == second_ids
    assert len(first_ids) == 3
    assert all(str(dataset.PatientID).startswith("SYN-PACS-") for dataset in first.datasets)
    assert all("PixelData" not in dataset for dataset in first.datasets)
