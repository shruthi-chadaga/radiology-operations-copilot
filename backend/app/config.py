"""Application settings with conservative behavior and required credentials."""

from functools import lru_cache
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "local"
    app_name: str = "Radiology Operations Copilot"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str
    access_token_minutes: int = Field(default=30, ge=1, le=120)
    refresh_token_days: int = Field(default=7, ge=1, le=30)
    login_rate_limit_attempts: int = Field(default=5, ge=1, le=20)
    login_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    ai_mock_mode: bool = True
    enable_auto_retry: bool = False
    max_auto_retries: int = 1
    low_confidence_threshold: float = Field(default=0.80, ge=0, le=1)
    orthanc_source_url: str = "http://orthanc-source:8042"
    orthanc_source_username: str = "source_admin"
    orthanc_source_password: str
    orthanc_destination_url: str = "http://orthanc-destination:8042"
    orthanc_destination_username: str = "destination_admin"
    orthanc_destination_password: str
    orthanc_destination_peer_name: str = "destination"
    scheduler_demo_password: str
    pacs_admin_demo_password: str
    operations_manager_demo_password: str
    auditor_demo_password: str
    system_admin_demo_password: str
    smtp_host: str = "mailhog"
    smtp_port: int = Field(default=1025, ge=1, le=65535)

    @field_validator("max_auto_retries")
    @classmethod
    def enforce_single_automatic_retry(cls, value: int) -> int:
        if value < 0 or value > 1:
            raise ValueError("MAX_AUTO_RETRIES must be 0 or 1")
        return value

    @model_validator(mode="after")
    def reject_demo_credentials_outside_local(self) -> Self:
        if self.app_env.lower() == "local":
            return self
        known_local_values = {
            "local-development-secret-change-before-sharing",
            "replace_with_a_unique_local_source_orthanc_password",
            "replace_with_a_unique_local_destination_orthanc_password",
        }
        if (
            self.jwt_secret in known_local_values
            or self.orthanc_source_password in known_local_values
            or self.orthanc_destination_password in known_local_values
            or "replace_with_a_unique_local_database_password" in self.database_url
        ):
            raise ValueError("local demo credentials are forbidden outside APP_ENV=local")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
