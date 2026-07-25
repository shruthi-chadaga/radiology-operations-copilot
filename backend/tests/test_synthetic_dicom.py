from io import BytesIO

import pydicom

from app.pacs.synthetic_dicom import SyntheticStudySpec, create_synthetic_dicom


def test_synthetic_dicom_has_fictional_linkage_and_no_pixel_data() -> None:
    payload = create_synthetic_dicom(
        SyntheticStudySpec(
            external_patient_id="SYN-0021",
            patient_name="Synthetic21^Example",
            accession_number="ACC-SYN-000021",
            modality="OT",
            study_description="Synthetic transfer test object",
            study_instance_uid="1.2.826.0.1.3680043.10.5432.1.1",
            series_instance_uid="1.2.826.0.1.3680043.10.5432.2.1",
            sop_instance_uid="1.2.826.0.1.3680043.10.5432.3.1",
        )
    )
    dataset = pydicom.dcmread(BytesIO(payload))

    assert dataset.PatientID == "SYN-0021"
    assert dataset.PatientName == "Synthetic21^Example"
    assert dataset.AccessionNumber == "ACC-SYN-000021"
    assert dataset.StudyInstanceUID == "1.2.826.0.1.3680043.10.5432.1.1"
    assert dataset.SeriesInstanceUID == "1.2.826.0.1.3680043.10.5432.2.1"
    assert dataset.SOPInstanceUID == "1.2.826.0.1.3680043.10.5432.3.1"
    assert "PixelData" not in dataset
    assert dataset.SeriesDescription == "SYNTHETIC NON-CLINICAL OBJECT"
