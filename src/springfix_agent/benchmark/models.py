"""Pydantic models for the M4B benchmark manifest.

Gold fields are intentionally kept in these models and are never projected
into ``AgentState`` or retrieval queries.  The runner and validator consume
them only after an agent-facing input has been constructed.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


def _non_empty_strings(value: object, *, field_name: str) -> list[str]:
    """Return a bounded list of non-empty strings or raise a useful error."""
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        result.append(item.strip())
    return result


def _validate_relative_path(value: str, *, field_name: str) -> str:
    """Reject absolute paths and parent traversal in manifest path fields."""
    value = value.strip()
    is_absolute = (
        Path(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or value.startswith(("/", "\\"))
    )
    if is_absolute or (len(value) >= 3 and value[1] == ":" and value[2] in "/\\"):
        raise ValueError(f"{field_name} must be a relative path")
    if ".." in value.replace("\\", "/").split("/"):
        raise ValueError(f"{field_name} must not contain '..'")
    if not value:
        raise ValueError(f"{field_name} must not be blank")
    return value


class EvidenceTarget(BaseModel):
    """A gold file and line range used by the manifest validator."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    required_text: list[str] = Field(min_length=1)

    @field_validator("file")
    @classmethod
    def _trim_file(cls, value: str) -> str:
        """Reject blank path values while preserving relative path spelling."""
        return _validate_relative_path(value, field_name="file")

    @field_validator("required_text", mode="before")
    @classmethod
    def _validate_required_text(cls, value: object) -> list[str]:
        """Require at least one non-empty evidence token."""
        return _non_empty_strings(value, field_name="required_text")

    @model_validator(mode="after")
    def _validate_range(self) -> EvidenceTarget:
        """Ensure the inclusive evidence range is ordered."""
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class ExpectedMavenResult(BaseModel):
    """Expected Surefire counters and assertion-failure terms for one case."""

    model_config = ConfigDict(extra="forbid")

    test_name: str = Field(min_length=1)
    tests: int = Field(ge=0)
    failures: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    required_failure_terms: list[str] = Field(default_factory=list)

    @field_validator("test_name")
    @classmethod
    def _trim_test_name(cls, value: str) -> str:
        """Normalize the testcase name used for Surefire lookup."""
        value = value.strip()
        if not value:
            raise ValueError("test_name must not be blank")
        return value

    @field_validator("required_failure_terms", mode="before")
    @classmethod
    def _validate_failure_terms(cls, value: object) -> list[str]:
        """Allow an empty term list but reject blank entries."""
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("required_failure_terms must be a list")
        result: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("required_failure_terms must contain strings")
            result.append(item.strip())
        return result


class BenchmarkCase(BaseModel):
    """One offline bug reproduction case and its gold verification data."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    issue_description: str = Field(min_length=1)
    error_log: str | None = None
    expected_issue_category: str = Field(min_length=1)
    expected_diagnosis_status: Literal[
        "complete", "partial", "insufficient_evidence"
    ]
    expected_root_cause_keywords: list[str] = Field(default_factory=list)
    expected_files: list[str] = Field(min_length=1)
    expected_symbols: list[str] = Field(min_length=1)
    evidence_targets: list[EvidenceTarget] = Field(min_length=1)
    expected_maven: ExpectedMavenResult

    @field_validator("case_id", "repository", "expected_issue_category")
    @classmethod
    def _trim_required_text(cls, value: str) -> str:
        """Reject whitespace-only identifiers and labels."""
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("repository")
    @classmethod
    def _repository_is_relative(cls, value: str) -> str:
        """Keep repository references portable and inside the runner root."""
        return _validate_relative_path(value, field_name="repository")

    @field_validator("expected_root_cause_keywords", mode="before")
    @classmethod
    def _validate_keywords(cls, value: object) -> list[str]:
        """Normalize optional gold keywords without inventing defaults."""
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("expected_root_cause_keywords must be a list")
        result: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("expected_root_cause_keywords must contain strings")
            result.append(item.strip())
        return result

    @field_validator("expected_files", "expected_symbols", mode="before")
    @classmethod
    def _validate_gold_lists(cls, value: object, info: ValidationInfo) -> list[str]:
        """Require non-empty file and symbol gold lists."""
        field_name = info.field_name or "gold field"
        values = _non_empty_strings(value, field_name=field_name)
        if field_name == "expected_files":
            return [
                _validate_relative_path(item, field_name="expected_files entry")
                for item in values
            ]
        return values

    def agent_input(self) -> dict[str, str | None]:
        """Return the only fields that a future benchmark runner may expose."""
        return {
            "repository": self.repository,
            "issue_description": self.issue_description,
            "error_log": self.error_log,
        }

    def gold_data(self) -> dict[str, object]:
        """Return verification-only fields for explicit runner code paths."""
        return {
            "expected_issue_category": self.expected_issue_category,
            "expected_diagnosis_status": self.expected_diagnosis_status,
            "expected_root_cause_keywords": self.expected_root_cause_keywords,
            "expected_files": self.expected_files,
            "expected_symbols": self.expected_symbols,
            "evidence_targets": [target.model_dump() for target in self.evidence_targets],
            "expected_maven": self.expected_maven.model_dump(),
        }
