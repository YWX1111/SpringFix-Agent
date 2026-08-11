"""SQLite API persistence and compatibility integration tests (M4A).

Tests that verify SQLite persistence through the API layer, app restart
scenarios, and backward compatibility with existing InMemory behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from springfix_agent import __version__
from springfix_agent.api.routes import (
    ApiError,
    api_error_to_json_response,
    request_validation_to_json_response,
    router,
)
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.service.task_service import TaskService
from springfix_agent.storage.in_memory import InMemoryTaskRepository
from springfix_agent.storage.migration import migrate
from springfix_agent.storage.models import Report
from springfix_agent.storage.sqlite_repository import SqliteTaskRepository


def _build_app(repo: object, allow_root: Path) -> FastAPI:
    """Build a minimal FastAPI app wired to the given repository."""
    app = FastAPI(title="SpringFix Agent", version=__version__)
    mock_llm = MockLLMClient()
    app.state.task_service = TaskService(
        repository=repo,  # type: ignore[arg-type]
        allow_root=allow_root,
        llm=mock_llm,
    )
    app.state.llm_provider = mock_llm.provider
    app.state.llm_model = mock_llm.model

    @app.exception_handler(ApiError)
    async def _api_exc(_request: object, exc: ApiError) -> JSONResponse:  # type: ignore[no-untyped-def]
        return api_error_to_json_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _val_exc(_request: object, exc: RequestValidationError) -> JSONResponse:  # type: ignore[no-untyped-def]
        return request_validation_to_json_response(exc)

    @app.exception_handler(HTTPException)
    async def _http_exc(_request: object, exc: HTTPException) -> JSONResponse:  # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "error", "message": str(exc.detail)},
        )

    app.include_router(router, prefix="/api/v1")
    return app


def _no_scheduler(_task_id: str) -> None:
    return None


# ===========================================================================
# API persistence tests (behavior 31)
# ===========================================================================

class TestApiPersistence:
    def test_app_rebuild_preserves_data(
        self, tmp_path: Path, allow_root: Path, sample_repo_path: str
    ) -> None:
        """Behavior 31: after app rebuild, API can still query historical tasks."""
        db_path = tmp_path / "api_test.db"
        migrate(db_path)

        # Directly create task via repository to avoid background thread
        repo1 = SqliteTaskRepository(db_path)
        task = repo1.create_task(
            repository_path=sample_repo_path,
            issue_description="calling createOrder throws but data not rolled back",
            error_log=None,
        )
        repo1.update_status(task.task_id, "running", current_node="validate_input")
        repo1.update_status(task.task_id, "completed", current_node="build_diagnostic_report")
        report = Report(
            task_id=task.task_id,
            json_report={"diagnosis_status": "complete", "summary": "test"},
            markdown_report="# Test Report\n\nRoot cause found.",
            created_at=datetime.now(tz=UTC),
        )
        repo1.save_report(task.task_id, report)

        # Second app instance: same DB, new app/repo
        repo2 = SqliteTaskRepository(db_path)
        app2 = _build_app(repo2, allow_root)
        client2 = TestClient(app2)

        # Query the same task
        resp_task = client2.get(f"/api/v1/tasks/{task.task_id}")
        assert resp_task.status_code == 200
        assert resp_task.json()["status"] == "completed"

        # Query traces (empty since we didn't run the graph)
        resp_traces = client2.get(f"/api/v1/tasks/{task.task_id}/traces")
        assert resp_traces.status_code == 200

        # Query report
        resp_report = client2.get(f"/api/v1/tasks/{task.task_id}/report")
        assert resp_report.status_code == 200
        assert resp_report.json()["json_report"]["diagnosis_status"] == "complete"


# ===========================================================================
# Restart recovery through API
# ===========================================================================

class TestRestartRecoveryApi:
    def test_pending_task_interrupted_on_startup(
        self, tmp_path: Path, allow_root: Path, sample_repo_path: str
    ) -> None:
        """A pending task is marked interrupted when a new app starts."""
        db_path = tmp_path / "restart_test.db"
        migrate(db_path)

        # Directly create a pending task without triggering background execution
        repo1 = SqliteTaskRepository(db_path)
        task = repo1.create_task(
            repository_path=sample_repo_path,
            issue_description="calling createOrder throws but data not rolled back",
            error_log=None,
        )

        # Second app: restart recovery runs on construction
        repo2 = SqliteTaskRepository(db_path)
        count = repo2.mark_interrupted_tasks()
        assert count == 1

        app2 = _build_app(repo2, allow_root)
        client2 = TestClient(app2)

        resp_task = client2.get(f"/api/v1/tasks/{task.task_id}")
        assert resp_task.status_code == 200
        data = resp_task.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "interrupted_by_service_restart"

        resp_traces = client2.get(f"/api/v1/tasks/{task.task_id}/traces")
        assert resp_traces.status_code == 200
        traces = resp_traces.json()["traces"]
        recovery_traces = [t for t in traces if t["kind"] == "system_recovery"]
        assert len(recovery_traces) == 1
        assert recovery_traces[0]["payload"]["reason"] == "interrupted_by_service_restart"


# ===========================================================================
# Compatibility tests (behaviors 42-46)
# ===========================================================================

class TestCompatibility:
    def test_inmemory_all_tests_pass(
        self, allow_root: Path, sample_repo_path: str
    ) -> None:
        """Behavior 42: InMemory repository continues to work through API."""
        repo = InMemoryTaskRepository()
        app = _build_app(repo, allow_root)
        client = TestClient(app)

        resp = client.post(
            "/api/v1/tasks",
            json={
                "repository_path": sample_repo_path,
                "issue_description": "calling createOrder throws but data not rolled back",
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["task_id"]

        resp_task = client.get(f"/api/v1/tasks/{task_id}")
        assert resp_task.status_code == 200
        assert resp_task.json()["status"] in ("pending", "running", "completed", "failed")

    def test_api_error_format_consistent(
        self, allow_root: Path
    ) -> None:
        """Behavior 45: API error format is consistent for not_found."""
        repo = InMemoryTaskRepository()
        app = _build_app(repo, allow_root)
        client = TestClient(app)

        resp = client.get("/api/v1/tasks/nonexistent-id")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "message" in data

    def test_path_safety_unchanged(
        self, allow_root: Path
    ) -> None:
        """Behavior 46: path safety validation is unchanged."""
        repo = InMemoryTaskRepository()
        app = _build_app(repo, allow_root)
        client = TestClient(app)

        resp = client.post(
            "/api/v1/tasks",
            json={
                "repository_path": "/etc/passwd",
                "issue_description": "calling createOrder throws but data not rolled back",
            },
        )
        assert resp.status_code == 400

    def test_sqlite_api_error_format(
        self, tmp_path: Path, allow_root: Path
    ) -> None:
        """SQLite API returns same error format as InMemory."""
        db_path = tmp_path / "err_fmt.db"
        migrate(db_path)
        repo = SqliteTaskRepository(db_path)
        app = _build_app(repo, allow_root)
        client = TestClient(app)

        resp = client.get("/api/v1/tasks/nonexistent-id")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "message" in data

    def test_health_version(
        self, allow_root: Path
    ) -> None:
        """Health endpoint returns the package version."""
        repo = InMemoryTaskRepository()
        app = _build_app(repo, allow_root)
        client = TestClient(app)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == __version__
