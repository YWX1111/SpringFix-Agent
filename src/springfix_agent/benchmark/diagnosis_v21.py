"""Versioned, evaluator-only Diagnosis V2.1 fairness calibration.

V2.1 is intentionally a new contract.  It consumes the same bounded,
post-output diagnosis projection as V2.0, but applies conservative
normalization and bounded relation windows so that equivalent natural
language is recognized without weakening directionality or contradiction
checks.  It never imports Agent state, prompts, retrieval, repair output, or
holdout material.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

DIAGNOSIS_V21_SCHEMA_VERSION = "diagnosis-semantic-v2.1"
V21_REPLAY_SCHEMA_VERSION = "diagnosis-v21-frozen-replay.1"

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|[;\n]+")
_WHITESPACE = re.compile(r"\s+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_WORD = re.compile(r"[^\w]+")
_NUMERIC_TOKEN = re.compile(r"(?<!\w)\d+(?!\w)")

# This is deliberately a finite, auditable morphology table.  It avoids an
# unrestricted stemmer that could make unrelated adversarial text match.
_BOUNDED_TOKEN_VARIANTS = {
    "aliases": "alias",
    "applications": "application",
    "beans": "bean",
    "conditions": "condition",
    "configurations": "configuration",
    "constraints": "constraint",
    "defaults": "default",
    "endpoints": "endpoint",
    "files": "file",
    "implementations": "implementation",
    "maps": "map",
    "properties": "property",
    "profiles": "profile",
    "providers": "provider",
    "relations": "relation",
    "senders": "sender",
    "settings": "setting",
    "sources": "source",
    "values": "value",
    "activates": "activate",
    "causes": "cause",
    "does": "do",
    "expects": "expect",
    "fails": "fail",
    "leaves": "leave",
    "matches": "match",
    "overridden": "override",
    "overrides": "override",
    "overriding": "override",
    "registered": "register",
    "requires": "require",
    "results": "result",
    "satisfies": "satisfy",
    "takes": "take",
    "binding": "bind",
    "specifies": "specify",
    "violates": "violate",
}


class DiagnosisV21ManifestError(ValueError):
    """Raised when V2.1 metadata or regression data is invalid."""


def _non_empty_aliases(value: object, *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    aliases: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        aliases.append(item.strip())
    if len({_normalize(alias) for alias in aliases}) != len(aliases):
        raise ValueError(f"{field_name} must not contain duplicate normalized aliases")
    return aliases


class SemanticBoundedPattern(BaseModel):
    """A bounded anchor/value pair for non-adjacent numeric expressions."""

    model_config = ConfigDict(extra="forbid")

    anchor_aliases: list[str] = Field(min_length=1)
    value_aliases: list[str] = Field(min_length=1)
    max_token_distance: int = Field(default=8, ge=1, le=16)

    @field_validator("anchor_aliases", "value_aliases", mode="before")
    @classmethod
    def _validate_aliases(cls, value: object, info: Any) -> list[str]:
        return _non_empty_aliases(value, field_name=info.field_name or "aliases")


class SemanticConceptGroupV21(BaseModel):
    """Equivalent expressions for one required V2.1 concept."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    bounded_patterns: list[SemanticBoundedPattern] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("aliases", mode="before")
    @classmethod
    def _validate_optional_aliases(cls, value: object) -> list[str]:
        if value in (None, []):
            return []
        return _non_empty_aliases(value, field_name="aliases")

    @model_validator(mode="after")
    def _require_match_expression(self) -> SemanticConceptGroupV21:
        if not self.aliases and not self.bounded_patterns:
            raise ValueError("concept group requires aliases or bounded_patterns")
        return self


class SemanticRelationVariantV21(BaseModel):
    """One directional left -> relation -> right expression."""

    model_config = ConfigDict(extra="forbid")

    left_aliases: list[str] = Field(min_length=1)
    relation_aliases: list[str] = Field(min_length=1)
    right_aliases: list[str] = Field(min_length=1)
    required_value_aliases: list[str] = Field(default_factory=list)
    max_token_distance: int = Field(default=24, ge=1, le=48)
    value_max_token_distance: int = Field(default=8, ge=1, le=16)

    @field_validator(
        "left_aliases",
        "relation_aliases",
        "right_aliases",
        "required_value_aliases",
        mode="before",
    )
    @classmethod
    def _validate_aliases(cls, value: object, info: Any) -> list[str]:
        if info.field_name == "required_value_aliases" and value in (None, []):
            return []
        return _non_empty_aliases(value, field_name=info.field_name or "aliases")


