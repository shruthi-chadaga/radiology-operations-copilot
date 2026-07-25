"""Minimal non-clinical DICOM generation using conspicuously synthetic identifiers."""

from dataclasses import dataclass
from io import BytesIO

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import UID, ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid


@dataclass(frozen=True)
class SyntheticStudySpec:
    external_patient_id: str
    patient_name: str
    accession_number: str
    modality: str
    study_description: str
    study_date: str = "20260719"
    study_instance_uid: str | None = None
    series_instance_uid: str | None = None
    sop_instance_uid: str | None = None


def create_synthetic_dicom(spec: SyntheticStudySpec) -> bytes:
    if not spec.external_patient_id.startswith("SYN-"):
        raise ValueError("Only explicitly synthetic patient IDs are allowed")
    if "Synthetic" not in spec.patient_name:
        raise ValueError("Synthetic patient names must be conspicuously labeled")

    sop_instance_uid = UID(spec.sop_instance_uid) if spec.sop_instance_uid else generate_uid()
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    dataset = FileDataset("", {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SpecificCharacterSet = "ISO_IR 100"
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = sop_instance_uid
    dataset.StudyInstanceUID = spec.study_instance_uid or generate_uid()
    dataset.SeriesInstanceUID = spec.series_instance_uid or generate_uid()
    dataset.PatientID = spec.external_patient_id
    dataset.PatientName = spec.patient_name
    dataset.PatientBirthDate = "19700101"
    dataset.PatientSex = "O"
    dataset.AccessionNumber = spec.accession_number
    dataset.Modality = spec.modality
    dataset.StudyDate = spec.study_date
    dataset.SeriesDate = spec.study_date
    dataset.ContentDate = spec.study_date
    dataset.StudyDescription = spec.study_description
    dataset.SeriesDescription = "SYNTHETIC NON-CLINICAL OBJECT"
    dataset.SeriesNumber = "1"
    dataset.InstanceNumber = "1"
    dataset.ImageType = ["DERIVED", "SECONDARY"]
    dataset.Manufacturer = "Radiology Operations Copilot Synthetic Generator"

    output = BytesIO()
    dataset.save_as(output, enforce_file_format=True)
    return output.getvalue()
