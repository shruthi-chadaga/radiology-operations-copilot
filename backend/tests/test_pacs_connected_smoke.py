from app.pacs.connected_smoke import check_connected_pacs
from app.pacs.schemas import PacsHealth, PacsStudyMetadata, StoreResult


class FakePacs:
    def __init__(self, *, node_name: str, studies: list[PacsStudyMetadata]) -> None:
        self.node_name = node_name
        self.studies = studies

    def health(self) -> PacsHealth:
        return PacsHealth(
            healthy=True,
            node_name=self.node_name,
            version="test",
            latency_ms=1,
        )

    def list_studies(self) -> list[PacsStudyMetadata]:
        return self.studies

    def find_study(self, study_instance_uid: str) -> list[PacsStudyMetadata]:
        return [study for study in self.studies if study.study_instance_uid == study_instance_uid]

    def upload_instance(self, dicom_bytes: bytes) -> str:
        raise AssertionError("Connected smoke must not upload instances")

    def send_study(self, orthanc_study_id: str, destination_name: str) -> StoreResult:
        raise AssertionError("Connected smoke must not send studies")


def synthetic_metadata(orthanc_study_id: str) -> PacsStudyMetadata:
    return PacsStudyMetadata(
        orthanc_study_id=orthanc_study_id,
        study_instance_uid=f"1.2.826.0.1.3680043.8.498.{orthanc_study_id[-1]}",
        accession_number=f"ACC-SYN-{orthanc_study_id[-1]}",
        patient_id=f"SYN-000{orthanc_study_id[-1]}",
        study_date="20260719",
        study_description="Synthetic connected smoke study",
        series_count=1,
        instance_count=1,
    )


def test_connected_smoke_returns_health_and_metadata_only_inventory_evidence() -> None:
    evidence = check_connected_pacs(
        {
            "source": FakePacs(node_name="Source", studies=[synthetic_metadata("study-1")]),
            "destination": FakePacs(
                node_name="Destination",
                studies=[synthetic_metadata("study-2")],
            ),
        }
    )

    assert evidence == {
        "source": {"node_name": "Source", "study_count": 1},
        "destination": {"node_name": "Destination", "study_count": 1},
        "metadata_only": True,
        "synthetic_markers_validated": True,
    }


def test_connected_smoke_accepts_the_deterministic_synthetic_seed_accession_prefix() -> None:
    source_study = synthetic_metadata("study-1").model_copy(
        update={"accession_number": "ACC-SP-0001"}
    )

    evidence = check_connected_pacs(
        {
            "source": FakePacs(node_name="Source", studies=[source_study]),
            "destination": FakePacs(node_name="Destination", studies=[]),
        }
    )

    assert evidence["synthetic_markers_validated"] is True
