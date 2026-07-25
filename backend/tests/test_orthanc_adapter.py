import httpx

from app.pacs.orthanc import OrthancClient


def test_orthanc_adapter_health_and_normalized_metadata_are_non_destructive() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/system":
            return httpx.Response(200, json={"Name": "Source", "Version": "1.12.9"})
        if request.url.path == "/studies":
            return httpx.Response(
                200,
                json=[
                    {
                        "ID": "orthanc-study-1",
                        "MainDicomTags": {
                            "StudyInstanceUID": "1.2.3.4",
                            "AccessionNumber": "ACC-SYN-1",
                            "StudyDate": "20260719",
                            "StudyDescription": "Synthetic transfer test",
                        },
                        "PatientMainDicomTags": {"PatientID": "SYN-0001"},
                        "Series": ["series-1"],
                    }
                ],
            )
        if request.url.path == "/studies/orthanc-study-1/statistics":
            return httpx.Response(200, json={"CountInstances": 2})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = OrthancClient(
        base_url="http://orthanc-source:8042",
        username="local",
        password="local",
        transport=httpx.MockTransport(handler),
    )
    health = client.health()
    studies = client.list_studies()

    assert health.healthy is True
    assert health.node_name == "Source"
    assert studies[0].orthanc_study_id == "orthanc-study-1"
    assert studies[0].patient_id == "SYN-0001"
    assert studies[0].instance_count == 2
    assert requests == [
        ("GET", "/system"),
        ("GET", "/studies"),
        ("GET", "/studies/orthanc-study-1/statistics"),
    ]
    assert not hasattr(client, "delete_study")
    assert not hasattr(client, "modify_patient_identity")


def test_orthanc_send_uses_allowlisted_store_endpoint_only() -> None:
    captured: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.method, request.url.path, request.content.decode()))
        return httpx.Response(200, json={"Path": "/modalities/destination/store"})

    client = OrthancClient(
        base_url="http://orthanc-source:8042",
        username="local",
        password="local",
        transport=httpx.MockTransport(handler),
    )
    result = client.send_study("orthanc-study-1", "destination")

    assert result.accepted is True
    assert captured == [("POST", "/modalities/destination/store", "orthanc-study-1")]
