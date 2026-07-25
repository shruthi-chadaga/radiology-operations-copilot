"""Upload deterministic, metadata-only synthetic DICOM objects to source Orthanc."""

from app.pacs.adapter import PacsAdapter
from app.pacs.dependencies import get_pacs_adapters
from app.pacs.synthetic_dicom import SyntheticStudySpec, create_synthetic_dicom

_UID_ROOT = "1.2.826.0.1.3680043.10.5432"


def seed_source_studies(adapter: PacsAdapter, *, count: int = 5) -> list[str]:
    if count < 1 or count > 20:
        raise ValueError("Synthetic PACS seed count must be between 1 and 20")
    instance_ids: list[str] = []
    for index in range(1, count + 1):
        suffix = str(index)
        payload = create_synthetic_dicom(
            SyntheticStudySpec(
                external_patient_id=f"SYN-PACS-{index:04d}",
                patient_name=f"SyntheticPacs{index:04d}^Example",
                accession_number=f"ACC-SP-{index:04d}",
                modality="OT",
                study_description="Synthetic non-clinical PACS transfer object",
                study_instance_uid=f"{_UID_ROOT}.1.{suffix}",
                series_instance_uid=f"{_UID_ROOT}.2.{suffix}",
                sop_instance_uid=f"{_UID_ROOT}.3.{suffix}",
            )
        )
        instance_ids.append(adapter.upload_instance(payload))
    return instance_ids


def main() -> None:
    source = get_pacs_adapters().get("source")
    if source is None:
        raise RuntimeError("Source PACS adapter is not configured")
    instance_ids = seed_source_studies(source)
    print(f"Seeded {len(instance_ids)} deterministic synthetic PACS objects.")


if __name__ == "__main__":
    main()
