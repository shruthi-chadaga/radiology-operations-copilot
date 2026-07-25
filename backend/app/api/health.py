"""Process and dependency health routes."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: str
    synthetic_only: bool


@router.get("/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse(
        status="ok",
        service="Radiology Operations Copilot API",
        synthetic_only=True,
    )
