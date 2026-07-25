import pytest

from app.config import Settings


def test_local_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "local"
    assert settings.ai_mock_mode is True
    assert settings.enable_auto_retry is False
    assert settings.max_auto_retries == 1
    assert settings.frontend_url == "http://localhost:3000"
    assert settings.orthanc_source_username != settings.orthanc_destination_username
    assert settings.orthanc_source_password != settings.orthanc_destination_password


def test_unsafe_retry_limit_is_rejected() -> None:
    try:
        Settings(_env_file=None, max_auto_retries=2)
    except ValueError as exc:
        assert "MAX_AUTO_RETRIES" in str(exc)
    else:
        raise AssertionError("unsafe automatic retry limit was accepted")


def test_non_local_environment_rejects_known_demo_credentials() -> None:
    with pytest.raises(ValueError, match="local demo credentials"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret="local-development-secret-change-before-sharing",
        )
