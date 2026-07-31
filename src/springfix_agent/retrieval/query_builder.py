"""Query builder: merges all available search signals into a RetrievalQuery.

Sources:
    - issue_description (original user text)
    - error_log exception types
    - IssueAnalysis.search_terms / spring_concepts / extracted_symbols
    - InvestigationPlan.steps[].search_terms / target_symbols
    - Deterministic symbol extraction
"""

from __future__ import annotations

import re
from typing import Any

from springfix_agent.retrieval.models import RetrievalQuery
from springfix_agent.retrieval.tokenizer import normalize_query_terms

MAX_QUERY_TERMS = 50
_EXCEPTION_CLASS_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*Exception)\b")
_ANNOTATION_RE = re.compile(r"@([A-Z][A-Za-z0-9_]*)")
_JAVA_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def build_query(state: dict[str, Any]) -> RetrievalQuery:
    """Build a structured RetrievalQuery from the current AgentState.

    Collects terms from all M2 sources, normalizes, de-duplicates,
    and enforces limits. Never trusts LLM-generated paths.
    """
    raw_terms: list[str] = []
    exact_symbols: list[str] = []
    exception_types: list[str] = []
    annotations: list[str] = []
    seen_raw: set[str] = set()

    def add_raw(term: str) -> None:
        t = term.strip()
        if not t or len(t) < 2:
            return
        if t in seen_raw:
            return
        seen_raw.add(t)
        raw_terms.append(t)

    # 1. issue_description — extract Java identifiers.
    issue_desc = str(state.get("issue_description", ""))
    for tok in _JAVA_IDENT_RE.findall(issue_desc):
        if len(tok) >= 3:
            add_raw(tok)
    # Also extract exception types from description.
    for m in _EXCEPTION_CLASS_RE.finditer(issue_desc):
        exc = m.group(1)
        if exc not in exception_types:
            exception_types.append(exc)
        add_raw(exc)

    # 2. error_log — extract exception class names.
    error_log = state.get("error_log")
    if isinstance(error_log, str) and error_log:
        for m in _EXCEPTION_CLASS_RE.finditer(error_log):
            exc = m.group(1)
            if exc not in exception_types:
                exception_types.append(exc)
            add_raw(exc)

    # 3. IssueAnalysis outputs.
    issue_analysis = state.get("issue_analysis") or {}
    if isinstance(issue_analysis, dict):
        for term in _safe_list(issue_analysis.get("search_terms")):
            add_raw(term)
        for concept in _safe_list(issue_analysis.get("spring_concepts")):
            add_raw(concept)
            ann_match = _ANNOTATION_RE.match(concept)
            if ann_match:
                ann = ann_match.group(1)
                if ann not in annotations:
                    annotations.append(ann)
        for sym in _safe_list(issue_analysis.get("extracted_symbols")):
            if sym not in exact_symbols:
                exact_symbols.append(sym)
            add_raw(sym)
        for exc in _safe_list(issue_analysis.get("exception_types")):
            if exc not in exception_types:
                exception_types.append(exc)
            add_raw(exc)

    # 4. InvestigationPlan outputs.
    plan = state.get("investigation_plan") or {}
    if isinstance(plan, dict):
        steps = plan.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                for term in _safe_list(step.get("search_terms")):
                    add_raw(term)
                for sym in _safe_list(step.get("target_symbols")):
                    if sym not in exact_symbols:
                        exact_symbols.append(sym)
                    add_raw(sym)

    # 5. Deterministic extracted_symbols (from explore_repository).
    for sym in _safe_list(state.get("extracted_symbols")):
        if sym not in exact_symbols:
            exact_symbols.append(sym)

    # Normalize all collected terms.
    normalized, discarded = normalize_query_terms(raw_terms, max_terms=MAX_QUERY_TERMS)

    # Add exception types as explicit tokens (lowered).
    for exc in exception_types:
        lowered = exc.lower()
        if lowered not in normalized:
            from springfix_agent.retrieval.tokenizer import tokenize_identifier
            for tok in tokenize_identifier(exc):
                if tok not in normalized and len(normalized) < MAX_QUERY_TERMS:
                    normalized.append(tok)

    # Cap exact_symbols.
    exact_symbols = exact_symbols[:20]
    exception_types = exception_types[:10]
    annotations = annotations[:10]

    return RetrievalQuery(
        raw_text=issue_desc,
        normalized_terms=normalized,
        exact_symbols=exact_symbols,
        exception_types=exception_types,
        annotations=annotations,
    )


def _safe_list(v: object) -> list[str]:
    """Safely extract a list of strings from a potentially unknown value."""
    if not isinstance(v, list):
        return []
    return [str(item) for item in v if isinstance(item, str) and item.strip()]


def query_terms_count(query: RetrievalQuery) -> tuple[int, int]:
    """Return (terms_used, terms_discarded) for diagnostics."""
    return len(query.normalized_terms), 0
