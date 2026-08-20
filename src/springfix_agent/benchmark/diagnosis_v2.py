"""Deterministic semantic diagnosis evaluation with versioned Gold metadata.

Diagnosis V2 is deliberately independent from the historical keyword-based
``evaluate_case`` contract.  It consumes only post-output, sanitized diagnosis
artifacts plus evaluator-only metadata; none of the metadata is projected to
the Agent or used by the repair pipeline.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from springfix_agent.benchmark.result_models import CaseResult

DIAGNOSIS_V2_SCHEMA_VERSION = "diagnosis-semantic-v2.0"
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|[;\n]+")
_WHITESPACE = re.compile(r"\s+")


class DiagnosisV2ManifestError(ValueError):
    """Raised when versioned Diagnosis V2 metadata is invalid."""


def _non_empty_aliases(value: object, *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    aliases: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        aliases.append(item.strip())
    if len({alias.casefold() for alias in aliases}) != len(aliases):
        raise ValueError(f"{field_name} must not contain duplicate aliases")
    return aliases


class SemanticConceptGroup(BaseModel):
    """Equivalent expressions for one required root-cause concept."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    aliases: list[str] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("aliases", mode="before")
    @classmethod
    def _validate_aliases(cls, value: object) -> list[str]:
        return _non_empty_aliases(value, field_name="aliases")


class SemanticRelationVariant(BaseModel):
    """One directional left → relation → right expression."""

    model_config = ConfigDict(extra="forbid")

    left_aliases: list[str] = Field(min_length=1)
    relation_aliases: list[str] = Field(min_length=1)
    right_aliases: list[str] = Field(min_length=1)

    @field_validator("left_aliases", "relation_aliases", "right_aliases", mode="before")
    @classmethod
    def _validate_aliases(cls, value: object, info: Any) -> list[str]:
        return _non_empty_aliases(value, field_name=info.field_name or "relation aliases")


class SemanticRelationGroup(BaseModel):
    """Alternative phrasings for one required or contradictory relationship."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    variants: list[SemanticRelationVariant] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class DiagnosisSemanticV2Spec(BaseModel):
    """Evaluator-only semantic contract for one benchmark case."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["diagnosis-semantic-v2.0"]
    case_id: str = Field(min_length=1)
    required_concepts: list[SemanticConceptGroup] = Field(min_length=1)
    required_relations: list[SemanticRelationGroup] = Field(min_length=1)
    forbidden_relations: list[SemanticRelationGroup] = Field(default_factory=list)

    @field_validator("case_id")
    @classmethod
    def _trim_case_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("case_id must not be blank")
        return value

    @model_validator(mode="after")
    def _unique_dimension_names(self) -> DiagnosisSemanticV2Spec:
        names = [group.name for group in self.required_concepts]
        names.extend(group.name for group in self.required_relations)
        names.extend(group.name for group in self.forbidden_relations)
        if len(set(names)) != len(names):
            raise ValueError("semantic dimension names must be unique within a case")
        return self


class DiagnosisV2Input(BaseModel):
    """Bounded, sanitized diagnosis data required by the V2 evaluator."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    agent_completed: bool
    diagnosis_status_match: bool
    issue_category_match: bool
    expected_file_hit: bool
    evidence_target_hit_count: int = Field(ge=0)
    invalid_rejected_evidence_count: int = Field(ge=0)
    root_cause_summary: str | None = None
    candidates: list[dict[str, object]] = Field(default_factory=list)

    @classmethod
    def from_case_result(cls, result: CaseResult) -> DiagnosisV2Input:
        """Build V2 input from a sanitized M4C ``CaseResult``."""
        metrics = result.metrics
        return cls(
            case_id=result.case_id,
            agent_completed=metrics.agent_completed,
            diagnosis_status_match=metrics.diagnosis_status_match,
            issue_category_match=metrics.issue_category_match,
            expected_file_hit=metrics.expected_file_hit,
            evidence_target_hit_count=metrics.evidence_target_hit_count,
            invalid_rejected_evidence_count=metrics.rejected_evidence_count,
            root_cause_summary=result.root_cause_summary,
            candidates=result.candidates,
        )

    @classmethod
    def from_e2e_record(cls, record: Mapping[str, object]) -> DiagnosisV2Input:
        """Adapt an archived E2E case without inventing omitted diagnosis text."""
        raw_candidates = record.get("diagnosis_candidates")
        candidates = (
            [dict(item) for item in raw_candidates if isinstance(item, Mapping)]
            if isinstance(raw_candidates, list)
            else []
        )
        summary = record.get("root_cause_summary")
        raw_target_recall = record.get("evidence_target_recall", 0.0)
        target_recall = (
            float(raw_target_recall)
            if isinstance(raw_target_recall, (int, float))
            else 0.0
        )
        raw_rejected = record.get("rejected_evidence_count", 0)
        rejected_count = raw_rejected if isinstance(raw_rejected, int) else 0
        return cls(
            case_id=str(record.get("case_id", "")),
            agent_completed=bool(record.get("diagnosis_completed", False)),
            diagnosis_status_match=bool(record.get("diagnosis_status_match", False)),
            issue_category_match=bool(record.get("issue_category_match", False)),
            expected_file_hit=bool(record.get("expected_file_hit", False)),
            evidence_target_hit_count=1 if target_recall > 0.0 else 0,
            invalid_rejected_evidence_count=rejected_count,
            root_cause_summary=str(summary) if isinstance(summary, str) else None,
            candidates=candidates,
        )


class DiagnosisV2Result(BaseModel):
    """Deterministic per-case V2 result with explicit evidence limitations."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["diagnosis-semantic-v2.0"] = "diagnosis-semantic-v2.0"
    case_id: str
    evaluation_status: Literal["evaluated", "insufficient_artifact"]
    semantic_pass: bool | None
    semantic_score: float | None
    structural_conditions: dict[str, bool]
    required_concept_hits: dict[str, bool]
    required_relation_hits: dict[str, bool]
    contradiction_hits: list[str]
    failure_reasons: list[str]
    evidence_limitation: str | None = None


