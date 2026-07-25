"""Typed, non-destructive PACS adapter boundary."""

from typing import Protocol

from app.pacs.schemas import PacsHealth, PacsStudyMetadata, StoreResult


class PacsAdapter(Protocol):
    def health(self) -> PacsHealth: ...

    def list_studies(self) -> list[PacsStudyMetadata]: ...

    def find_study(self, study_instance_uid: str) -> list[PacsStudyMetadata]: ...

    def upload_instance(self, dicom_bytes: bytes) -> str: ...

    def send_study(self, orthanc_study_id: str, destination_name: str) -> StoreResult: ...
