"""Tests for the health check endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from springfix_agent import __version__


def test_health_returns_ok(client: TestClient) -> None:
    """GET /api/v1/health must return status=ok and the package version."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "version": __version__}


def test_health_response_shape(client: TestClient) -> None:
    """Response must expose exactly the status and version fields."""
    response = client.get("/api/v1/health")
    body = response.json()
    assert set(body.keys()) == {"status", "version"}
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_m5a_version_is_0_9_0() -> None:
    """M5A release metadata is aligned across package and health response."""
    assert __version__ == "0.9.0"


def test_openapi_docs_available(client: TestClient) -> None:
    """The OpenAPI schema must be reachable for /docs."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "SpringFix Agent"
    assert "/api/v1/health" in schema["paths"]
