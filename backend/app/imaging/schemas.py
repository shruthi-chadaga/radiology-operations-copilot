"""Strict Imaging Workspace metadata and authored-report contracts."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    expected_version_number: int | None = Field(default=None, ge=1)

    @field_validator("indication", "findings", "impression")
    @classmethod
    def authored_content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("authored content must not be blank")
        return value.strip()


class ReportCorrectionRequest(ReportDraftRequest):
    expected_version_number: int = Field(ge=1)
    correction_reason: str = Field(min_length=1, max_length=1000)

    @field_validator("correction_reason")
    @classmethod
    def correction_reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("correction reason must not be blank")
        return value.strip()


class ReportFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version_number: int = Field(ge=1)


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


class ShareCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_label: str = Field(min_length=1, max_length=120)
    expires_in_hours: int = Field(ge=1, le=336)

    @field_validator("recipient_label")
    @classmethod
    def recipient_label_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("recipient label must not be blank")
        return value.strip()


class ShareResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    report_id: str
    study_id: str
    recipient_label: str
    status: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class ShareCreatedResponse(ShareResponse):
    """Creation response; the raw token is returned exactly once, never stored."""

    token: str


class SharePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ShareResponse]


class ShareResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=256)


class SharedReportResponse(BaseModel):
    """Bounded recipient-facing view; no patient identifiers or study metadata."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    recipient_label: str
    status: str
    version: str
    indication: str
    findings: str
    impression: str
    expires_at: str


class ShareEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_email: str = Field(min_length=3, max_length=254)

    @field_validator("recipient_email")
    @classmethod
    def recipient_email_must_be_well_formed(cls, value: str) -> str:
        # Pragmatic pattern; permissive enough for synthetic .local addresses.
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()):
            raise ValueError("recipient_email must be a valid email address")
        return value.strip().lower()
