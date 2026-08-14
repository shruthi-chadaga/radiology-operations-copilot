"""Upload deterministic, metadata-only synthetic DICOM objects to source Orthanc."""

from dataclasses import dataclass

from app.pacs.adapter import PacsAdapter
from app.pacs.dependencies import get_pacs_adapters
from app.pacs.synthetic_dicom import SyntheticStudySpec, create_synthetic_dicom

_UID_ROOT = "1.2.826.0.1.3680043.10.5432"


@dataclass(frozen=True)
class _ModalitySpec:
    modality: str
    description: str


_MODALITIES: list[_ModalitySpec] = [
    _ModalitySpec("CT", "SYNTHETIC — Routine CT chest without contrast"),
    _ModalitySpec("MR", "SYNTHETIC — MR brain with and without contrast"),
    _ModalitySpec("US", "SYNTHETIC — Abdominal ultrasound survey"),
    _ModalitySpec("XA", "SYNTHETIC — Diagnostic angiography lower extremity"),
    _ModalitySpec("CR", "SYNTHETIC — Computed radiography chest PA and lateral"),
    _ModalitySpec("NM", "SYNTHETIC — Nuclear medicine bone scan whole body"),
    _ModalitySpec("CT", "SYNTHETIC — CT abdomen and pelvis with IV contrast"),
    _ModalitySpec("MR", "SYNTHETIC — MR lumbar spine without contrast"),
    _ModalitySpec("US", "SYNTHETIC — Thyroid ultrasound with Doppler"),
    _ModalitySpec("CT", "SYNTHETIC — CT head without contrast"),
]


def seed_source_studies(adapter: PacsAdapter, *, count: int = 5) -> list[str]:
    if count < 1 or count > 20:
        raise ValueError("Synthetic PACS seed count must be between 1 and 20")
    instance_ids: list[str] = []
    for index in range(1, count + 1):
        suffix = str(index)
        mod_spec = _MODALITIES[(index - 1) % len(_MODALITIES)]
        payload = create_synthetic_dicom(
            SyntheticStudySpec(
                external_patient_id=f"SYN-PACS-{index:04d}",
                patient_name=f"SyntheticPacs{index:04d}^Example",
                accession_number=f"ACC-SP-{index:04d}",
                modality=mod_spec.modality,
                study_description=mod_spec.description,
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
