"""Shared pytest fixtures for M2."""

from __future__ import annotations

from pathlib import Path

import pytest
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
from springfix_agent.llm.client import LLMClient
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.service.task_service import TaskService
from springfix_agent.storage.in_memory import InMemoryTaskRepository


@pytest.fixture
def mock_llm() -> MockLLMClient:
    """A fresh MockLLMClient for each test."""
    return MockLLMClient()


@pytest.fixture
def app() -> object:
    """Fresh FastAPI app per test (not wired with a task_service; see client)."""
    return FastAPI()


@pytest.fixture
def client(allow_root: Path, mock_llm: LLMClient) -> TestClient:
    """TestClient wired to a fresh TaskService + MockLLMClient."""
    app = FastAPI(title="SpringFix Agent", version=__version__)
    repository = InMemoryTaskRepository()
    app.state.task_service = TaskService(
        repository=repository,
        allow_root=allow_root,
        llm=mock_llm,
    )
    app.state.llm_provider = mock_llm.provider
    app.state.llm_model = mock_llm.model

    @app.exception_handler(ApiError)
    async def _api_exc_handler(_request, exc: ApiError) -> JSONResponse:  # type: ignore[no-untyped-def]
        return api_error_to_json_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _req_val_exc_handler(  # type: ignore[no-untyped-def]
        _request, exc: RequestValidationError
    ) -> JSONResponse:
        return request_validation_to_json_response(exc)

    @app.exception_handler(HTTPException)
    async def _http_exc_handler(_request, exc: HTTPException) -> JSONResponse:  # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "error", "message": str(exc.detail)},
        )

    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


@pytest.fixture
def allow_root(tmp_path: Path) -> Path:
    """A clean allow_root directory per test, under pytest tmp_path."""
    root = tmp_path / "allow_root"
    root.mkdir()
    return root.resolve()


@pytest.fixture
def sample_repo(allow_root: Path) -> Path:
    """A small fake Spring Boot repository under allow_root for tool tests."""
    repo = allow_root / "sample-repo"
    src = repo / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)
    (src / "OrderService.java").write_text(
        "package com.example;\n\n"
        "import org.springframework.stereotype.Service;\n"
        "import org.springframework.transaction.annotation.Transactional;\n\n"
        "@Service\n"
        "public class OrderService {\n"
        "    public void createOrder() {\n"
        "        createOrderInTransaction();\n"
        "    }\n\n"
        "    @Transactional\n"
        "    public void createOrderInTransaction() {\n"
        "        throw new RuntimeException(\"simulated failure\");\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "OtherService.java").write_text(
        "package com.example;\n\n"
        "public class OtherService {\n"
        "    public void doSomething() {\n"
        "        System.out.println(\"hello\");\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "Config.java").write_text(
        "package com.example;\n"
        "import org.springframework.context.annotation.Configuration;\n"
        "@Configuration\n"
        "public class Config {\n"
        "}\n",
        encoding="utf-8",
    )
    (repo / "pom.xml").write_text(
        "<project xmlns=\"http://maven.apache.org/POM/4.0.0\"></project>\n",
        encoding="utf-8",
    )
    (repo / "src" / "main" / "resources").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "main" / "resources" / "application.properties").write_text(
        "spring.application.name=test\n", encoding="utf-8"
    )
    target_dir = repo / "target"
    target_dir.mkdir()
    (target_dir / "generated.java").write_text("// generated\n", encoding="utf-8")
    build_dir = repo / "build"
    build_dir.mkdir()
    (build_dir / "out.java").write_text("// build out\n", encoding="utf-8")
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return repo


@pytest.fixture
def task_service(allow_root: Path, mock_llm: LLMClient) -> TaskService:
    """A TaskService with InMemoryTaskRepository + MockLLMClient."""
    repo = InMemoryTaskRepository()
    return TaskService(repository=repo, allow_root=allow_root, llm=mock_llm)


@pytest.fixture
def sample_repo_path(sample_repo: Path) -> str:
    """Path of sample_repo as a string for use in API requests."""
    return sample_repo.as_posix()
