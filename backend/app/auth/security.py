"""Password hashing and bounded JWT access-token handling."""

from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from pydantic import BaseModel, ConfigDict

from app.auth.models import Role
from app.config import get_settings

_hasher = PasswordHasher()


class AccessClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sub: str
    role: Role
    token_type: str
    exp: int


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(subject: str, role: Role) -> str:
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode(
        {"sub": subject, "role": role.value, "token_type": "access", "exp": expires},
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> AccessClaims:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return AccessClaims.model_validate(payload)
