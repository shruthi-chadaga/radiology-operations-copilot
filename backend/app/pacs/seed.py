"""Idempotent local PACS node seed; credentials remain environment-only."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.pacs.models import PacsNode


def seed_pacs_nodes(session: Session) -> None:
    settings = get_settings()
    definitions = (
        (
            "Source Orthanc",
            "source",
            settings.orthanc_source_url,
            "SOURCE_PACS",
            "orthanc-source",
            "source",
        ),
        (
            "Destination Orthanc",
            "destination",
            settings.orthanc_destination_url,
            "DEST_PACS",
            "orthanc-destination",
            settings.orthanc_destination_peer_name,
        ),
    )
    for name, node_type, url, ae_title, host, adapter_key in definitions:
        if session.scalar(select(PacsNode.id).where(PacsNode.name == name)) is None:
            session.add(
                PacsNode(
                    name=name,
                    node_type=node_type,
                    base_url=url,
                    dicom_ae_title=ae_title,
                    dicom_host=host,
                    dicom_port=4242,
                    adapter_key=adapter_key,
                    active=True,
                )
            )
    session.flush()
