"""Bounded Orthanc REST client exposing only non-destructive operations."""

from time import perf_counter
from typing import Any

import httpx

from app.pacs.schemas import PacsHealth, PacsStudyMetadata, StoreResult


class OrthancAdapterError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class OrthancClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            auth=(username, password),
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    def health(self) -> PacsHealth:
        started = perf_counter()
        try:
            response = self._client.get("/system")
            response.raise_for_status()
            payload = response.json()
            return PacsHealth(
                healthy=True,
                node_name=self._string(payload.get("Name")),
                version=self._string(payload.get("Version")),
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return PacsHealth(
                healthy=False,
                node_name=None,
                version=None,
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
                error=self._redacted_error(exc),
            )

    def list_studies(self) -> list[PacsStudyMetadata]:
        response = self._client.get("/studies", params={"expand": "true"})
        self._raise(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise OrthancAdapterError("Orthanc study response was not a list")
        return [self._with_instance_count(self._normalize_study(item)) for item in payload]

    def find_study(self, study_instance_uid: str) -> list[PacsStudyMetadata]:
        response = self._client.post(
            "/tools/find",
            json={
                "Level": "Study",
                "Expand": True,
                "Query": {"StudyInstanceUID": study_instance_uid},
            },
        )
        self._raise(response)
        payload = response.json()
        if not isinstance(payload, list):
            raise OrthancAdapterError("Orthanc find response was not a list")
        return [self._with_instance_count(self._normalize_study(item)) for item in payload]

    def upload_instance(self, dicom_bytes: bytes) -> str:
        response = self._client.post(
            "/instances", content=dicom_bytes, headers={"Content-Type": "application/dicom"}
        )
        self._raise(response)
        payload = response.json()
        instance_id = payload.get("ID") if isinstance(payload, dict) else None
        if not isinstance(instance_id, str):
            raise OrthancAdapterError("Orthanc upload response lacked an instance ID")
        return instance_id

    def send_study(self, orthanc_study_id: str, destination_name: str) -> StoreResult:
        response = self._client.post(
            f"/modalities/{destination_name}/store",
            content=orthanc_study_id,
            headers={"Content-Type": "text/plain"},
        )
        self._raise(response)
        payload = response.json()
        path = payload.get("Path") if isinstance(payload, dict) else None
        return StoreResult(accepted=True, response_path=path if isinstance(path, str) else None)

    def render_instance_preview(self, orthanc_instance_id: str) -> tuple[bytes, str]:
        """Retrieve one server-rendered preview, never the original DICOM object."""
        response = self._client.get(f"/instances/{orthanc_instance_id}/preview")
        self._raise(response)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in {"image/png", "image/jpeg"}:
            raise OrthancAdapterError("Orthanc preview response was not a supported image")
        if not response.content:
            raise OrthancAdapterError("Orthanc preview response was empty")
        return response.content, content_type

    def list_series(self, orthanc_study_id: str) -> list[dict[str, object]]:
        response = self._client.get(f"/studies/{orthanc_study_id}/series")
        self._raise(response)
        series_ids = response.json()
        if not isinstance(series_ids, list):
            raise OrthancAdapterError("Orthanc series response was not a list")
        result: list[dict[str, object]] = []
        for sid in series_ids:
            if not isinstance(sid, str):
                continue
            series_resp = self._client.get(f"/series/{sid}")
            self._raise(series_resp)
            series_data = series_resp.json()
            if not isinstance(series_data, dict):
                continue
            main_tags = series_data.get("MainDicomTags")
            tags_dict: dict[str, str] = {}
            if isinstance(main_tags, dict):
                for key, value in main_tags.items():
                    tags_dict[str(key)] = value if isinstance(value, str) else str(value)
            instances_raw = series_data.get("Instances")
            instance_ids = (
                [str(item) for item in instances_raw if isinstance(item, str)]
                if isinstance(instances_raw, list)
                else []
            )
            instance_refs: list[dict[str, str]] = [
                {"orthanc_instance_id": iid, "sop_instance_uid": "", "instance_number": ""}
                for iid in instance_ids
            ]
            main_tag_values = series_data.get("MainDicomTags")
            main_tag_values = main_tag_values if isinstance(main_tag_values, dict) else {}
            result.append(
                {
                    "orthanc_series_id": sid,
                    "series_instance_uid": str(main_tag_values.get("SeriesInstanceUID", "")),
                    "series_number": self._string(tags_dict.get("SeriesNumber")),
                    "series_description": self._string(tags_dict.get("SeriesDescription")),
                    "modality": self._string(tags_dict.get("Modality")),
                    "instance_count": len(instance_ids),
                    "instances": instance_refs,
                    "tags": tags_dict,
                }
            )
        return result

    def _with_instance_count(self, study: PacsStudyMetadata) -> PacsStudyMetadata:
        response = self._client.get(f"/studies/{study.orthanc_study_id}/statistics")
        self._raise(response)
        payload = response.json()
        raw_count = payload.get("CountInstances") if isinstance(payload, dict) else None
        if isinstance(raw_count, int) and not isinstance(raw_count, bool):
            instance_count = raw_count
        elif isinstance(raw_count, str):
            try:
                instance_count = int(raw_count)
            except ValueError as exc:
                raise OrthancAdapterError("Orthanc statistics lacked CountInstances") from exc
        else:
            raise OrthancAdapterError("Orthanc statistics lacked CountInstances")
        if instance_count < 0:
            raise OrthancAdapterError("Orthanc statistics had an invalid CountInstances")
        return study.model_copy(update={"instance_count": instance_count})

    def get_study_tags(self, orthanc_study_id: str) -> dict[str, dict[str, str]]:
        response = self._client.get(f"/studies/{orthanc_study_id}")
        self._raise(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise OrthancAdapterError("Orthanc study response was not an object")
        main = payload.get("MainDicomTags")
        patient = payload.get("PatientMainDicomTags")
        if not isinstance(main, dict) or not isinstance(patient, dict):
            raise OrthancAdapterError("Orthanc study metadata was incomplete")
        return {
            "MainDicomTags": {
                str(key): value if isinstance(value, str) else str(value)
                for key, value in main.items()
            },
            "PatientMainDicomTags": {
                str(key): value if isinstance(value, str) else str(value)
                for key, value in patient.items()
            },
        }

    @classmethod
    def _normalize_study(cls, raw: Any) -> PacsStudyMetadata:
        if not isinstance(raw, dict):
            raise OrthancAdapterError("Orthanc study entry was not an object")
        main = raw.get("MainDicomTags")
        patient = raw.get("PatientMainDicomTags")
        if not isinstance(main, dict) or not isinstance(patient, dict):
            raise OrthancAdapterError("Orthanc study metadata was incomplete")
        return PacsStudyMetadata(
            orthanc_study_id=cls._required_string(raw.get("ID"), "ID"),
            study_instance_uid=cls._required_string(
                main.get("StudyInstanceUID"), "StudyInstanceUID"
            ),
            accession_number=cls._required_string(main.get("AccessionNumber"), "AccessionNumber"),
            patient_id=cls._required_string(patient.get("PatientID"), "PatientID"),
            patient_name=cls._string(patient.get("PatientName")),
            patient_birth_date=cls._string(patient.get("PatientBirthDate")),
            patient_sex=cls._string(patient.get("PatientSex")),
            study_date=cls._string(main.get("StudyDate")),
            study_description=cls._string(main.get("StudyDescription")),
            modality=cls._string(main.get("Modality")),
            series_count=cls._list_length(raw.get("Series")),
            instance_count=cls._list_length(raw.get("Instances")),
        )

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OrthancAdapterError(
                f"Orthanc request failed with HTTP {response.status_code}",
                http_status=response.status_code,
            ) from exc

    @staticmethod
    def _required_string(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise OrthancAdapterError(f"Orthanc metadata lacked {field}")
        return value

    @staticmethod
    def _string(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _list_length(value: Any) -> int:
        return len(value) if isinstance(value, list) else 0

    @staticmethod
    def _redacted_error(exc: Exception) -> str:
        return f"{type(exc).__name__}: Orthanc request failed"
