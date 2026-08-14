import pytest
from pydantic import ValidationError

from app.incidents.classifier import (
    IncidentCategory,
    IncidentClassificationInput,
    classify_incident,
)
from app.incidents.policy import (
    IncidentPolicyInput,
    PolicyDecision,
    PolicyDecisionCode,
    evaluate_incident_policy,
)


def valid_input(**overrides: object) -> IncidentPolicyInput:
    values: dict[str, object] = {
        "automation_enabled": True,
        "confidence": 1.0,
        "confidence_threshold": 0.8,
        "category": IncidentCategory.CONNECTIVITY,
        "retry_candidate": True,
        "requested_action": "RETRY_TRANSFER",
        "attempt_count": 0,
        "attempt_limit": 1,
        "destination_node_id": "destination-node-1",
        "health_node_id": "destination-node-1",
        "destination_healthy": True,
        "destination_health_verified": True,
        "destination_health_age_seconds": 5,
        "maximum_health_age_seconds": 60,
        "proposer_id": "operator-1",
        "approver_id": "manager-1",
        "approver_role": "operations_manager",
        "approver_authorized": True,
        "approval_granted": True,
    }
    values.update(overrides)
    return IncidentPolicyInput(**values)


def test_authorizes_only_a_fully_gated_connectivity_retry() -> None:
    result = evaluate_incident_policy(valid_input())

    assert result.decision == PolicyDecision.AUTHORIZED
    assert result.code == PolicyDecisionCode.EXECUTION_AUTHORIZED
    assert result.execution_authorized is True
    assert result.requires_human_approval is False


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"automation_enabled": False}, PolicyDecisionCode.KILL_SWITCH_ACTIVE),
        ({"confidence": 0.79}, PolicyDecisionCode.LOW_CONFIDENCE),
        (
            {"category": IncidentCategory.IDENTITY_MISMATCH},
            PolicyDecisionCode.CATEGORY_PROHIBITED,
        ),
        (
            {"category": IncidentCategory.UNKNOWN},
            PolicyDecisionCode.CATEGORY_PROHIBITED,
        ),
        ({"retry_candidate": False}, PolicyDecisionCode.NOT_RETRY_CANDIDATE),
        ({"requested_action": "DELETE_AND_RETRY"}, PolicyDecisionCode.ACTION_NOT_ALLOWLISTED),
        ({"attempt_count": 1}, PolicyDecisionCode.ATTEMPT_LIMIT_REACHED),
        ({"destination_healthy": False}, PolicyDecisionCode.DESTINATION_UNHEALTHY),
        (
            {"destination_node_id": "destination-node-2"},
            PolicyDecisionCode.DESTINATION_HEALTH_UNVERIFIED,
        ),
        (
            {"destination_health_verified": False},
            PolicyDecisionCode.DESTINATION_HEALTH_UNVERIFIED,
        ),
        (
            {"destination_health_age_seconds": 61},
            PolicyDecisionCode.DESTINATION_HEALTH_STALE,
        ),
        ({"approver_id": None, "approver_role": None}, PolicyDecisionCode.APPROVAL_REQUIRED),
        ({"approver_authorized": False}, PolicyDecisionCode.APPROVER_NOT_AUTHORIZED),
        ({"approval_granted": False}, PolicyDecisionCode.APPROVAL_REQUIRED),
        (
            {"proposer_id": "same-user", "approver_id": "same-user"},
            PolicyDecisionCode.SEPARATION_OF_DUTIES_VIOLATION,
        ),
    ],
)
def test_each_gate_denies_execution_with_a_specific_reason(
    overrides: dict[str, object], code: PolicyDecisionCode
) -> None:
    result = evaluate_incident_policy(valid_input(**overrides))

    assert result.decision == PolicyDecision.DENIED
    assert result.code == code
    assert result.execution_authorized is False


def test_kill_switch_wins_over_all_other_inputs() -> None:
    result = evaluate_incident_policy(
        valid_input(
            automation_enabled=False,
            confidence=0.1,
            category=IncidentCategory.IDENTITY_MISMATCH,
            retry_candidate=False,
            requested_action="DELETE_AND_RETRY",
            attempt_count=100,
            destination_healthy=False,
            destination_node_id="destination-node-2",
            destination_health_verified=False,
            proposer_id="same-user",
            approver_id="same-user",
        )
    )

    assert result.code == PolicyDecisionCode.KILL_SWITCH_ACTIVE
    assert result.execution_authorized is False


def test_confidence_threshold_is_inclusive() -> None:
    result = evaluate_incident_policy(valid_input(confidence=0.8, confidence_threshold=0.8))

    assert result.decision == PolicyDecision.AUTHORIZED


def test_retry_candidate_cannot_be_authorized_for_a_non_retryable_category() -> None:
    result = evaluate_incident_policy(valid_input(category=IncidentCategory.COUNT_MISMATCH))

    assert result.code == PolicyDecisionCode.CATEGORY_PROHIBITED
    assert result.execution_authorized is False


def test_classifier_result_still_requires_a_real_approval_record() -> None:
    classification = classify_incident(
        IncidentClassificationInput(
            domain="pacs",
            source_entity_type="transfer_job",
            source_entity_id="transfer-1",
            error_code="DESTINATION_UNAVAILABLE",
        )
    )
    result = evaluate_incident_policy(
        valid_input(
            category=classification.category,
            confidence=classification.confidence,
            retry_candidate=classification.retry_candidate,
            approver_id=None,
            approver_role=None,
            approver_authorized=False,
            approval_granted=False,
        )
    )

    assert classification.execution_authorized is False
    assert result.code == PolicyDecisionCode.APPROVAL_REQUIRED
    assert result.execution_authorized is False


def test_input_is_strict_and_bounds_attempts_and_confidence() -> None:
    with pytest.raises(ValidationError):
        valid_input(unexpected="reject me")
    with pytest.raises(ValidationError):
        valid_input(confidence=1.1)
    with pytest.raises(ValidationError):
        valid_input(confidence_threshold=-0.1)
    with pytest.raises(ValidationError):
        valid_input(attempt_count=-1)
    with pytest.raises(ValidationError):
        valid_input(attempt_count=101)
    with pytest.raises(ValidationError):
        valid_input(attempt_limit=2)
    with pytest.raises(ValidationError):
        valid_input(proposer_id=" ")
    with pytest.raises(ValidationError):
        valid_input(retry_candidate="true")