class SemanticRelationGroupV21(BaseModel):
    """Alternative phrasings for one required or forbidden relationship."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    variants: list[SemanticRelationVariantV21] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class DiagnosisSemanticV21Spec(BaseModel):
    """Evaluator-only semantic contract for one development case."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["diagnosis-semantic-v2.1"]
    case_id: str = Field(min_length=1)
    required_concepts: list[SemanticConceptGroupV21] = Field(min_length=1)
    required_relations: list[SemanticRelationGroupV21] = Field(min_length=1)
    forbidden_relations: list[SemanticRelationGroupV21] = Field(default_factory=list)

    @field_validator("case_id")
    @classmethod
    def _trim_case_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("case_id must not be blank")
        return value

    @model_validator(mode="after")
    def _unique_dimension_names(self) -> DiagnosisSemanticV21Spec:
        names = [group.name for group in self.required_concepts]
        names.extend(group.name for group in self.required_relations)
        names.extend(group.name for group in self.forbidden_relations)
        if len(set(names)) != len(names):
            raise ValueError("semantic dimension names must be unique within a case")
        return self


class DiagnosisV21Input(BaseModel):
    """Bounded diagnosis data accepted by V2.1."""

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
    def from_e2e_record(cls, record: Mapping[str, object]) -> DiagnosisV21Input:
        raw_candidates = record.get("diagnosis_candidates")
        candidates = (
            [dict(item) for item in raw_candidates if isinstance(item, Mapping)]
            if isinstance(raw_candidates, list)
            else []
        )
        raw_target_recall = record.get("evidence_target_recall", 0.0)
        target_recall = (
            float(raw_target_recall) if isinstance(raw_target_recall, (int, float)) else 0.0
        )
        raw_rejected = record.get("rejected_evidence_count", 0)
        return cls(
            case_id=str(record.get("case_id", "")),
            agent_completed=bool(record.get("diagnosis_completed", False)),
            diagnosis_status_match=bool(record.get("diagnosis_status_match", False)),
            issue_category_match=bool(record.get("issue_category_match", False)),
            expected_file_hit=bool(record.get("expected_file_hit", False)),
            evidence_target_hit_count=1 if target_recall > 0.0 else 0,
            invalid_rejected_evidence_count=raw_rejected if isinstance(raw_rejected, int) else 0,
            root_cause_summary=(
                str(record["root_cause_summary"])
                if isinstance(record.get("root_cause_summary"), str)
                else None
            ),
            candidates=candidates,
        )


class DiagnosisV21Result(BaseModel):
    """Deterministic V2.1 per-case result."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["diagnosis-semantic-v2.1"] = "diagnosis-semantic-v2.1"
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


class DiagnosisV21Aggregate(BaseModel):
    """Aggregate preserving the distinction between failure and absent text."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["diagnosis-semantic-v2.1"] = "diagnosis-semantic-v2.1"
    cases_total: int
    cases_evaluated: int
    cases_passed: int
    cases_failed: int
    cases_insufficient_artifact: int
    pass_rate_over_evaluated: float | None
    mean_semantic_score_over_evaluated: float | None


