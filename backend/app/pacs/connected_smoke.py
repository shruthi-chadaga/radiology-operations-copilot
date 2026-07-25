"""Read-only connected PACS verification for the Phase 3 integration gate."""

import json
from collections.abc import Mapping

from app.pacs.adapter import PacsAdapter
from app.pacs.dependencies import get_pacs_adapters
from app.pacs.inventory import validate_synthetic_metadata


class ConnectedPacsCheckFailed(RuntimeError):
    """Raised when the connected PACS contract is not satisfied."""


def check_connected_pacs(adapters: Mapping[str, PacsAdapter]) -> dict[str, object]:
    """Verify node health and synthetic metadata without issuing mutations."""
    evidence: dict[str, object] = {}
    for adapter_key in ("source", "destination"):
        adapter = adapters[adapter_key]
        health = adapter.health()
        if not health.healthy:
            raise ConnectedPacsCheckFailed(f"{adapter_key} PACS node is unhealthy")

        studies = adapter.list_studies()
        if adapter_key == "source" and not studies:
            raise ConnectedPacsCheckFailed("source PACS inventory is empty; run make seed-pacs")
        for metadata in studies:
            validate_synthetic_metadata(metadata)

        evidence[adapter_key] = {
            "node_name": health.node_name,
            "study_count": len(studies),
        }

    evidence["metadata_only"] = True
    evidence["synthetic_markers_validated"] = True
    return evidence


def main() -> None:
    print(json.dumps(check_connected_pacs(get_pacs_adapters()), sort_keys=True))


if __name__ == "__main__":
    main()
