"""Loader for the Fresh Holdout v2 Agent-facing manifest only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from scripts.m7f1.fresh_holdout_v2_schema import (
    FreshHoldoutV2Case,
    FreshHoldoutV2Manifest,
)


class FreshHoldoutV2SchemaError(ValueError):
    """Raised for malformed or semantically invalid Fresh v2 input."""


class FreshHoldoutV2InfrastructureError(RuntimeError):
    """Raised when the frozen Agent-facing files cannot be read."""


class FreshHoldoutV2Loader:
    """Load Fresh v2 cases without opening Gold or reference-patch files."""

    def __init__(self, *, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def load(self, manifest_path: Path) -> tuple[FreshHoldoutV2Manifest, tuple[FreshHoldoutV2Case, ...]]:
        """Load and validate only the Agent manifest and its cases JSONL."""
        manifest = self._load_manifest(manifest_path)
        cases_path = self._resolve_relative(manifest.cases_path, field_name="cases_path")
        cases = self._load_cases(cases_path)
        if manifest.case_count != len(cases):
            raise FreshHoldoutV2SchemaError(
                f"case_count mismatch: manifest={manifest.case_count} loaded={len(cases)}"
            )
        case_ids = tuple(case.case_id for case in cases)
        if case_ids != tuple(manifest.case_ids):
            raise FreshHoldoutV2SchemaError("case_ids do not match the frozen manifest")
        return manifest, cases

    def _load_manifest(self, manifest_path: Path) -> FreshHoldoutV2Manifest:
        """Read and validate the non-Gold Agent manifest."""
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise FreshHoldoutV2InfrastructureError(
                f"cannot read Fresh v2 Agent manifest: {manifest_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise FreshHoldoutV2SchemaError(
                f"invalid Fresh v2 Agent manifest JSON: {manifest_path}"
            ) from exc
        try:
            return FreshHoldoutV2Manifest.model_validate(payload)
        except (ValidationError, TypeError, ValueError) as exc:
            raise FreshHoldoutV2SchemaError("invalid Fresh v2 Agent manifest schema") from exc

    def _load_cases(self, cases_path: Path) -> tuple[FreshHoldoutV2Case, ...]:
        """Read and validate the blinded cases JSONL."""
        try:
            lines = cases_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise FreshHoldoutV2InfrastructureError(
                f"cannot read Fresh v2 cases: {cases_path}"
            ) from exc

        cases: list[FreshHoldoutV2Case] = []
        seen_ids: set[str] = set()
        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload: Any = json.loads(line)
                case = FreshHoldoutV2Case.model_validate(payload)
            except json.JSONDecodeError as exc:
                raise FreshHoldoutV2SchemaError(
                    f"invalid Fresh v2 case JSON at line {line_number}"
                ) from exc
            except (ValidationError, TypeError, ValueError) as exc:
                raise FreshHoldoutV2SchemaError(
                    f"invalid Fresh v2 case schema at line {line_number}"
                ) from exc
            if case.case_id in seen_ids:
                raise FreshHoldoutV2SchemaError(f"duplicate Fresh v2 case_id: {case.case_id}")
            seen_ids.add(case.case_id)
            cases.append(case)
        if not cases:
            raise FreshHoldoutV2SchemaError("Fresh v2 cases manifest is empty")
        return tuple(cases)

    def _resolve_relative(self, relative: str, *, field_name: str) -> Path:
        """Resolve a manifest path while enforcing the project boundary."""
        candidate = (self.project_root / relative).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise FreshHoldoutV2SchemaError(f"{field_name} escapes project root") from exc
        return candidate
