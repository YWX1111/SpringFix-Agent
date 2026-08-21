"""Strict schemas for the Fresh Holdout v2 Agent-facing projection.

This module deliberately contains no Gold or reference-patch types.  The
legacy ``BenchmarkCase`` model remains the owner of the legacy benchmark
interface; Fresh Holdout v2 uses this separate projection model instead.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FRESH_HOLDOUT_V2_SCHEMA_VERSION = "fresh-holdout-v2-agent-manifest-v1"
FRESH_HOLDOUT_V2_BENCHMARK_VERSION = "fresh_holdout_v2"
FRESH_HOLDOUT_V2_STATUS = "REGISTERED_BEFORE_AGENT_EXECUTION"
FRESH_HOLDOUT_V2_PROJECTION_FIELDS = (
    "case_id",
    "repository",
    "issue_description",
    "error_log",
    "error_log_version",
)


def _validate_relative_path(value: str, *, field_name: str) -> str:
    """Reject absolute paths and parent traversal in projection paths."""
    value = value.strip()
    is_absolute = (
        Path(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or value.startswith(("/", "\\"))
        or (len(value) >= 3 and value[1] == ":" and value[2] in "/\\")
    )
    if is_absolute or ".." in value.replace("\\", "/").split("/"):
        raise ValueError(f"{field_name} must be a relative path")
    if not value:
        raise ValueError(f"{field_name} must not be blank")
    return value


class FreshHoldoutV2ExecutionContract(BaseModel):
    """The frozen pre-execution counters and target for Fresh v2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_executions: int = Field(ge=0)
    mock_executions: int = Field(ge=0)
    live_executions: int = Field(ge=0)
    llm_benchmark_calls: int = Field(ge=0)
    maven_target: Literal["mvn test"]
    fresh_holdout_execution: bool


class FreshHoldoutV2Case(BaseModel):
    """One blinded Fresh Holdout v2 case exposed to the Agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    issue_description: str = Field(min_length=1)
    error_log: str = Field(min_length=1)
    error_log_version: str = Field(min_length=1)

    @field_validator("case_id", "issue_description", "error_log", "error_log_version")
    @classmethod
    def _trim_required_text(cls, value: str) -> str:
        """Reject whitespace-only projection values."""
        value = value.strip()
        if not value:
            raise ValueError("projection text must not be blank")
        return value

    @field_validator("repository")
    @classmethod
    def _repository_is_relative(cls, value: str) -> str:
        """Keep repository references inside the project root."""
        return _validate_relative_path(value, field_name="repository")

    def agent_input(self) -> AgentCaseInput:
        """Return the explicit allow-list projection consumed by the Agent."""
        return AgentCaseInput(
            case_id=self.case_id,
            repository=self.repository,
            issue_description=self.issue_description,
            error_log=self.error_log,
            error_log_version=self.error_log_version,
        )


class AgentCaseInput(BaseModel):
    """Immutable allow-list DTO for the Agent-facing layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    issue_description: str = Field(min_length=1)
    error_log: str = Field(min_length=1)
    error_log_version: str = Field(min_length=1)


class FreshHoldoutV2Manifest(BaseModel):
    """The non-Gold Agent manifest contract used by the Fresh v2 loader."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["fresh-holdout-v2-agent-manifest-v1"]
    benchmark_version: Literal["fresh_holdout_v2"]
    status: Literal["REGISTERED_BEFORE_AGENT_EXECUTION"]
    case_count: int = Field(ge=1)
    case_ids: list[str] = Field(min_length=1)
    cases_path: str = Field(min_length=1)
    execution_contract: FreshHoldoutV2ExecutionContract
    agent_projection_fields: list[str] = Field(min_length=1)
    gold_projection: Literal["excluded"]
    reference_material: str = Field(min_length=1)

    @field_validator("cases_path")
    @classmethod
    def _cases_path_is_relative(cls, value: str) -> str:
        """Keep the case manifest path relative to the project root."""
        return _validate_relative_path(value, field_name="cases_path")

    @model_validator(mode="after")
    def _validate_identity(self) -> FreshHoldoutV2Manifest:
        """Validate the frozen case identity and strict projection allow-list."""
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("case_ids must be unique")
        if tuple(self.agent_projection_fields) != FRESH_HOLDOUT_V2_PROJECTION_FIELDS:
            raise ValueError("agent_projection_fields do not match the Fresh v2 allow-list")
        contract = self.execution_contract
        if any(
            count != 0
            for count in (
                contract.agent_executions,
                contract.mock_executions,
                contract.live_executions,
                contract.llm_benchmark_calls,
            )
        ):
            raise ValueError("Fresh v2 manifest must be pre-execution")
        if contract.fresh_holdout_execution:
            raise ValueError("Fresh v2 manifest must not be marked executed")
        return self
