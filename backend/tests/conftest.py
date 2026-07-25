"""Pytest-only environment values; these are fixtures, not deployable credentials."""

import os

_TEST_ENV = {
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    "JWT_SECRET": "pytest-only-jwt-value-not-for-deployment",
    "ORTHANC_SOURCE_PASSWORD": "pytest-source-only",
    "ORTHANC_DESTINATION_PASSWORD": "pytest-destination-only",
    "SCHEDULER_DEMO_PASSWORD": "pytest-scheduler-only",
    "PACS_ADMIN_DEMO_PASSWORD": "pytest-pacs-admin-only",
    "OPERATIONS_MANAGER_DEMO_PASSWORD": "pytest-manager-only",
    "AUDITOR_DEMO_PASSWORD": "pytest-auditor-only",
    "SYSTEM_ADMIN_DEMO_PASSWORD": "pytest-system-admin-only",
}

for name, value in _TEST_ENV.items():
    os.environ.setdefault(name, value)
