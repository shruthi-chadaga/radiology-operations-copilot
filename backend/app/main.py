"""FastAPI application entry point."""

from typing import cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.health import router as health_router
from app.audit.router import router as audit_router
from app.audit.service import AuditActor, append_audit_event
from app.auth.router import router as auth_router
from app.config import get_settings
from app.pacs.router import router as pacs_router
from app.scheduling.router import router as scheduling_router

settings = get_settings()
app = FastAPI(
    title="Radiology Operations Copilot API",
    description="Synthetic local-only healthcare operations portfolio API. Never enter real PHI.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Request-ID", "X-Correlation-ID", "Idempotency-Key"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    response = cast(Response, await call_next(request))
    if response.status_code == 403 and not getattr(
        request.state, "authorization_denial_audited", False
    ):
        db = getattr(request.state, "auth_db", None)
        if db is not None:
            request_id = request.headers.get("x-request-id", "local-rbac-denial")[:160]
            correlation_id = request.headers.get("x-correlation-id", request_id)[:160]
            append_audit_event(
                db,
                actor=AuditActor("user", getattr(request.state, "auth_user_id", None)),
                action="auth.authorization.denied",
                entity_type="http_route",
                entity_id=request.url.path[:160],
                decision_reason="Backend role policy denied access",
                correlation_id=correlation_id,
                request_id=request_id,
                source_ip=request.client.host if request.client else None,
                success=False,
                error_code="FORBIDDEN",
            )
            db.commit()
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(scheduling_router, prefix="/api/v1")
app.include_router(pacs_router, prefix="/api/v1")
