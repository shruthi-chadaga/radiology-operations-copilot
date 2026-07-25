"""scheduling automation foundation

Revision ID: 0002_scheduling
Revises: 0001_foundation
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_scheduling"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synthetic_patients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_patient_id", sa.String(64), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("sex_for_administrative_use", sa.String(32), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("preferred_contact_method", sa.String(32), nullable=False),
        sa.Column("preferred_language", sa.String(16), nullable=False),
        sa.Column("accessibility_notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_synthetic_patients_external_patient_id",
        "synthetic_patients",
        ["external_patient_id"],
        unique=True,
    )

    op.create_table(
        "exception_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exception_number", sa.String(64), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_entity_type", sa.String(64), nullable=False),
        sa.Column("source_entity_id", sa.String(64), nullable=False),
        sa.Column("assigned_role", sa.String(32), nullable=False),
        sa.Column("assigned_user_id", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "exception_number",
        "domain",
        "category",
        "severity",
        "status",
        "source_entity_id",
    ):
        op.create_index(
            f"ix_exception_cases_{column}",
            "exception_cases",
            [column],
            unique=column == "exception_number",
        )

    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("address_text", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_locations_code", "locations", ["code"], unique=True)

    op.create_table(
        "imaging_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("modality", sa.String(16), nullable=False),
        sa.Column("body_region", sa.String(80), nullable=False),
        sa.Column("default_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imaging_services_code", "imaging_services", ["code"], unique=True)
    op.create_index("ix_imaging_services_modality", "imaging_services", ["modality"], unique=False)
    op.create_index(
        "ix_imaging_services_location_id", "imaging_services", ["location_id"], unique=False
    )

    op.create_table(
        "schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("imaging_service_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["imaging_service_id"], ["imaging_services.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("schedule_id", "start_time", "status"):
        op.create_index(f"ix_slots_{column}", "slots", [column], unique=False)

    op.create_table(
        "referrals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("referral_number", sa.String(64), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("requested_exam", sa.String(200), nullable=True),
        sa.Column("modality", sa.String(16), nullable=True),
        sa.Column("body_region", sa.String(80), nullable=True),
        sa.Column("laterality", sa.String(32), nullable=True),
        sa.Column("reason_for_exam", sa.Text(), nullable=True),
        sa.Column("requested_priority", sa.String(32), nullable=True),
        sa.Column("referring_provider", sa.String(160), nullable=True),
        sa.Column("preferred_location", sa.String(120), nullable=True),
        sa.Column("earliest_date", sa.Date(), nullable=True),
        sa.Column("latest_date", sa.Date(), nullable=True),
        sa.Column("contrast_indicator", sa.String(32), nullable=True),
        sa.Column("sedation_indicator", sa.String(32), nullable=True),
        sa.Column("authorization_status", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("completeness_status", sa.String(32), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["synthetic_patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referrals_referral_number", "referrals", ["referral_number"], unique=True)
    for column in ("patient_id", "modality", "status"):
        op.create_index(f"ix_referrals_{column}", "referrals", [column], unique=False)

    op.create_table(
        "referral_field_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("referral_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(80), nullable=False),
        sa.Column("extracted_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("accepted_value", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("corrected_by", sa.String(64), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["referral_id"], ["referrals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_referral_field_extractions_referral_id",
        "referral_field_extractions",
        ["referral_id"],
        unique=False,
    )
    op.create_index(
        "ix_referral_field_extractions_field_name",
        "referral_field_extractions",
        ["field_name"],
        unique=False,
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("appointment_number", sa.String(64), nullable=False),
        sa.Column("accession_number", sa.String(64), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("referral_id", sa.Uuid(), nullable=False),
        sa.Column("slot_id", sa.Uuid(), nullable=False),
        sa.Column("imaging_service_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("booked_by_type", sa.String(32), nullable=False),
        sa.Column("booking_reason", sa.Text(), nullable=False),
        sa.Column("preparation_message", sa.Text(), nullable=True),
        sa.Column("confirmation_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["synthetic_patients.id"]),
        sa.ForeignKeyConstraint(["referral_id"], ["referrals.id"]),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"]),
        sa.ForeignKeyConstraint(["imaging_service_id"], ["imaging_services.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_appointments_appointment_number",
        "appointments",
        ["appointment_number"],
        unique=True,
    )
    op.create_index(
        "ix_appointments_accession_number", "appointments", ["accession_number"], unique=True
    )
    for column in ("patient_id", "referral_id", "slot_id", "status"):
        op.create_index(f"ix_appointments_{column}", "appointments", [column], unique=False)

    op.create_table(
        "imaging_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("accession_number", sa.String(64), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("requested_procedure_code", sa.String(40), nullable=False),
        sa.Column("requested_procedure_description", sa.String(200), nullable=False),
        sa.Column("modality", sa.String(16), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["synthetic_patients.id"]),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id"),
    )
    op.create_index(
        "ix_imaging_orders_accession_number", "imaging_orders", ["accession_number"], unique=True
    )

    op.create_table(
        "appointment_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_appointment_history_appointment_id",
        "appointment_history",
        ["appointment_id"],
        unique=False,
    )


def downgrade() -> None:
    for table in (
        "appointment_history",
        "imaging_orders",
        "appointments",
        "referral_field_extractions",
        "referrals",
        "slots",
        "schedules",
        "imaging_services",
        "locations",
        "exception_cases",
        "synthetic_patients",
    ):
        op.drop_table(table)
