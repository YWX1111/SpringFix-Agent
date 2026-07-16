"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from springfix_agent import __version__
from springfix_agent.api.routes import api_error_to_json_response, router
from springfix_agent.config import get_settings
from springfix_agent.service.task_service import TaskService
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def create_app() -> FastAPI:
    """Build the FastAPI application instance with M1 task routes wired up."""
    settings = get_settings()
    app = FastAPI(
        title="SpringFix Agent",
        description=(
            "Intelligent diagnosis and repair platform for Java/Spring Boot projects. "
            "M1 stage: deterministic vertical slice (no LLM)."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings

    repository = InMemoryTaskRepository()
    app.state.task_service = TaskService(
        repository=repository,
        allow_root=settings.resolved_allow_root(),
    )

    from springfix_agent.api.routes import ApiError

    @app.exception_handler(ApiError)
    async def _api_exc_handler(_request, exc: ApiError) -> JSONResponse:  # type: ignore[no-untyped-def]
        return api_error_to_json_response(exc)

    @app.exception_handler(HTTPException)
    async def _http_exc_handler(_request, exc: HTTPException) -> JSONResponse:  # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "error", "message": str(exc.detail)},
        )

    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