class DiagnosisV2Aggregate(BaseModel):
    """Aggregate that keeps not-evaluable archived cases distinct from failures."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["diagnosis-semantic-v2.0"] = "diagnosis-semantic-v2.0"
    cases_total: int
    cases_evaluated: int
    cases_passed: int
    cases_failed: int
    cases_insufficient_artifact: int
    pass_rate_over_evaluated: float | None
    mean_semantic_score_over_evaluated: float | None


def load_diagnosis_v2_specs(path: Path) -> list[DiagnosisSemanticV2Spec]:
    """Load strict versioned JSONL metadata and reject duplicate case IDs."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DiagnosisV2ManifestError(f"cannot read Diagnosis V2 metadata {path}: {exc}") from exc

    specs: list[DiagnosisSemanticV2Spec] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            spec = DiagnosisSemanticV2Spec.model_validate_json(raw_line)
        except (ValidationError, ValueError) as exc:
            raise DiagnosisV2ManifestError(
                f"invalid Diagnosis V2 metadata at line {line_number}: {exc}"
            ) from exc
        if spec.case_id in seen:
            raise DiagnosisV2ManifestError(
                f"duplicate Diagnosis V2 case_id {spec.case_id!r} at line {line_number}"
            )
        seen.add(spec.case_id)
        specs.append(spec)
    if not specs:
        raise DiagnosisV2ManifestError(f"Diagnosis V2 metadata contains no cases: {path}")
    return specs


def _normalize(value: str) -> str:
    return _WHITESPACE.sub(" ", value.casefold().replace("\\", "/")).strip()


