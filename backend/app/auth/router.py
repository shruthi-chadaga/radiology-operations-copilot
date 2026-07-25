"""Local-only, seeded-user authentication routes."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditEvent
from app.audit.service import AuditActor, append_audit_event
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import LoginRequest, LoginResponse, UserResponse
from app.auth.security import create_access_token, verify_password
from app.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["authentication"])
settings = get_settings()


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id), email=user.email, display_name=user.display_name, role=user.role
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    request_id = request.headers.get("x-request-id", "local-login")
    correlation_id = request.headers.get("x-correlation-id", request_id)
    source_ip = request.client.host if request.client else None
    window_start = datetime.now(UTC) - timedelta(seconds=settings.login_rate_limit_window_seconds)
    recent_failures = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == "auth.login",
            AuditEvent.success.is_(False),
            AuditEvent.source_ip == source_ip,
            AuditEvent.timestamp >= window_start,
        )
    )
    if int(recent_failures or 0) >= settings.login_rate_limit_attempts:
        append_audit_event(
            db,
            actor=AuditActor("anonymous", None),
            action="auth.login.rate_limited",
            entity_type="user",
            entity_id="unknown",
            decision_reason="Bounded login attempt policy denied authentication",
            correlation_id=correlation_id,
            request_id=request_id,
            source_ip=source_ip,
            success=False,
            error_code="LOGIN_RATE_LIMITED",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(settings.login_rate_limit_window_seconds)},
        )
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    valid = (
        user is not None
        and user.is_active
        and verify_password(payload.password, user.password_hash)
    )
    append_audit_event(
        db,
        actor=AuditActor(
            actor_type="user" if valid else "anonymous",
            actor_id=str(user.id) if user else None,
        ),
        action="auth.login",
        entity_type="user",
        entity_id=str(user.id) if user else "unknown",
        decision_reason="Seeded local account authentication",
        correlation_id=correlation_id,
        request_id=request_id,
        source_ip=request.client.host if request.client else None,
        success=bool(valid),
        error_code=None if valid else "INVALID_CREDENTIALS",
    )
    db.commit()
    if not valid or user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    response.set_cookie(
        "access_token",
        create_access_token(str(user.id), user.role),
        httponly=True,
        secure=settings.app_env != "local",
        samesite="strict",
        max_age=settings.access_token_minutes * 60,
        path="/",
    )
    return LoginResponse(user=_user_response(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    request_id = request.headers.get("x-request-id", "local-logout")[:160]
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action="auth.logout",
        entity_type="user",
        entity_id=str(user.id),
        decision_reason="Authenticated user ended the local session",
        correlation_id=request.headers.get("x-correlation-id", request_id)[:160],
        request_id=request_id,
        source_ip=request.client.host if request.client else None,
        success=True,
    )
    db.commit()
    response.delete_cookie("access_token", path="/")


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return _user_response(user)
