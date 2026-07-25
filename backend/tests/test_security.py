from app.auth.models import Role
from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_is_argon2_hashed_and_verifiable() -> None:
    encoded = hash_password("local-demo-password")

    assert encoded.startswith("$argon2")
    assert "local-demo-password" not in encoded
    assert verify_password("local-demo-password", encoded)
    assert not verify_password("wrong", encoded)


def test_access_token_round_trip_contains_role_and_subject() -> None:
    token = create_access_token("user-123", Role.SCHEDULER)
    claims = decode_access_token(token)

    assert claims.sub == "user-123"
    assert claims.role == Role.SCHEDULER
    assert claims.token_type == "access"
