"""Versioned, evaluator-only Diagnosis V2.2 correction.

V2.2 is an independent, bounded contract.  It corrects the three defects
documented by M7E-2C2C3 without reading Agent state, prompts, raw responses,
repair output, Maven output, or holdout material.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

DIAGNOSIS_V22_SCHEMA_VERSION = "diagnosis-semantic-v2.2"
V22_REPLAY_SCHEMA_VERSION = "diagnosis-v22-frozen-replay.1"

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|[;\n]+")
_WHITESPACE = re.compile(r"\s+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_WORD = re.compile(r"[^\w]+")
_NUMERIC_TOKEN = re.compile(r"(?<!\w)\d+(?!\w)")

_BOUNDED_TOKEN_VARIANTS = {
    "aliases": "alias", "applications": "application", "beans": "bean",
    "conditions": "condition", "configurations": "configuration", "constraints": "constraint",
    "defaults": "default", "endpoints": "endpoint", "files": "file",
    "implementations": "implementation", "maps": "map", "properties": "property",
    "profiles": "profile", "providers": "provider", "relations": "relation",
    "senders": "sender", "settings": "setting", "sources": "source", "values": "value",
    "activates": "activate", "causes": "cause", "does": "do", "expects": "expect",
    "fails": "fail", "leaves": "leave", "matches": "match", "overridden": "override",
    "overrides": "override", "overriding": "override", "registered": "register",
    "requires": "require", "results": "result", "satisfies": "satisfy", "takes": "take",
    "binding": "bind", "specifies": "specify", "restricts": "restrict", "targets": "target",
    "configured": "configure", "conditionally": "conditional", "disabled": "disable",
}


class DiagnosisV22ManifestError(ValueError):
    """Raised when V2.2 metadata or regression data is invalid."""


def _split_camel(value: str) -> str:
    return _CAMEL_BOUNDARY.sub(" ", value)


def _normalize_token(token: str) -> str:
    return _BOUNDED_TOKEN_VARIANTS.get(token, token)


def _normalize(value: str) -> str:
    """Normalize punctuation, CamelCase, contractions, and finite morphology."""
    prepared = value.replace("doesn't", "does not").replace("doesn’t", "does not")
    prepared = prepared.replace("can't", "cannot").replace("can’t", "cannot")
    prepared = _split_camel(prepared.replace("\\", "/"))
    prepared = _NON_WORD.sub(" ", prepared.casefold())
    tokens = [_normalize_token(token) for token in prepared.split()]
    return _WHITESPACE.sub(" ", " ".join(tokens)).strip()


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


class SemanticBoundedPatternV22(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor_aliases: list[str] = Field(min_length=1)
    value_aliases: list[str] = Field(min_length=1)
    max_token_distance: int = Field(default=8, ge=1, le=16)

    @field_validator("anchor_aliases", "value_aliases", mode="before")
    @classmethod
    def _validate_aliases(cls, value: object, info: Any) -> list[str]:
        return _non_empty_aliases(value, field_name=info.field_name or "aliases")


class SemanticConceptGroupV22(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    bounded_patterns: list[SemanticBoundedPatternV22] = Field(default_factory=list)

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
    def _require_match_expression(self) -> SemanticConceptGroupV22:
        if not self.aliases and not self.bounded_patterns:
            raise ValueError("concept group requires aliases or bounded_patterns")
        return self


class SemanticRelationVariantV22(BaseModel):
    """Directional relation with optional bounded companion context."""

    model_config = ConfigDict(extra="forbid")
    left_aliases: list[str] = Field(min_length=1)
    relation_aliases: list[str] = Field(min_length=1)
    right_aliases: list[str] = Field(min_length=1)
    required_value_aliases: list[str] = Field(default_factory=list)
    context_aliases: list[str] = Field(default_factory=list)
    max_token_distance: int = Field(default=24, ge=1, le=48)
    value_max_token_distance: int = Field(default=8, ge=1, le=16)
    context_max_token_distance: int = Field(default=64, ge=1, le=96)

    @field_validator(
        "left_aliases", "relation_aliases", "right_aliases", "required_value_aliases", "context_aliases",
        mode="before",
    )
    @classmethod
    def _validate_aliases(cls, value: object, info: Any) -> list[str]:
        if info.field_name in {"required_value_aliases", "context_aliases"} and value in (None, []):
            return []
        return _non_empty_aliases(value, field_name=info.field_name or "aliases")


class SemanticRelationGroupV22(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    variants: list[SemanticRelationVariantV22] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class DiagnosisSemanticV22Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["diagnosis-semantic-v2.2"]
    case_id: str = Field(min_length=1)
    required_concepts: list[SemanticConceptGroupV22] = Field(min_length=1)
    required_relations: list[SemanticRelationGroupV22] = Field(min_length=1)
    forbidden_relations: list[SemanticRelationGroupV22] = Field(default_factory=list)

    @field_validator("case_id")
    @classmethod
    def _trim_case_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("case_id must not be blank")
        return value

    @model_validator(mode="after")
    def _unique_dimension_names(self) -> DiagnosisSemanticV22Spec:
        names = [group.name for group in self.required_concepts]
        names.extend(group.name for group in self.required_relations)
        names.extend(group.name for group in self.forbidden_relations)
        if len(set(names)) != len(names):
            raise ValueError("semantic dimension names must be unique within a case")
        return self


class DiagnosisV22Input(BaseModel):
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
    def from_e2e_record(cls, record: Mapping[str, object]) -> DiagnosisV22Input:
        raw_candidates = record.get("diagnosis_candidates")
        candidates = (
            [dict(item) for item in raw_candidates if isinstance(item, Mapping)]
            if isinstance(raw_candidates, list) else []
        )
        raw_recall = record.get("evidence_target_recall", 0.0)
        raw_rejected = record.get("rejected_evidence_count", 0)
        raw_summary = record.get("root_cause_summary")
        return cls(
            case_id=str(record.get("case_id", "")),
            agent_completed=bool(record.get("diagnosis_completed", False)),
            diagnosis_status_match=bool(record.get("diagnosis_status_match", False)),
            issue_category_match=bool(record.get("issue_category_match", False)),
            expected_file_hit=bool(record.get("expected_file_hit", False)),
            evidence_target_hit_count=1 if isinstance(raw_recall, (int, float)) and float(raw_recall) > 0 else 0,
            invalid_rejected_evidence_count=raw_rejected if isinstance(raw_rejected, int) else 0,
            root_cause_summary=raw_summary if isinstance(raw_summary, str) else None,
            candidates=candidates,
        )


class DiagnosisV22Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["diagnosis-semantic-v2.2"] = "diagnosis-semantic-v2.2"
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


class DiagnosisV22Aggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["diagnosis-semantic-v2.2"] = "diagnosis-semantic-v2.2"
    cases_total: int
    cases_evaluated: int
    cases_passed: int
    cases_failed: int
    cases_insufficient_artifact: int
    pass_rate_over_evaluated: float | None
    mean_semantic_score_over_evaluated: float | None


class DiagnosisV22Regression(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["diagnosis-semantic-v2.2-regression"]
    regression_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    semantic_component_id: str = Field(min_length=1)
    bounded_input: dict[str, str] = Field(min_length=1)
    expected_v2_1: dict[str, object]
    expected_v2_2: dict[str, object]


def _alias_spans(text: str, aliases: Sequence[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for alias in aliases:
        normalized = _normalize(alias)
        if normalized:
            pattern = re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")
            spans.extend((match.start(), match.end()) for match in pattern.finditer(text))
    return sorted(set(spans))


def _token_count(value: str) -> int:
    return len(value.split())


def _span_token_distance(text: str, start: int, end: int) -> int:
    return _token_count(text[start:end])


def _has_intervening_numeric(text: str, start: int, end: int) -> bool:
    return bool(_NUMERIC_TOKEN.search(text[start:end]))


def _contains_alias(text: str, aliases: Sequence[str]) -> bool:
    return bool(_alias_spans(text, aliases))


def _bounded_pattern_hit(text: str, pattern: SemanticBoundedPatternV22) -> bool:
    anchors = _alias_spans(text, pattern.anchor_aliases)
    values = _alias_spans(text, pattern.value_aliases)
    return any(
        anchor_end <= value_start
        and _span_token_distance(text, anchor_end, value_start) <= pattern.max_token_distance
        and not _has_intervening_numeric(text, anchor_end, value_start)
        for _, anchor_end in anchors for value_start, _ in values
    )


def _concept_group_hit(text: str, group: SemanticConceptGroupV22) -> bool:
    return _contains_alias(text, group.aliases) or any(
        _bounded_pattern_hit(text, pattern) for pattern in group.bounded_patterns
    )


def _context_hit(text: str, aliases: Sequence[str], max_distance: int) -> bool:
    if not aliases:
        return True
    # Context anchors are finite and restricted to a small neighboring-clause
    # window.  This avoids turning context awareness into whole-document
    # semantic search.
    return _token_count(text) <= max_distance and bool(_alias_spans(text, aliases))


def _relation_variant_witness(
    clause: str, variant: SemanticRelationVariantV22, context_text: str,
) -> tuple[int, int] | None:
    left = _alias_spans(clause, variant.left_aliases)
    relations = _alias_spans(clause, variant.relation_aliases)
    right = _alias_spans(clause, variant.right_aliases)
    values = _alias_spans(clause, variant.required_value_aliases)
    if variant.context_aliases and not _context_hit(context_text, variant.context_aliases, variant.context_max_token_distance):
        return None
    for _, left_end in left:
        for relation_start, relation_end in relations:
            if relation_start < left_end:
                continue
            for right_start, _ in right:
                if right_start < relation_end:
                    continue
                if _span_token_distance(clause, left_end, right_start) > variant.max_token_distance:
                    continue
                if variant.required_value_aliases and not any(
                    left_end <= value_start <= relation_start
                    and _span_token_distance(clause, left_end, value_start) <= variant.value_max_token_distance
                    and not _has_intervening_numeric(clause, left_end, value_start)
                    for value_start, _ in values
                ):
                    continue
                return relation_start, relation_end
    return None


def _relation_group_hit(
    clauses: Sequence[str], group: SemanticRelationGroupV22, context_text: str = "",
) -> bool:
    del context_text
    for index, clause in enumerate(clauses):
        window = " ".join(clauses[max(0, index - 1): min(len(clauses), index + 2)])
        if any(
            _relation_variant_witness(clause, variant, window) is not None
            for variant in group.variants
        ):
            return True
    return False


def _negation_or_non_assertion(clause: str, relation_span: tuple[int, int]) -> bool:
    """Reject positive forbidden hits when the relation is negated or hypothetical."""
    relation_start, _ = relation_span
    prefix = clause[:relation_start]
    tokens = prefix.split()
    nearby = tokens[max(0, len(tokens) - 5):]
    # ``do not match`` and ``fails to bind`` are bounded negation scopes.
    if any(token in {"not", "never", "cannot", "fail"} for token in nearby):
        return True
    hypothetical = {
        "if", "would", "could", "should", "might", "may", "expected", "counterfactual",
        "after", "changing", "change", "rename", "renaming", "update", "updated", "correct", "corrected",
    }
    return any(token in hypothetical for token in nearby)


def _forbidden_group_hit(clauses: Sequence[str], group: SemanticRelationGroupV22, context_text: str) -> bool:
    for clause in clauses:
        for variant in group.variants:
            witness = _relation_variant_witness(clause, variant, context_text)
            if witness is not None and not _negation_or_non_assertion(clause, witness):
                return True
    return False


def _all_parts(value: DiagnosisV22Input) -> list[str]:
    parts: list[str] = []
    if value.root_cause_summary and value.root_cause_summary.strip():
        parts.append(value.root_cause_summary[:2000])
    for candidate in value.candidates[:3]:
        for key in ("title", "description", "recommended_fix"):
            item = candidate.get(key)
            if isinstance(item, str) and item.strip():
                parts.append(item[:2000])
    return parts


def _assertion_parts(value: DiagnosisV22Input) -> list[str]:
    parts: list[str] = []
    if value.root_cause_summary and value.root_cause_summary.strip():
        parts.append(value.root_cause_summary[:2000])
    for candidate in value.candidates[:3]:
        for key in ("title", "description"):
            item = candidate.get(key)
            if isinstance(item, str) and item.strip():
                parts.append(item[:2000])
    return parts


def _clauses(parts: Sequence[str]) -> list[str]:
    return [
        clause for part in parts
        for clause in (_normalize(item) for item in _SENTENCE_BOUNDARY.split(part))
        if clause
    ]


def evaluate_diagnosis_v22(value: DiagnosisV22Input, spec: DiagnosisSemanticV22Spec) -> DiagnosisV22Result:
    """Evaluate V2.2 concepts and directional relations deterministically."""
    if value.case_id != spec.case_id:
        raise ValueError(f"Diagnosis V2.2 input/spec case mismatch: {value.case_id!r} != {spec.case_id!r}")
    structural = {
        "agent_completed": value.agent_completed,
        "diagnosis_status_match": value.diagnosis_status_match,
        "issue_category_match": value.issue_category_match,
        "expected_source_file_hit": value.expected_file_hit,
        "evidence_target_hit": value.evidence_target_hit_count > 0,
        "no_invalid_rejected_evidence": value.invalid_rejected_evidence_count == 0,
    }
    parts = _all_parts(value)
    if not parts:
        return DiagnosisV22Result(
            case_id=value.case_id, evaluation_status="insufficient_artifact", semantic_pass=None,
            semantic_score=None, structural_conditions=structural, required_concept_hits={},
            required_relation_hits={}, contradiction_hits=[], failure_reasons=["semantic_text_not_archived"],
            evidence_limitation="The archived E2E result omits the bounded diagnosis summary and candidate text required for deterministic V2.2 replay.",
        )
    semantic_text = "\n".join(_normalize(part) for part in parts)
    clauses = _clauses(parts)
    assertion_clauses = _clauses(_assertion_parts(value))
    concept_hits = {group.name: _concept_group_hit(semantic_text, group) for group in spec.required_concepts}
    relation_hits = {group.name: _relation_group_hit(clauses, group, semantic_text) for group in spec.required_relations}
    contradictions = [
        group.name for group in spec.forbidden_relations
        if _forbidden_group_hit(assertion_clauses, group, "\n".join(_normalize(part) for part in _assertion_parts(value)))
    ]
    components = [*structural.values(), *concept_hits.values(), *relation_hits.values(), not contradictions]
    passed = all(components)
    score = round(sum(components) / len(components), 4) if components else 0.0
    failures = [name for name, hit in structural.items() if not hit]
    failures.extend(f"missing_concept:{name}" for name, hit in concept_hits.items() if not hit)
    failures.extend(f"missing_relation:{name}" for name, hit in relation_hits.items() if not hit)
    failures.extend(f"contradiction:{name}" for name in contradictions)
    return DiagnosisV22Result(
        case_id=value.case_id, evaluation_status="evaluated", semantic_pass=passed, semantic_score=score,
        structural_conditions=structural, required_concept_hits=concept_hits,
        required_relation_hits=relation_hits, contradiction_hits=contradictions, failure_reasons=failures,
    )


def aggregate_diagnosis_v22(results: Sequence[DiagnosisV22Result]) -> DiagnosisV22Aggregate:
    evaluated = [result for result in results if result.evaluation_status == "evaluated"]
    passed = sum(result.semantic_pass is True for result in evaluated)
    scores = [result.semantic_score for result in evaluated if result.semantic_score is not None]
    return DiagnosisV22Aggregate(
        cases_total=len(results), cases_evaluated=len(evaluated), cases_passed=passed,
        cases_failed=len(evaluated) - passed, cases_insufficient_artifact=len(results) - len(evaluated),
        pass_rate_over_evaluated=round(passed / len(evaluated), 4) if evaluated else None,
        mean_semantic_score_over_evaluated=round(statistics.mean(scores), 4) if scores else None,
    )


def load_diagnosis_v22_specs(path: Path) -> list[DiagnosisSemanticV22Spec]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DiagnosisV22ManifestError(f"cannot read Diagnosis V2.2 metadata {path}: {exc}") from exc
    specs: list[DiagnosisSemanticV22Spec] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            spec = DiagnosisSemanticV22Spec.model_validate_json(raw_line)
        except (ValidationError, ValueError) as exc:
            raise DiagnosisV22ManifestError(f"invalid Diagnosis V2.2 metadata at line {line_number}: {exc}") from exc
        if spec.case_id in seen:
            raise DiagnosisV22ManifestError(f"duplicate Diagnosis V2.2 case_id {spec.case_id!r}")
        seen.add(spec.case_id)
        specs.append(spec)
    if not specs:
        raise DiagnosisV22ManifestError(f"Diagnosis V2.2 metadata contains no cases: {path}")
    return specs


def load_diagnosis_v22_regressions(path: Path) -> list[DiagnosisV22Regression]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DiagnosisV22ManifestError(f"cannot read V2.2 regressions {path}: {exc}") from exc
    regressions: list[DiagnosisV22Regression] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            regression = DiagnosisV22Regression.model_validate_json(raw_line)
        except (ValidationError, ValueError) as exc:
            raise DiagnosisV22ManifestError(f"invalid V2.2 regression at line {line_number}: {exc}") from exc
        if regression.regression_id in seen:
            raise DiagnosisV22ManifestError(f"duplicate V2.2 regression_id {regression.regression_id!r}")
        seen.add(regression.regression_id)
        regressions.append(regression)
    if len(regressions) != 15:
        raise DiagnosisV22ManifestError(f"V2.2 regression corpus must contain 15 items, found {len(regressions)}")
    return regressions


def replay_frozen_e2e_summary_v22(
    summary: Mapping[str, object], specs: Sequence[DiagnosisSemanticV22Spec], v2_specs: Sequence[Any],
) -> dict[str, object]:
    """Replay frozen V1/V2.0 plus independent V2.2 without Agent/LLM calls."""
    from springfix_agent.benchmark.diagnosis_v2 import replay_frozen_e2e_summary
    from springfix_agent.benchmark.diagnosis_v21 import (
        DiagnosisV21Input,
        aggregate_diagnosis_v21,
        evaluate_diagnosis_v21,
        load_diagnosis_v21_specs,
    )

    v2_replay = replay_frozen_e2e_summary(summary, v2_specs)
    raw_cases = summary.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("frozen E2E summary does not contain a cases list")
    specs_by_id = {spec.case_id: spec for spec in specs}
    results: list[DiagnosisV22Result] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise ValueError("frozen E2E summary contains a non-object case")
        case_id = str(raw_case.get("case_id", ""))
        spec = specs_by_id.get(case_id)
        if spec is None:
            raise ValueError(f"missing Diagnosis V2.2 metadata for frozen case {case_id!r}")
        results.append(evaluate_diagnosis_v22(DiagnosisV22Input.from_e2e_record(raw_case), spec))
    # V2.1 is deliberately replayed unchanged for comparison and compatibility.
    v21_metadata = Path(__file__).resolve().parents[3] / "benchmark" / "dev_semantic_diagnosis_v2_1.jsonl"
    v21_specs = load_diagnosis_v21_specs(v21_metadata)
    v21_results = []
    v21_by_id = {spec.case_id: spec for spec in v21_specs}
    for raw_case in raw_cases:
        if isinstance(raw_case, Mapping):
            v21_results.append(evaluate_diagnosis_v21(DiagnosisV21Input.from_e2e_record(raw_case), v21_by_id[str(raw_case.get("case_id", ""))]))
    return {
        "schema_version": V22_REPLAY_SCHEMA_VERSION,
        "source_run_id": str(summary.get("run_id", "unknown")),
        "agent_rerun": False,
        "new_llm_calls": 0,
        "diagnosis_v1": v2_replay["diagnosis_v1"],
        "diagnosis_v2_0": v2_replay["diagnosis_v2"],
        "diagnosis_v2_1": {"aggregate": aggregate_diagnosis_v21(v21_results).model_dump(), "cases": [result.model_dump() for result in v21_results]},
        "diagnosis_v2_2": {"aggregate": aggregate_diagnosis_v22(results).model_dump(), "cases": [result.model_dump() for result in results]},
    }


def load_frozen_summary(path: Path) -> dict[str, object]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read frozen E2E summary {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"frozen E2E summary must be a JSON object: {path}")
    return payload
