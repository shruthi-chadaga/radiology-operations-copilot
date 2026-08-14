import pytest
from pydantic import ValidationError

from app.incidents.classifier import (
    IncidentCategory,
    IncidentClassificationInput,
    IncidentSeverity,
    classify_incident,
)


@pytest.mark.parametrize(
    ("error_code", "category", "severity", "retry_candidate", "approval_required"),
    [
        (
            "DESTINATION_UNAVAILABLE",
            IncidentCategory.CONNECTIVITY,
            IncidentSeverity.MEDIUM,
            True,
            True,
        ),
        (
            "TIMEOUT",
            IncidentCategory.CONNECTIVITY,
            IncidentSeverity.MEDIUM,
            True,
            True,
        ),
        (
            "TimeoutError",
            IncidentCategory.CONNECTIVITY,
            IncidentSeverity.MEDIUM,
            True,
            True,
        ),
        (
            "ReadTimeout",
            IncidentCategory.CONNECTIVITY,
            IncidentSeverity.MEDIUM,
            True,
            True,
        ),
        (
            "ConnectError",
            IncidentCategory.CONNECTIVITY,
            IncidentSeverity.MEDIUM,
            True,
            True,
        ),
        (
            "HTTPStatusError",
            IncidentCategory.CONNECTIVITY,
            IncidentSeverity.MEDIUM,
            True,
            True,
        ),
        (
            "IDENTITY_MISMATCH",
            IncidentCategory.IDENTITY_MISMATCH,
            IncidentSeverity.CRITICAL,
            False,
            True,
        ),
        (
            "COUNT_MISMATCH",
            IncidentCategory.COUNT_MISMATCH,
            IncidentSeverity.HIGH,
            False,
            True,
        ),
        (
            "FORBIDDEN",
            IncidentCategory.UNAUTHORIZED,
            IncidentSeverity.CRITICAL,
            False,
            True,
        ),
        (
            "TOPOLOGY_INVALID",
            IncidentCategory.CONFIGURATION,
            IncidentSeverity.HIGH,
            False,
            True,
        ),
        (
            "DELETE_REQUEST",
            IncidentCategory.DESTRUCTIVE_ACTION,
            IncidentSeverity.CRITICAL,
            False,
            True,
        ),
        (
            "ACTION_NOT_ALLOWLISTED",
            IncidentCategory.NON_ALLOWLISTED_ACTION,
            IncidentSeverity.CRITICAL,
            False,
            True,
        ),
    ],
)
def test_classifies_known_failure_codes_deterministically(
    error_code: str,
    category: IncidentCategory,
    severity: IncidentSeverity,
    retry_candidate: bool,
    approval_required: bool,
) -> None:
    result = classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-1",
            error_code=error_code,
            error_message="Synthetic failure evidence",
        )
    )

    assert result.category == category
    assert result.severity == severity
    assert result.retry_candidate == retry_candidate
    assert result.approval_required == approval_required
    assert result.execution_authorized is False
    assert result.requires_human_review is True
    assert result.incident_required is True
    assert result.confidence == 1.0


def test_http_authorization_status_overrides_generic_http_error_code() -> None:
    result = classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-http-auth",
            error_code="HTTPStatusError",
            http_status=403,
        )
    )

    assert result.category == IncidentCategory.UNAUTHORIZED
    assert result.retry_candidate is False
    assert result.execution_authorized is False


def test_http_service_unavailable_is_a_connectivity_retry_candidate() -> None:
    result = classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-http-down",
            error_code="HTTPStatusError",
            http_status=503,
        )
    )

    assert result.category == IncidentCategory.CONNECTIVITY
    assert result.retry_candidate is True
    assert result.approval_required is True


def test_identity_evidence_overrides_a_misleading_connectivity_code() -> None:
    result = classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-identity",
            error_code="TIMEOUT",
            error_message="Synthetic adapter timeout",
            identifiers_match=False,
        )
    )

    assert result.category == IncidentCategory.IDENTITY_MISMATCH
    assert result.severity == IncidentSeverity.CRITICAL
    assert result.retry_candidate is False


def test_unknown_failure_defaults_to_human_review_and_no_automation() -> None:
    result = classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-unknown",
            error_code="NEW_UNMAPPED_FAILURE",
            error_message="Synthetic unmapped error",
        )
    )

    assert result.category == IncidentCategory.UNKNOWN
    assert result.severity == IncidentSeverity.HIGH
    assert result.retry_candidate is False
    assert result.approval_required is True
    assert result.incident_required is True


@pytest.mark.parametrize("transfer_status", ["completed", "transferred"])
def test_only_completed_transfer_is_a_no_incident_success(transfer_status: str) -> None:
    result = classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-status",
            transfer_status=transfer_status,
        )
    )

    if transfer_status == "completed":
        assert result.category == IncidentCategory.NO_INCIDENT
        assert result.incident_required is False
        assert result.requires_human_review is False
    else:
        assert result.category == IncidentCategory.UNKNOWN
        assert result.incident_required is True
        assert result.requires_human_review is True

    assert result.retry_candidate is False
    assert result.execution_authorized is False


def test_completed_status_with_error_evidence_fails_closed() -> None:
    result = classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-contradictory",
            transfer_status="completed",
            error_message="Synthetic contradictory error evidence",
        )
    )

    assert result.category == IncidentCategory.UNKNOWN
    assert result.severity == IncidentSeverity.HIGH
    assert result.incident_required is True
    assert result.requires_human_review is True


def test_input_rejects_unbounded_unexpected_or_blank_fields() -> None:
    with pytest.raises(ValidationError):
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-1",
            unexpected="must be rejected",
        )

    with pytest.raises(ValidationError):
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-1",
            error_message="x" * 501,
        )

    with pytest.raises(ValidationError):
        IncidentClassificationInput(
            domain=" ",
            source_entity_type="transfer_job",
            source_entity_id="transfer-1",
        )

    with pytest.raises(ValidationError):
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-1",
            identifiers_match="false",
        )
