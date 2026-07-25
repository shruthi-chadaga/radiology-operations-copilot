"""Authentication dependencies; backend role checks remain authoritative."""

from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request, status
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.auth.models import User
from app.auth.security import decode_access_token
from app.config import get_settings
from app.db.session import get_db


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    access_token: Annotated[str | None, Cookie()] = None,
) -> User:
    request.state.auth_db = db
    if not access_token:
        _audit_denial(db, request, "AUTHENTICATION_REQUIRED")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin != get_settings().frontend_url:
            _audit_denial(db, request, "UNTRUSTED_ORIGIN")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Untrusted origin")
    try:
        claims = decode_access_token(access_token)
        user_id = UUID(claims.sub)
    except (InvalidTokenError, ValueError) as exc:
        _audit_denial(db, request, "INVALID_SESSION")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.role != claims.role:
        _audit_denial(db, request, "INVALID_SESSION", actor_id=str(user_id))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    request.state.auth_user_id = str(user.id)
    return user


def _audit_denial(
    db: Session, request: Request, error_code: str, *, actor_id: str | None = None
) -> None:
    request_id = request.headers.get("x-request-id", "local-auth-denial")[:160]
    correlation_id = request.headers.get("x-correlation-id", request_id)[:160]
    append_audit_event(
        db,
        actor=AuditActor("user" if actor_id else "anonymous", actor_id),
        action="auth.access.denied",
        entity_type="http_route",
        entity_id=request.url.path[:160],
        decision_reason="Backend authentication or browser-origin policy denied access",
        correlation_id=correlation_id,
        request_id=request_id,
        source_ip=request.client.host if request.client else None,
        success=False,
        error_code=error_code,
    )
    db.commit()
    request.state.authorization_denial_audited = True
