"""Pydantic request/response schemas for the API layer."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from springfix_agent.storage.models import TaskStatus


class HealthResponse(BaseModel):
    """Response model for GET /api/v1/health."""

    status: str = Field(description="Service health status.", examples=["ok"])
    version: str = Field(description="Application version from pyproject.toml.", examples=["0.1.0"])


class ErrorResponse(BaseModel):
    """Standard error response model for all non-2xx responses."""

    error: str = Field(description="Stable machine-readable error code.", examples=["not_found"])
    message: str = Field(description="Human-readable error message.", examples=["Task not found"])


class TaskCreateRequest(BaseModel):
    """Request body for POST /api/v1/tasks."""

    repository_path: str = Field(
        description="Repository path. Relative paths are resolved against ALLOW_ROOT; "
        "absolute paths must resolve inside ALLOW_ROOT.",
    )
    issue_description: str = Field(
        min_length=10,
        max_length=2000,
        description="Natural-language problem description (10-2000 chars).",
    )
    error_log: str | None = Field(
        default=None,
        max_length=10000,
        description="Optional error log text (max 10000 chars).",
    )


class TaskCreateResponse(BaseModel):
    """Response for POST /api/v1/tasks."""

    task_id: str
    status: TaskStatus
    created_at: datetime


class TaskStatusResponse(BaseModel):
    """Response for GET /api/v1/tasks/{task_id}."""

    task_id: str
    status: TaskStatus
    current_node: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class TraceItem(BaseModel):
    """A single trace entry (tool_call or node_timing)."""

    kind: str
    recorded_at: datetime
    payload: dict[str, object]


class TraceListResponse(BaseModel):
    """Response for GET /api/v1/tasks/{task_id}/traces."""

    task_id: str
    traces: list[TraceItem]


class ReportResponse(BaseModel):
    """Response for GET /api/v1/tasks/{task_id}/report."""

    task_id: str
    json_report: dict[str, object]
    markdown_report: str
    created_at: datetime
