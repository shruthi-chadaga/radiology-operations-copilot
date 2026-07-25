import pytest

from app.ai.schemas import ExtractedField, ReferralExtraction
from app.scheduling.validation import ReferralValidationContext, validate_referral


def extraction(**overrides: object) -> ReferralExtraction:
    values: dict[str, object] = {
        "requested_exam": ExtractedField(
            value="CT abdomen", confidence=0.95, source_excerpt="CT abdomen"
        ),
        "modality": ExtractedField(value="CT", confidence=0.99, source_excerpt="CT"),
        "body_region": ExtractedField(value="abdomen", confidence=0.95, source_excerpt="abdomen"),
        "laterality": ExtractedField(value=None, confidence=1.0, source_excerpt=None),
        "explicit_priority": ExtractedField(
            value="routine", confidence=0.9, source_excerpt="routine"
        ),
        "contrast_indicator": ExtractedField(value=None, confidence=1.0, source_excerpt=None),
        "sedation_indicator": ExtractedField(value=None, confidence=1.0, source_excerpt=None),
        "authorization_status": ExtractedField(
            value="approved", confidence=0.9, source_excerpt="approved"
        ),
        "missing_or_ambiguous_fields": [],
        "requires_human_review": False,
        "review_reasons": [],
        "model_name": "mock-v1",
        "prompt_version": "referral-extraction-v1",
    }
    values.update(overrides)
    return ReferralExtraction.model_validate(values)


def test_complete_referral_passes_deterministic_validation() -> None:
    result = validate_referral(
        ReferralValidationContext(
            patient_id="SYN-0001",
            extraction=extraction(),
            imaging_service_exists=True,
            requested_location_active=True,
            identity_conflict=False,
            low_confidence_threshold=0.8,
        )
    )

    assert result.is_complete is True
    assert result.requires_human_review is False
    assert result.issues == []


def test_sedation_identity_and_low_confidence_always_require_human_review() -> None:
    result = validate_referral(
        ReferralValidationContext(
            patient_id="SYN-0001",
            extraction=extraction(
                sedation_indicator=ExtractedField(
                    value="required", confidence=0.95, source_excerpt="sedation required"
                ),
                modality=ExtractedField(value="CT", confidence=0.6, source_excerpt="CT"),
            ),
            imaging_service_exists=True,
            requested_location_active=True,
            identity_conflict=True,
            low_confidence_threshold=0.8,
        )
    )

    assert result.requires_human_review is True
    assert {issue.code for issue in result.issues} == {
        "LOW_EXTRACTION_CONFIDENCE",
        "SEDATION_REVIEW_REQUIRED",
        "IDENTITY_CONFLICT",
    }
    assert all(issue.blocks_booking for issue in result.issues)


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        (
            {
                "authorization_status": ExtractedField(
                    value="denied", confidence=0.99, source_excerpt="denied"
                )
            },
            "AUTHORIZATION_NOT_APPROVED",
        ),
        ({"missing_or_ambiguous_fields": ["laterality"]}, "EXTRACTION_AMBIGUOUS"),
        ({"requires_human_review": True}, "AI_REVIEW_REQUIRED"),
        (
            {"body_region": ExtractedField(value=None, confidence=1.0, source_excerpt=None)},
            "BODY_REGION_REQUIRED",
        ),
        (
            {
                "modality": ExtractedField(
                    value="UNKNOWN", confidence=0.99, source_excerpt="UNKNOWN"
                )
            },
            "UNSUPPORTED_MODALITY",
        ),
    ],
)
def test_ambiguity_review_flags_and_unaccepted_values_block_ready_status(
    overrides: dict[str, object], expected_code: str
) -> None:
    result = validate_referral(
        ReferralValidationContext(
            patient_id="SYN-0001",
            extraction=extraction(**overrides),
            imaging_service_exists=True,
            requested_location_active=True,
            identity_conflict=False,
            low_confidence_threshold=0.8,
        )
    )

    assert result.is_complete is False
    assert result.requires_human_review is True
    assert expected_code in {issue.code for issue in result.issues}
