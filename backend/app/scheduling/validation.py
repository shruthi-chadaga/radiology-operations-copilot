"""Deterministic administrative referral validation, separate from AI prompts."""

from dataclasses import dataclass

from app.ai.schemas import ReferralExtraction


@dataclass(frozen=True)
class ReferralValidationContext:
    patient_id: str | None
    extraction: ReferralExtraction
    imaging_service_exists: bool
    requested_location_active: bool
    identity_conflict: bool
    low_confidence_threshold: float


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    blocks_booking: bool = True


@dataclass(frozen=True)
class ValidationResult:
    is_complete: bool
    requires_human_review: bool
    issues: list[ValidationIssue]


def validate_referral(context: ReferralValidationContext) -> ValidationResult:
    issues: list[ValidationIssue] = []
    extraction = context.extraction
    supported_modalities = {"CT", "MR", "CR", "US", "NM"}

    if not context.patient_id:
        issues.append(ValidationIssue("PATIENT_ID_REQUIRED", "Synthetic patient ID is required"))
    if not extraction.requested_exam.value:
        issues.append(ValidationIssue("REQUESTED_EXAM_REQUIRED", "Requested exam is required"))
    if not extraction.modality.value:
        issues.append(ValidationIssue("MODALITY_REQUIRED", "Modality is required"))
    elif extraction.modality.value not in supported_modalities:
        issues.append(ValidationIssue("UNSUPPORTED_MODALITY", "Modality is not allowlisted"))
    if not extraction.body_region.value:
        issues.append(ValidationIssue("BODY_REGION_REQUIRED", "Body region is required"))
    if not context.imaging_service_exists:
        issues.append(ValidationIssue("UNKNOWN_EXAM", "Imaging service is not recognized"))
    if extraction.preferred_location.value and not context.requested_location_active:
        issues.append(ValidationIssue("INACTIVE_LOCATION", "Requested location is not active"))
    if extraction.authorization_status.value != "approved":
        issues.append(
            ValidationIssue(
                "AUTHORIZATION_NOT_APPROVED",
                "Administrative authorization must be explicitly approved",
            )
        )
    if extraction.missing_or_ambiguous_fields:
        issues.append(
            ValidationIssue(
                "EXTRACTION_AMBIGUOUS",
                "Missing or ambiguous administrative fields require review",
            )
        )

    confidence_fields = (
        extraction.requested_exam,
        extraction.modality,
        extraction.body_region,
        extraction.explicit_priority,
        extraction.preferred_location,
        extraction.contrast_indicator,
        extraction.sedation_indicator,
        extraction.authorization_status,
    )
    if any(
        field.value is not None and field.confidence < context.low_confidence_threshold
        for field in confidence_fields
    ):
        issues.append(
            ValidationIssue("LOW_EXTRACTION_CONFIDENCE", "Low-confidence extraction needs review")
        )
    if extraction.sedation_indicator.value:
        issues.append(
            ValidationIssue("SEDATION_REVIEW_REQUIRED", "Sedation-marked cases require review")
        )
    if context.identity_conflict:
        issues.append(ValidationIssue("IDENTITY_CONFLICT", "Identity conflicts require review"))
    if extraction.requires_human_review and not issues:
        issues.append(
            ValidationIssue("AI_REVIEW_REQUIRED", "The validated AI response requires review")
        )

    requires_review = bool(issues) or extraction.requires_human_review
    return ValidationResult(
        is_complete=not issues and not extraction.requires_human_review,
        requires_human_review=requires_review,
        issues=issues,
    )
