"""Pure deterministic incident taxonomy and severity classification.

This module intentionally has no database, AI, adapter, or task dependencies. It produces
bounded evidence for a later incident persistence and policy workflow; it never executes an
action or decides that a remediation is safe by itself.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class IncidentCategory(StrEnum):
    NO_INCIDENT = "no_incident"
    CONNECTIVITY = "connectivity"
    IDENTITY_MISMATCH = "identity_mismatch"
    COUNT_MISMATCH = "count_mismatch"
    UNAUTHORIZED = "unauthorized"
    CONFIGURATION = "configuration"
    DESTRUCTIVE_ACTION = "destructive_action"
    NON_ALLOWLISTED_ACTION = "non_allowlisted_action"
    UNKNOWN = "unknown"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentClassificationInput(BaseModel):
    """Strict, bounded facts used by the deterministic classifier.

    Values are evidence only. They are never treated as executable instructions.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    domain: StrictStr = Field(min_length=1, max_length=32)
    source_entity_type: StrictStr = Field(min_length=1, max_length=64)
    source_entity_id: StrictStr = Field(min_length=1, max_length=80)
    error_code: StrictStr | None = Field(default=None, max_length=80)
    error_message: StrictStr | None = Field(default=None, max_length=500)
    transfer_status: StrictStr | None = Field(default=None, max_length=32)
    http_status: int | None = Field(default=None, ge=100, le=599)
    identifiers_match: bool | None = None
    instance_counts_match: bool | None = None

    @field_validator("domain", "source_entity_type", "source_entity_id")
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value

    @field_validator("error_code", "transfer_status")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class IncidentClassificationResult(BaseModel):
    """Deterministic evidence for policy evaluation, never action authorization."""

    model_config = ConfigDict(extra="forbid", strict=True)

    category: IncidentCategory
    severity: IncidentSeverity
    confidence: float = Field(ge=0, le=1)
    incident_required: bool
    requires_human_review: bool
    retry_candidate: bool
    approval_required: bool
    execution_authorized: Literal[False] = False
    rule_code: StrictStr = Field(min_length=1, max_length=80)


_NO_INCIDENT_STATUSES = frozenset({"COMPLETED"})
_CONNECTIVITY_CODES = frozenset(
    {
        "DESTINATION_UNAVAILABLE",
        "NODE_UNAVAILABLE",
        "TIMEOUT",
        "TIMEOUTERROR",
        "READTIMEOUT",
        "CONNECTION_ERROR",
        "CONNECTIONERROR",
        "CONNECTERROR",
        "CONNECTIVITY_ERROR",
        "HTTPSTATUSERROR",
        "HTTP_502",
        "HTTP_503",
        "HTTP_504",
    }
)
_UNAUTHORIZED_CODES = frozenset({"UNAUTHORIZED", "FORBIDDEN", "HTTP_401", "HTTP_403"})
_CONFIGURATION_CODES = frozenset(
    {"TOPOLOGY_INVALID", "ADAPTER_MISSING", "CONFIGURATION_ERROR", "INVALID_CONFIGURATION"}
)
_DESTRUCTIVE_CODES = frozenset(
    {"DELETE_REQUEST", "DELETE_ATTEMPT", "PIXEL_MODIFICATION", "IDENTITY_TAG_MODIFICATION"}
)
_NON_ALLOWLISTED_CODES = frozenset(
    {"ACTION_NOT_ALLOWLISTED", "NON_ALLOWLISTED_ACTION", "UNSUPPORTED_ACTION"}
)


def classify_incident(payload: IncidentClassificationInput) -> IncidentClassificationResult:
    """Classify evidence with a fail-closed, deterministic precedence order."""

    code = payload.error_code
    if payload.transfer_status in _NO_INCIDENT_STATUSES and not _has_failure_evidence(payload):
        return _result(
            IncidentCategory.NO_INCIDENT,
            IncidentSeverity.LOW,
            incident_required=False,
            requires_human_review=False,
            retry_candidate=False,
            approval_required=False,
            rule_code="NO_INCIDENT_SUCCESS_STATUS",
        )

    # Safety-critical evidence outranks a misleading generic/network error code.
    if payload.identifiers_match is False or code == (
        IncidentCategory.IDENTITY_MISMATCH.value.upper()
    ):
        return _result(
            IncidentCategory.IDENTITY_MISMATCH,
            IncidentSeverity.CRITICAL,
            rule_code="IDENTITY_MISMATCH_REQUIRES_HUMAN",
        )
    if payload.instance_counts_match is False or code == (
        IncidentCategory.COUNT_MISMATCH.value.upper()
    ):
        return _result(
            IncidentCategory.COUNT_MISMATCH,
            IncidentSeverity.HIGH,
            rule_code="COUNT_MISMATCH_REQUIRES_HUMAN",
        )
    if code in _DESTRUCTIVE_CODES:
        return _result(
            IncidentCategory.DESTRUCTIVE_ACTION,
            IncidentSeverity.CRITICAL,
            rule_code="DESTRUCTIVE_ACTION_PROHIBITED",
        )
    if code in _NON_ALLOWLISTED_CODES:
        return _result(
            IncidentCategory.NON_ALLOWLISTED_ACTION,
            IncidentSeverity.CRITICAL,
            rule_code="ACTION_NOT_ALLOWLISTED",
        )
    if payload.http_status in {401, 403} or code in _UNAUTHORIZED_CODES:
        return _result(
            IncidentCategory.UNAUTHORIZED,
            IncidentSeverity.CRITICAL,
            rule_code="UNAUTHORIZED_ACTION_REQUIRES_HUMAN",
        )
    if code in _CONFIGURATION_CODES:
        return _result(
            IncidentCategory.CONFIGURATION,
            IncidentSeverity.HIGH,
            rule_code="CONFIGURATION_REQUIRES_HUMAN",
        )
    if code in _CONNECTIVITY_CODES or payload.http_status in {502, 503, 504}:
        return _result(
            IncidentCategory.CONNECTIVITY,
            IncidentSeverity.MEDIUM,
            retry_candidate=True,
            rule_code="CONNECTIVITY_RETRY_REQUIRES_APPROVAL",
        )
    return _result(
        IncidentCategory.UNKNOWN,
        IncidentSeverity.HIGH,
        rule_code="UNKNOWN_FAILURE_REQUIRES_HUMAN",
    )


def _has_failure_evidence(payload: IncidentClassificationInput) -> bool:
    return any(
        value is not None
        for value in (
            payload.error_code,
            payload.error_message,
            payload.http_status,
            payload.identifiers_match,
            payload.instance_counts_match,
        )
    )


def _result(
    category: IncidentCategory,
    severity: IncidentSeverity,
    *,
    rule_code: str,
    incident_required: bool = True,
    requires_human_review: bool = True,
    retry_candidate: bool = False,
    approval_required: bool = True,
) -> IncidentClassificationResult:
    return IncidentClassificationResult(
        category=category,
        severity=severity,
        confidence=1.0,
        incident_required=incident_required,
        requires_human_review=requires_human_review,
        retry_candidate=retry_candidate,
        approval_required=approval_required,
        rule_code=rule_code,
    )
