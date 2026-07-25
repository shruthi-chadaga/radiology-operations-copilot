"""Strict scheduling API request and response contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.scheduling.validation import ValidationIssue


class ReferralCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str
    source_text: str = Field(min_length=5, max_length=20_000)
    synthetic_data_confirmed: Literal[True]

    @field_validator("source_text")
    @classmethod
    def require_synthetic_marker(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("[SYNTHETIC]"):
            raise ValueError("source_text must begin with [SYNTHETIC]")
        return normalized


class ReferralResponse(BaseModel):
    id: str
    referral_number: str
    patient_id: str
    source_text: str
    requested_exam: str | None
    modality: str | None
    body_region: str | None
    status: str
    completeness_status: str
    extraction_confidence: float | None


class ReferralPage(BaseModel):
    items: list[ReferralResponse]


class ValidationIssueResponse(BaseModel):
    code: str
    message: str
    blocks_booking: bool

    @classmethod
    def from_issue(cls, issue: ValidationIssue) -> "ValidationIssueResponse":
        return cls(code=issue.code, message=issue.message, blocks_booking=issue.blocks_booking)


class ValidationResponse(BaseModel):
    is_complete: bool
    requires_human_review: bool
    issues: list[ValidationIssueResponse]


class SlotRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_location_code: str | None = None
    preferred_time_of_day: str | None = Field(default=None, pattern="^(morning|afternoon|evening)$")


class SlotRecommendationResponse(BaseModel):
    slot_id: str
    start_time: datetime
    score: int
    explanation: str
    version: int


class SlotRecommendationPage(BaseModel):
    items: list[SlotRecommendationResponse]


class AppointmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    referral_id: str
    slot_id: str
    imaging_service_id: str
    expected_slot_version: int = Field(ge=1)
    booking_reason: str = Field(min_length=5, max_length=500)


class AppointmentCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=5, max_length=500)


class AppointmentReschedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_slot_id: str
    expected_new_slot_version: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=500)


class AppointmentResponse(BaseModel):
    id: str
    appointment_number: str
    accession_number: str
    referral_id: str
    slot_id: str
    status: str