def _alias_spans(text: str, aliases: Sequence[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for alias in aliases:
        normalized = _normalize(alias)
        if not normalized:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    return sorted(set(spans))


def _contains_alias(text: str, aliases: Sequence[str]) -> bool:
    return bool(_alias_spans(text, aliases))


def _relation_variant_hit(clause: str, variant: SemanticRelationVariant) -> bool:
    left = _alias_spans(clause, variant.left_aliases)
    relations = _alias_spans(clause, variant.relation_aliases)
    right = _alias_spans(clause, variant.right_aliases)
    return any(
        left_end <= relation_start and relation_end <= right_start
        for _, left_end in left
        for relation_start, relation_end in relations
        for right_start, _ in right
    )


def _relation_group_hit(clauses: Sequence[str], group: SemanticRelationGroup) -> bool:
    return any(
        _relation_variant_hit(clause, variant)
        for clause in clauses
        for variant in group.variants
    )


def _semantic_parts(value: DiagnosisV2Input) -> list[str]:
    parts: list[str] = []
    if value.root_cause_summary and value.root_cause_summary.strip():
        parts.append(value.root_cause_summary[:2000])
    for candidate in value.candidates[:3]:
        for key in ("title", "description", "recommended_fix"):
            item = candidate.get(key)
            if isinstance(item, str) and item.strip():
                parts.append(item[:2000])
    return parts


def evaluate_diagnosis_v2(
    value: DiagnosisV2Input, spec: DiagnosisSemanticV2Spec
) -> DiagnosisV2Result:
    """Evaluate semantic concepts and directional relations deterministically."""
    if value.case_id != spec.case_id:
        raise ValueError(
            f"Diagnosis V2 input/spec case mismatch: {value.case_id!r} != {spec.case_id!r}"
        )

    structural = {
        "agent_completed": value.agent_completed,
        "diagnosis_status_match": value.diagnosis_status_match,
        "issue_category_match": value.issue_category_match,
        "expected_source_file_hit": value.expected_file_hit,
        "evidence_target_hit": value.evidence_target_hit_count > 0,
        "no_invalid_rejected_evidence": value.invalid_rejected_evidence_count == 0,
    }
    parts = _semantic_parts(value)
    if not parts:
        return DiagnosisV2Result(
            case_id=value.case_id,
            evaluation_status="insufficient_artifact",
            semantic_pass=None,
            semantic_score=None,
            structural_conditions=structural,
            required_concept_hits={},
            required_relation_hits={},
            contradiction_hits=[],
            failure_reasons=["semantic_text_not_archived"],
            evidence_limitation=(
                "The archived E2E result omits the bounded diagnosis summary and candidate text "
                "required for deterministic semantic replay."
            ),
        )

    normalized_parts = [_normalize(part) for part in parts]
    semantic_text = "\n".join(normalized_parts)
    clauses = [
        clause
        for part in normalized_parts
        for clause in (_normalize(item) for item in _SENTENCE_BOUNDARY.split(part))
        if clause
    ]
    concept_hits = {
        group.name: _contains_alias(semantic_text, group.aliases)
        for group in spec.required_concepts
    }
    relation_hits = {
        group.name: _relation_group_hit(clauses, group)
        for group in spec.required_relations
    }
    contradictions = [
        group.name
        for group in spec.forbidden_relations
        if _relation_group_hit(clauses, group)
    ]

    components = [*structural.values(), *concept_hits.values(), *relation_hits.values()]
    components.append(not contradictions)
    passed = all(components)
    score = round(sum(components) / len(components), 4) if components else 0.0
    failures = [name for name, hit in structural.items() if not hit]
    failures.extend(f"missing_concept:{name}" for name, hit in concept_hits.items() if not hit)
    failures.extend(f"missing_relation:{name}" for name, hit in relation_hits.items() if not hit)
    failures.extend(f"contradiction:{name}" for name in contradictions)
    return DiagnosisV2Result(
        case_id=value.case_id,
        evaluation_status="evaluated",
        semantic_pass=passed,
        semantic_score=score,
        structural_conditions=structural,
        required_concept_hits=concept_hits,
        required_relation_hits=relation_hits,
        contradiction_hits=contradictions,
        failure_reasons=failures,
    )


def aggregate_diagnosis_v2(results: Sequence[DiagnosisV2Result]) -> DiagnosisV2Aggregate:
    """Aggregate evaluated cases without treating missing artifacts as semantic failures."""
    evaluated = [result for result in results if result.evaluation_status == "evaluated"]
    passed = sum(result.semantic_pass is True for result in evaluated)
    scores = [result.semantic_score for result in evaluated if result.semantic_score is not None]
    return DiagnosisV2Aggregate(
        cases_total=len(results),
        cases_evaluated=len(evaluated),
        cases_passed=passed,
        cases_failed=len(evaluated) - passed,
        cases_insufficient_artifact=len(results) - len(evaluated),
        pass_rate_over_evaluated=(round(passed / len(evaluated), 4) if evaluated else None),
        mean_semantic_score_over_evaluated=(
            round(statistics.mean(scores), 4) if scores else None
        ),
    )


def replay_frozen_e2e_summary(
    summary: Mapping[str, object], specs: Sequence[DiagnosisSemanticV2Spec]
) -> dict[str, object]:
    """Replay archived E2E metrics without invoking the Agent or an LLM."""
    raw_cases = summary.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("frozen E2E summary does not contain a cases list")
    specs_by_id = {spec.case_id: spec for spec in specs}
    v1_cases: list[dict[str, object]] = []
    v2_results: list[DiagnosisV2Result] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise ValueError("frozen E2E summary contains a non-object case")
        case_id = str(raw_case.get("case_id", ""))
        spec = specs_by_id.get(case_id)
        if spec is None:
            raise ValueError(f"missing Diagnosis V2 metadata for frozen case {case_id!r}")
        v1_cases.append(
            {
                "case_id": case_id,
                "keyword_coverage": float(
                    raw_case.get("root_cause_keyword_coverage", 0.0) or 0.0
                ),
                "keyword_pass": bool(raw_case.get("diagnosis_benchmark_pass", False)),
            }
        )
        v2_results.append(
            evaluate_diagnosis_v2(DiagnosisV2Input.from_e2e_record(raw_case), spec)
        )

    aggregate = summary.get("aggregate")
    aggregate_map = aggregate if isinstance(aggregate, Mapping) else {}
    return {
        "schema_version": "diagnosis-v2-frozen-replay.1",
        "source_run_id": str(summary.get("run_id", "unknown")),
        "agent_rerun": False,
        "new_llm_calls": 0,
        "repair_success": {
            "passed": int(aggregate_map.get("repair_success_count", 0) or 0),
            "total": int(aggregate_map.get("sample_size", len(raw_cases)) or len(raw_cases)),
        },
        "diagnosis_v1": {
            "passed": sum(bool(item["keyword_pass"]) for item in v1_cases),
            "total": len(v1_cases),
            "cases": v1_cases,
        },
        "diagnosis_v2": {
            "aggregate": aggregate_diagnosis_v2(v2_results).model_dump(),
            "cases": [result.model_dump() for result in v2_results],
        },
    }


def load_frozen_summary(path: Path) -> dict[str, object]:
    """Read one frozen summary as a JSON object for the offline replay script."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read frozen E2E summary {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"frozen E2E summary must be a JSON object: {path}")
    return payload
