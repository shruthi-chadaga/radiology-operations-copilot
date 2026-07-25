"""Strict structured-output contracts for provider-agnostic AI assistance."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ExtractedField(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    value: T | None
    confidence: float = Field(ge=0, le=1)
    source_excerpt: str | None = Field(default=None, max_length=500)


class ReferralExtraction(BaseModel):
    """Administrative facts only; no diagnosis or clinical suitability fields exist."""

    model_config = ConfigDict(extra="forbid")

    requested_exam: ExtractedField[str]
    modality: ExtractedField[str]
    body_region: ExtractedField[str]
    laterality: ExtractedField[str]
    explicit_priority: ExtractedField[str]
    preferred_location: ExtractedField[str] = ExtractedField(
        value=None, confidence=1.0, source_excerpt=None
    )
    contrast_indicator: ExtractedField[str]
    sedation_indicator: ExtractedField[str]
    authorization_status: ExtractedField[str]
    missing_or_ambiguous_fields: list[str]
    requires_human_review: bool
    review_reasons: list[str]
    model_name: str
    prompt_version: str