class DiagnosisV21Regression(BaseModel):
    """One bounded confirmed-paraphrase regression record."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["diagnosis-semantic-v2.1-regression"]
    regression_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    semantic_component_id: str = Field(min_length=1)
    bounded_input: dict[str, str] = Field(min_length=1)
    expected_v2_0: dict[str, object]
    expected_v2_1: dict[str, object]


def _split_camel(value: str) -> str:
    return _CAMEL_BOUNDARY.sub(" ", value)


def _normalize_token(token: str) -> str:
    return _BOUNDED_TOKEN_VARIANTS.get(token, token)


def _normalize(value: str) -> str:
    """Normalize punctuation, CamelCase, and finite morphology into tokens."""
    prepared = _split_camel(value.replace("\\", "/"))
    prepared = _NON_WORD.sub(" ", prepared.casefold())
    tokens = [_normalize_token(token) for token in prepared.split()]
    return _WHITESPACE.sub(" ", " ".join(tokens)).strip()


def _alias_spans(text: str, aliases: Sequence[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for alias in aliases:
        normalized = _normalize(alias)
        if not normalized:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    return sorted(set(spans))


def _token_count(value: str) -> int:
    return len(value.split())


def _span_token_distance(text: str, start: int, end: int) -> int:
    return _token_count(text[start:end])


def _has_intervening_numeric(text: str, start: int, end: int) -> bool:
    """Reject a value span if another numeric value intervenes before it."""
    return bool(_NUMERIC_TOKEN.search(text[start:end]))


def _contains_alias(text: str, aliases: Sequence[str]) -> bool:
    return bool(_alias_spans(text, aliases))


def _bounded_pattern_hit(text: str, pattern: SemanticBoundedPattern) -> bool:
    anchors = _alias_spans(text, pattern.anchor_aliases)
    values = _alias_spans(text, pattern.value_aliases)
    return any(
        anchor_end <= value_start
        and _span_token_distance(text, anchor_end, value_start) <= pattern.max_token_distance
        and not _has_intervening_numeric(text, anchor_end, value_start)
        for _, anchor_end in anchors
        for value_start, _ in values
    )


def _concept_group_hit(text: str, group: SemanticConceptGroupV21) -> bool:
    return _contains_alias(text, group.aliases) or any(
        _bounded_pattern_hit(text, pattern) for pattern in group.bounded_patterns
    )


def _relation_variant_hit(clause: str, variant: SemanticRelationVariantV21) -> bool:
    left = _alias_spans(clause, variant.left_aliases)
    relations = _alias_spans(clause, variant.relation_aliases)
    right = _alias_spans(clause, variant.right_aliases)
    values = _alias_spans(clause, variant.required_value_aliases)
    for _, left_end in left:
        for relation_start, relation_end in relations:
            if relation_start < left_end:
                continue
            for right_start, _ in right:
                if right_start < relation_end:
                    continue
                if _span_token_distance(clause, left_end, right_start) > variant.max_token_distance:
                    continue
                if variant.required_value_aliases:
                    value_ok = any(
                        left_end <= value_start <= relation_start
                        and _span_token_distance(clause, left_end, value_start)
                        <= variant.value_max_token_distance
                        and not _has_intervening_numeric(clause, left_end, value_start)
                        for value_start, _ in values
                    )
                    if not value_ok:
                        continue
                return True
    return False


def _relation_group_hit(clauses: Sequence[str], group: SemanticRelationGroupV21) -> bool:
    return any(
        _relation_variant_hit(clause, variant) for clause in clauses for variant in group.variants
    )


def _semantic_parts(value: DiagnosisV21Input) -> list[str]:
    parts: list[str] = []
    if value.root_cause_summary and value.root_cause_summary.strip():
        parts.append(value.root_cause_summary[:2000])
    for candidate in value.candidates[:3]:
        for key in ("title", "description", "recommended_fix"):
            item = candidate.get(key)
            if isinstance(item, str) and item.strip():
                parts.append(item[:2000])
    return parts


def evaluate_diagnosis_v21(
    value: DiagnosisV21Input, spec: DiagnosisSemanticV21Spec
) -> DiagnosisV21Result:
    """Evaluate V2.1 concepts and directional relations deterministically."""
    if value.case_id != spec.case_id:
        raise ValueError(
            f"Diagnosis V2.1 input/spec case mismatch: {value.case_id!r} != {spec.case_id!r}"
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
        return DiagnosisV21Result(
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
                "required for deterministic V2.1 replay."
            ),
        )

    normalized_parts = [_normalize(part) for part in parts]
    semantic_text = "\n".join(normalized_parts)
    clauses = [
        clause
        for part in parts
        for clause in (_normalize(item) for item in _SENTENCE_BOUNDARY.split(part))
        if clause
    ]
    concept_hits = {
        group.name: _concept_group_hit(semantic_text, group) for group in spec.required_concepts
    }
    relation_hits = {
        group.name: _relation_group_hit(clauses, group) for group in spec.required_relations
    }
    contradictions = [
        group.name for group in spec.forbidden_relations if _relation_group_hit(clauses, group)
    ]
    components = [*structural.values(), *concept_hits.values(), *relation_hits.values()]
    components.append(not contradictions)
    passed = all(components)
    score = round(sum(components) / len(components), 4) if components else 0.0
    failures = [name for name, hit in structural.items() if not hit]
    failures.extend(f"missing_concept:{name}" for name, hit in concept_hits.items() if not hit)
    failures.extend(f"missing_relation:{name}" for name, hit in relation_hits.items() if not hit)
    failures.extend(f"contradiction:{name}" for name in contradictions)
    return DiagnosisV21Result(
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


def aggregate_diagnosis_v21(results: Sequence[DiagnosisV21Result]) -> DiagnosisV21Aggregate:
    """Aggregate V2.1 cases without treating missing artifacts as failures."""
    evaluated = [result for result in results if result.evaluation_status == "evaluated"]
    passed = sum(result.semantic_pass is True for result in evaluated)
    scores = [result.semantic_score for result in evaluated if result.semantic_score is not None]
    return DiagnosisV21Aggregate(
        cases_total=len(results),
        cases_evaluated=len(evaluated),
        cases_passed=passed,
        cases_failed=len(evaluated) - passed,
        cases_insufficient_artifact=len(results) - len(evaluated),
        pass_rate_over_evaluated=(round(passed / len(evaluated), 4) if evaluated else None),
        mean_semantic_score_over_evaluated=(round(statistics.mean(scores), 4) if scores else None),
    )


def load_diagnosis_v21_specs(path: Path) -> list[DiagnosisSemanticV21Spec]:
    """Load strict V2.1 JSONL metadata and reject duplicate case IDs."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DiagnosisV21ManifestError(
            f"cannot read Diagnosis V2.1 metadata {path}: {exc}"
        ) from exc
    specs: list[DiagnosisSemanticV21Spec] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            spec = DiagnosisSemanticV21Spec.model_validate_json(raw_line)
        except (ValidationError, ValueError) as exc:
            raise DiagnosisV21ManifestError(
                f"invalid Diagnosis V2.1 metadata at line {line_number}: {exc}"
            ) from exc
        if spec.case_id in seen:
            raise DiagnosisV21ManifestError(
                f"duplicate Diagnosis V2.1 case_id {spec.case_id!r} at line {line_number}"
            )
        seen.add(spec.case_id)
        specs.append(spec)
    if not specs:
        raise DiagnosisV21ManifestError(f"Diagnosis V2.1 metadata contains no cases: {path}")
    return specs


