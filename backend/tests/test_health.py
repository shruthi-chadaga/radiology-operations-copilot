from fastapi.testclient import TestClient

from app.main import app


def test_liveness_is_public_and_labels_synthetic_prototype() -> None:
    response = TestClient(app).get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Radiology Operations Copilot API",
        "synthetic_only": True,
    }


def test_security_headers_are_present() -> None:
    response = TestClient(app).get("/api/v1/health/live")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
