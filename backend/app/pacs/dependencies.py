"""PACS adapter construction from local environment settings."""

from app.config import get_settings
from app.pacs.adapter import PacsAdapter
from app.pacs.orthanc import OrthancClient


def get_pacs_adapters() -> dict[str, PacsAdapter]:
    settings = get_settings()
    return {
        "source": OrthancClient(
            base_url=settings.orthanc_source_url,
            username=settings.orthanc_source_username,
            password=settings.orthanc_source_password,
        ),
        "destination": OrthancClient(
            base_url=settings.orthanc_destination_url,
            username=settings.orthanc_destination_username,
            password=settings.orthanc_destination_password,
        ),
    }