def load_diagnosis_v21_regressions(path: Path) -> list[DiagnosisV21Regression]:
    """Load the bounded 11-item confirmed-false-negative corpus."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DiagnosisV21ManifestError(f"cannot read V2.1 regressions {path}: {exc}") from exc
    regressions: list[DiagnosisV21Regression] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            regression = DiagnosisV21Regression.model_validate_json(raw_line)
        except (ValidationError, ValueError) as exc:
            raise DiagnosisV21ManifestError(
                f"invalid V2.1 regression at line {line_number}: {exc}"
            ) from exc
        if regression.regression_id in seen:
            raise DiagnosisV21ManifestError(
                f"duplicate V2.1 regression_id {regression.regression_id!r}"
            )
        seen.add(regression.regression_id)
        regressions.append(regression)
    if len(regressions) != 11:
        raise DiagnosisV21ManifestError(
            f"V2.1 regression corpus must contain 11 items, found {len(regressions)}"
        )
    return regressions


def replay_frozen_e2e_summary_v21(
    summary: Mapping[str, object],
    specs: Sequence[DiagnosisSemanticV21Spec],
    v2_specs: Sequence[Any],
) -> dict[str, object]:
    """Replay V1, frozen V2.0, and independent V2.1 without Agent/LLM calls."""
    from springfix_agent.benchmark.diagnosis_v2 import replay_frozen_e2e_summary

    v2_replay = replay_frozen_e2e_summary(summary, v2_specs)
    raw_cases = summary.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("frozen E2E summary does not contain a cases list")
    specs_by_id = {spec.case_id: spec for spec in specs}
    results: list[DiagnosisV21Result] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise ValueError("frozen E2E summary contains a non-object case")
        case_id = str(raw_case.get("case_id", ""))
        spec = specs_by_id.get(case_id)
        if spec is None:
            raise ValueError(f"missing Diagnosis V2.1 metadata for frozen case {case_id!r}")
        results.append(evaluate_diagnosis_v21(DiagnosisV21Input.from_e2e_record(raw_case), spec))
    return {
        "schema_version": V21_REPLAY_SCHEMA_VERSION,
        "source_run_id": str(summary.get("run_id", "unknown")),
        "agent_rerun": False,
        "new_llm_calls": 0,
        "diagnosis_v1": v2_replay["diagnosis_v1"],
        "diagnosis_v2_0": v2_replay["diagnosis_v2"],
        "diagnosis_v2_1": {
            "aggregate": aggregate_diagnosis_v21(results).model_dump(),
            "cases": [result.model_dump() for result in results],
        },
    }


def load_frozen_summary(path: Path) -> dict[str, object]:
    """Read one frozen summary as a JSON object for offline replay."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read frozen E2E summary {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"frozen E2E summary must be a JSON object: {path}")
    return payload
