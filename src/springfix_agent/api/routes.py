"""HTTP routes for SpringFix Agent.

M0 exposes only GET /api/v1/health.
M1 adds: POST /tasks, GET /tasks/{id}, GET /tasks/{id}/traces, GET /tasks/{id}/report.

The route layer is a thin HTTP adapter. All business logic lives in
TaskService; the API layer never touches LangGraph or Tool instances
directly. Errors are raised as ``ApiError`` and converted to a uniform
``ErrorResponse`` JSON shape by the handler in ``main.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from springfix_agent import __version__
from springfix_agent.api.schemas import (
    HealthResponse,
    ReportResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
    TraceItem,
    TraceListResponse,
)
from springfix_agent.service.task_service import TaskService, TaskValidationError

router = APIRouter(tags=["tasks"])


class ApiError(Exception):
    """Domain error carrying an HTTP status code and structured detail."""

    def __init__(self, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message


def _service(request: Request) -> TaskService:
    service = getattr(request.app.state, "task_service", None)
    if not isinstance(service, TaskService):
        raise ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "service_unavailable",
            "TaskService not initialized",
        )
    return service


def _not_found(task_id: str) -> ApiError:
    return ApiError(404, "not_found", f"task not found: {task_id}")


def _validation_error(message: str) -> ApiError:
    return ApiError(400, "validation_error", message)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return service liveness and version."""
    return HealthResponse(status="ok", version=__version__)


@router.post(
    "/tasks",
    response_model=TaskCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(req: TaskCreateRequest, request: Request) -> TaskCreateResponse:
    """Submit a new diagnostic task. Schedules background execution."""
    service = _service(request)
    try:
        task = service.submit_task(
            repository_path=req.repository_path,
            issue_description=req.issue_description,
            error_log=req.error_log,
        )
    except TaskValidationError as e:
        raise _validation_error(str(e)) from e
    return TaskCreateResponse(
        task_id=task.task_id,
        status=task.status,
        created_at=task.submitted_at,
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str, request: Request) -> TaskStatusResponse:
    """Return task status, current node, and timestamps."""
    service = _service(request)
    task = service.get_task(task_id)
    if task is None:
        raise _not_found(task_id)
    error_message: str | None = None
    if task.status == "failed":
        traces = service.get_traces(task_id)
        errs = [
            str(t.payload.get("error"))
            for t in traces
            if t.payload.get("error") and t.kind == "tool_call"
        ]
        if errs:
            error_message = "; ".join(errs[:3])
    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        current_node=task.current_node,
        created_at=task.submitted_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        error_message=error_message,
    )


@router.get("/tasks/{task_id}/traces", response_model=TraceListResponse)
def get_traces(task_id: str, request: Request) -> TraceListResponse:
    """Return all trace records for a task, ordered by recorded_at."""
    service = _service(request)
    if service.get_task(task_id) is None:
        raise _not_found(task_id)
    traces = service.get_traces(task_id)
    return TraceListResponse(
        task_id=task_id,
        traces=[
            TraceItem(kind=t.kind, recorded_at=t.recorded_at, payload=t.payload)
            for t in traces
        ],
    )


@router.get("/tasks/{task_id}/report", response_model=ReportResponse)
def get_report(task_id: str, request: Request) -> ReportResponse:
    """Return the basic diagnostic report. 409 if not yet generated."""
    service = _service(request)
    if service.get_task(task_id) is None:
        raise _not_found(task_id)
    report = service.get_report(task_id)
    if report is None:
        raise ApiError(
            409,
            "not_ready",
            "report not yet generated; task may still be running",
        )
    return ReportResponse(
        task_id=report.task_id,
        json_report=report.json_report,
        markdown_report=report.markdown_report,
        created_at=report.created_at,
    )


def api_error_to_json_response(exc: ApiError) -> JSONResponse:
    """Convert an ApiError into the uniform ErrorResponse JSON shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "message": exc.message},
    )
