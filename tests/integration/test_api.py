"""HTTP API integration tests (cases 39-44)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from springfix_agent.service.task_service import TaskService

_NO_SCHEDULER = lambda tid: None  # noqa: E731


def _service(client: TestClient) -> TaskService:
    return client.app.state.task_service  # type: ignore[union-attr]


def test_post_creates_task(client: TestClient, sample_repo_path: str) -> None:
    """Case 39: POST /api/v1/tasks creates a task and returns 201."""
    body = {
        "repository_path": sample_repo_path,
        "issue_description": "calling createOrder throws but data not rolled back",
        "error_log": None,
    }
    # Disable background scheduling for determinism by patching the service
    svc = _service(client)
    original_submit = svc.submit_task

    def patched_submit(**kwargs):  # type: ignore[no-untyped-def]
        kwargs["scheduler"] = _NO_SCHEDULER
        return original_submit(**kwargs)

    svc.submit_task = patched_submit  # type: ignore[assignment]
    r = client.post("/api/v1/tasks", json=body)
    assert r.status_code == 201
    data = r.json()
    assert "task_id" in data
    assert data["status"] == "pending"


def test_get_task_returns_status(client: TestClient, sample_repo_path: str) -> None:
    """Case 40: GET /api/v1/tasks/{id} returns task status."""
    svc = _service(client)
    task = svc.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_NO_SCHEDULER,
    )
    r = client.get(f"/api/v1/tasks/{task.task_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == task.task_id
    assert data["status"] == "pending"


def test_get_traces_after_run(client: TestClient, sample_repo_path: str) -> None:
    """Case 41: GET /api/v1/tasks/{id}/traces returns recorded traces."""
    svc = _service(client)
    task = svc.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_NO_SCHEDULER,
    )
    svc.run_task_sync(task.task_id)
    r = client.get(f"/api/v1/tasks/{task.task_id}/traces")
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == task.task_id
    assert len(data["traces"]) > 0
    kinds = {t["kind"] for t in data["traces"]}
    assert "node_timing" in kinds
    assert "tool_call" in kinds


def test_get_report_after_run(client: TestClient, sample_repo_path: str) -> None:
    """Case 42: GET /api/v1/tasks/{id}/report returns the basic report."""
    svc = _service(client)
    task = svc.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_NO_SCHEDULER,
    )
    svc.run_task_sync(task.task_id)
    r = client.get(f"/api/v1/tasks/{task.task_id}/report")
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == task.task_id
    assert "json_report" in data
    assert "markdown_report" in data
    assert len(data["markdown_report"]) > 0


def test_unknown_task_id_returns_404(client: TestClient) -> None:
    """Case 43: unknown task_id returns 404 with structured error."""
    r = client.get("/api/v1/tasks/nonexistent-uuid")
    assert r.status_code == 404
    data = r.json()
    assert data["error"] == "not_found"
    assert "message" in data


def test_invalid_request_returns_structured_error(
    client: TestClient, sample_repo_path: str
) -> None:
    """Case 44: invalid request returns 400/422 with structured error."""
    body = {
        "repository_path": sample_repo_path,
        "issue_description": "short",
    }
    r = client.post("/api/v1/tasks", json=body)
    assert r.status_code in (400, 422)
    data = r.json()
    # Pydantic 422 returns detail list; our 400 returns ErrorResponse
    if r.status_code == 400:
        assert data["error"] in ("validation_error", "error")
        assert "message" in data


def test_request_validation_error_is_structured(
    client: TestClient, sample_repo_path: str
) -> None:
    """422 errors return the structured request_validation_error shape."""
    body = {
        "repository_path": sample_repo_path,
        "issue_description": "short",
    }
    r = client.post("/api/v1/tasks", json=body)
    # FastAPI may return 422 (pydantic) before our handler runs; either way
    # the response shape must be the structured one defined in M1.1.
    assert r.status_code in (400, 422)
    data = r.json()
    if r.status_code == 422:
        assert data["error"] == "request_validation_error"
        assert data["message"] == "Request validation failed"
        assert "details" in data
        assert isinstance(data["details"], list)
        assert len(data["details"]) > 0
        first = data["details"][0]
        assert "field" in first and "reason" in first
        assert first["field"] == "issue_description"
    else:
        assert data["error"] in ("validation_error", "error")
        assert "message" in data


def test_missing_required_field_is_structured(
    client: TestClient, sample_repo_path: str
) -> None:
    """Omitting issue_description still returns a structured 422."""
    body = {"repository_path": sample_repo_path}
    r = client.post("/api/v1/tasks", json=body)
    assert r.status_code == 422
    data = r.json()
    assert data["error"] == "request_validation_error"
    assert "details" in data
    fields = {d["field"] for d in data["details"]}
    assert "issue_description" in fields


def test_report_not_ready_returns_409(client: TestClient, sample_repo_path: str) -> None:
    """Report endpoint returns 409 when task is still pending (consistent with docs)."""
    svc = _service(client)
    task = svc.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_NO_SCHEDULER,
    )
    r = client.get(f"/api/v1/tasks/{task.task_id}/report")
    assert r.status_code == 409
    data = r.json()
    assert data["error"] == "not_ready"


def test_health_still_works(client: TestClient) -> None:
    """Health endpoint still works after M1 routes are added."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
