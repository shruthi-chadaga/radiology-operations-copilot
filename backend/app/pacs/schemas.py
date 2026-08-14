"""Strict PACS metadata and API schemas; pixel data is never represented."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PacsHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    healthy: bool
    node_name: str | None
    version: str | None
    latency_ms: int
    error: str | None = None


class PacsStudyMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orthanc_study_id: str
    study_instance_uid: str
    accession_number: str
    patient_id: str
    patient_name: str | None = None
    patient_birth_date: str | None = None
    patient_sex: str | None = None
    study_date: str | None
    study_description: str | None
    modality: str | None = None
    series_count: int = Field(ge=0)
    instance_count: int = Field(ge=0)


class StoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    response_path: str | None


class PacsNodeResponse(BaseModel):
    id: str
    name: str
    node_type: str
    dicom_ae_title: str
    active: bool
    last_health_status: str | None
    last_health_at: datetime | None


class PacsNodePage(BaseModel):
    items: list[PacsNodeResponse]


class HealthCheckResponse(BaseModel):
    id: str
    node_id: str
    status: str
    latency_ms: int
    checked_at: datetime


class InventorySyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    synthetic_data_confirmed: Literal[True]


class InventorySyncResponse(BaseModel):
    node_id: str
    study_count: int


class PacsStudyResponse(BaseModel):
    id: str
    node_id: str
    study_instance_uid: str
    accession_number: str
    patient_id: str
    patient_name: str | None = None
    patient_birth_date: str | None = None
    patient_sex: str | None = None
    study_date: str | None = None
    study_description: str | None
    modality: str | None = None
    series_count: int
    instance_count: int


class PacsStudyPage(BaseModel):
    items: list[PacsStudyResponse]


class TransferCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_node_id: str
    destination_node_id: str
    study_id: str


class TransferResponse(BaseModel):
    id: str
    source_node_id: str
    destination_node_id: str
    study_id: str
    status: str
    retry_count: int
    maximum_retries: int
    correlation_id: str


class TransferPage(BaseModel):
    items: list[TransferResponse]


class ReconciliationResponse(BaseModel):
    id: str
    transfer_job_id: str
    outcome: str
    identifiers_match: bool
    instance_counts_match: bool
    source_instance_count: int = Field(ge=0)
    destination_instance_count: int = Field(ge=0)


class TransferAttemptResponse(BaseModel):
    id: str
    attempt_number: int
    outcome: str
    started_at: datetime
    completed_at: datetime | None
    redacted_error: str | None


class TransferDetailResponse(TransferResponse):
    attempts: list[TransferAttemptResponse]
    reconciliations: list[ReconciliationResponse]


class PacsDashboardResponse(BaseModel):
    total_studies: int
    healthy_nodes: int
    total_nodes: int
    modality_counts: dict[str, int]
    recent_study_count: int
    recent_transfer_count: int


class DicomTagItem(BaseModel):
    tag: str
    name: str
    value: str | None
    group: str


class DicomTagsResponse(BaseModel):
    study_id: str
    tags: list[DicomTagItem]


class SeriesInstanceRef(BaseModel):
    orthanc_instance_id: str
    sop_instance_uid: str
    instance_number: str | None = None


class SeriesItem(BaseModel):
    orthanc_series_id: str
    series_instance_uid: str
    series_number: str | None = None
    series_description: str | None = None
    modality: str | None = None
    instance_count: int = Field(ge=0)
    instances: list[SeriesInstanceRef] = []
    tags: list[DicomTagItem] = []


class SeriesListResponse(BaseModel):
    study_id: str
    series: list[SeriesItem]
