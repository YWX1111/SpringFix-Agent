"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from springfix_agent import __version__
from springfix_agent.api.routes import (
    ApiError,
    api_error_to_json_response,
    request_validation_to_json_response,
    router,
)
from springfix_agent.config import Settings, get_settings
from springfix_agent.llm.client import LLMClient
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.service.task_service import TaskService
from springfix_agent.storage.in_memory import InMemoryTaskRepository
from springfix_agent.storage.repository import TaskRepository

_LOGGER = logging.getLogger(__name__)


def _build_llm_client(settings: Settings) -> LLMClient:
    """Construct an LLM client based on settings.

    - ``mock`` provider → ``MockLLMClient`` (no network, safe for CI)
    - ``openai_compatible`` provider → ``OpenAICompatibleLLMClient``
      (requires LLM_BASE_URL / LLM_API_KEY / LLM_MODEL; raises on
      missing config).
    """
    if settings.llm_provider == "mock" or not settings.llm_provider:
        return MockLLMClient()
    if settings.llm_provider == "openai_compatible":
        from springfix_agent.llm.openai_compatible import OpenAICompatibleLLMClient

        return OpenAICompatibleLLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=float(settings.llm_timeout_seconds),
            max_retries=settings.llm_max_retries,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    _LOGGER.warning("unknown LLM_PROVIDER %r, falling back to mock", settings.llm_provider)
    return MockLLMClient()


def _build_repository(settings: Settings) -> TaskRepository:
    """Construct the TaskRepository based on TASK_REPOSITORY setting.

    - ``memory`` → InMemoryTaskRepository
    - ``sqlite`` → SqliteTaskRepository (runs migration + restart recovery)
    """
    if settings.task_repository == "memory":
        _LOGGER.info("using InMemoryTaskRepository")
        return InMemoryTaskRepository()
    if settings.task_repository == "sqlite":
        from springfix_agent.storage.migration import migrate
        from springfix_agent.storage.sqlite_repository import SqliteTaskRepository

        db_path = settings.resolved_sqlite_path()
        _LOGGER.info("using SqliteTaskRepository at %s", db_path)
        migrate(
            db_path,
            wal_enabled=settings.sqlite_wal_enabled,
            busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        )
        repo = SqliteTaskRepository(
            db_path,
            wal_enabled=settings.sqlite_wal_enabled,
            busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        )
        interrupted = repo.mark_interrupted_tasks()
        if interrupted:
            _LOGGER.info("marked %d interrupted task(s) as failed on startup", interrupted)
        return repo
    _LOGGER.warning(
        "unknown TASK_REPOSITORY %r, falling back to memory",
        settings.task_repository,
    )
    return InMemoryTaskRepository()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application instance with M4B-compatible routes wired up."""
    resolved = settings if settings is not None else get_settings()
    app = FastAPI(
        title="SpringFix Agent",
        description=(
            "Intelligent diagnosis and repair platform for Java/Spring Boot projects. "
            "M4B stage: SQLite persistence plus offline bug benchmark samples."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = resolved

    repository = _build_repository(resolved)
    llm = _build_llm_client(resolved)
    app.state.task_service = TaskService(
        repository=repository,
        allow_root=resolved.resolved_allow_root(),
        llm=llm,
    )
    app.state.llm_provider = llm.provider
    app.state.llm_model = llm.model

    @app.exception_handler(ApiError)
    async def _api_exc_handler(_request: Any, exc: ApiError) -> JSONResponse:
        return api_error_to_json_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _req_val_exc_handler(_request: Any, exc: RequestValidationError) -> JSONResponse:
        return request_validation_to_json_response(exc)

    @app.exception_handler(HTTPException)
    async def _http_exc_handler(_request: Any, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "error", "message": str(exc.detail)},
        )

    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
