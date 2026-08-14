"""Strict Imaging Workspace metadata and authored-report contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ImagingWorklistItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    patient_id: str | None
    pacs_patient_id: str
    patient_name: str | None
    patient_birth_date: str | None
    accession_number: str
    modality: str | None
    study_description: str | None
    study_date: str | None
    workflow_status: str
    priority: str
    assigned_reader_id: str | None
    report_status: str
    scheduled_at: datetime | None
    received_at: datetime | None
    pacs_study_id: str | None
    appointment_id: str | None


class ImagingWorklistPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ImagingWorklistItemResponse]
    generated_at: datetime


class PatientTimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    event_id: str
    occurred_at: datetime
    label: str
    detail: str
    status: str


class PatientTimelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str
    external_patient_id: str
    patient_name: str
    events: list[PatientTimelineEvent]


class ViewerStudyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: str
    accession_number: str
    study_instance_uid: str
    study_date: str | None
    modality: str | None
    study_description: str | None
    is_synthetic: bool
    preview_available: bool
    representative_instance_id: str | None
    series_count: int
    instance_count: int


class ViewerComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: ViewerStudyResponse
    priors: list[ViewerStudyResponse]


class ReportDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indication: str = Field(default="", max_length=400)
    findings: str = Field(default="", max_length=12000)
    impression: str = Field(default="", max_length=4000)


class ReportCorrectionRequest(ReportDraftRequest):
    correction_reason: str = Field(min_length=1, max_length=1000)


class ReportVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version_number: int
    kind: str
    author_id: str
    indication: str
    findings: str
    impression: str
    correction_reason: str | None
    created_at: datetime


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    study_id: str
    status: str
    current_version_number: int | None
    finalized_by: str | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime
    versions: list[ReportVersionResponse]
