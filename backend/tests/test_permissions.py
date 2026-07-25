from app.auth.models import Role
from app.auth.permissions import require_any_role


def test_scheduler_cannot_approve_pacs_remediation() -> None:
    allowed = require_any_role(Role.PACS_ADMIN, Role.OPERATIONS_MANAGER)

    assert allowed(Role.SCHEDULER) is False
    assert allowed(Role.PACS_ADMIN) is True
    assert allowed(Role.OPERATIONS_MANAGER) is True


def test_auditor_has_no_mutating_role_grant() -> None:
    allowed = require_any_role(Role.SCHEDULER, Role.PACS_ADMIN, Role.OPERATIONS_MANAGER)

    assert allowed(Role.AUDITOR) is False
