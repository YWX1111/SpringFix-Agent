"""Retrieval evaluation script for M3 multi-channel retrieval.

Runs Baseline, BM25, and Hybrid retrieval against a gold-standard
fixture set and computes deterministic metrics:

    - Recall@1, Recall@3, Recall@5
    - MRR@10
    - Per-case ranking diagnostics (Top-5 per channel)
    - Symbol channel activation diagnostics
    - Development / Holdout split metrics

Supports limited parameter comparison for RRF k and symbol weight.

Does NOT use LLM. All results come from real execution.
Retrieval metrics are NOT Agent accuracy.
BM25 is lexical (keyword) retrieval, NOT semantic search.
Hybrid improves Top-K recall; Top-1 improvement depends on holdout data.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import math
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = (
    PROJECT_ROOT / "tests" / "fixtures" / "retrieval"
    / "benchmark" / "retrieval_cases.jsonl"
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))  # noqa: E402

from springfix_agent.retrieval.baseline import BaselineLexicalRetriever  # noqa: E402
from springfix_agent.retrieval.bm25 import BM25Retriever  # noqa: E402
from springfix_agent.retrieval.chunker import chunk_repository  # noqa: E402
from springfix_agent.retrieval.fusion import (  # noqa: E402
    DEFAULT_RRF_K,
    DEFAULT_WEIGHT_BASELINE,
    DEFAULT_WEIGHT_BM25,
    reciprocal_rank_fusion,
)
from springfix_agent.retrieval.query_builder import build_query  # noqa: E402
from springfix_agent.retrieval.symbol import SymbolRetriever  # noqa: E402

TOP_K = 5

# Pre-declared parameter grid (limited, no auto-search).
RRF_K_VALUES = (10, 20, 40, 60)
SYMBOL_WEIGHT_VALUES = (1.0, 1.25, 1.5)


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _files_in_hits(hits: list[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for h in hits:
        f = h.chunk.file  # type: ignore[attr-defined]
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


def _recall_at_k(expected_files: list[str], hits: list[object], k: int) -> float:
    if not expected_files:
        return 1.0
    retrieved_files = set(_files_in_hits(hits[:k]))
    found = sum(1 for f in expected_files if f in retrieved_files)
    return found / len(expected_files)


def _mrr_at_n(expected_files: list[str], hits: list[object], n: int = 10) -> float:
    if not expected_files:
        return 1.0
    expected_set = set(expected_files)
    for i, h in enumerate(hits[:n]):
        if h.chunk.file in expected_set:  # type: ignore[attr-defined]
            return 1.0 / (i + 1)
    return 0.0


def _first_relevant_rank(expected_files: list[str], hits: list[object]) -> int:
    """Return 0-based rank of first relevant hit, or -1 if none."""
    expected_set = set(expected_files)
    for i, h in enumerate(hits):
        if h.chunk.file in expected_set:  # type: ignore[attr-defined]
            return i
    return -1


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(math.ceil(0.95 * len(s))) - 1
    return s[max(0, idx)]


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------

def _load_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _make_state(case: dict[str, object]) -> dict[str, object]:
    """Build an AgentState-like dict from case data.

    Uses issue_analysis (if present) to populate LLM-derived symbols,
    and error_log (if present) for stack trace extraction.

    IMPORTANT: expected_symbols is NEVER used here — it is the gold
    standard for evaluation, not an input to the retrieval pipeline.
    """
    issue_analysis_raw = case.get("issue_analysis")
    issue_analysis: dict[str, object] = (
        dict(issue_analysis_raw)  # type: ignore[arg-type]
        if isinstance(issue_analysis_raw, dict) else {}
    )

    return {
        "issue_description": case.get("query", ""),
        "error_log": case.get("error_log"),
        "issue_analysis": issue_analysis,
        "investigation_plan": {},
        "extracted_symbols": [],
    }


# ---------------------------------------------------------------------------
# Channel runners
# ---------------------------------------------------------------------------

def _run_baseline(
    repo_path: Path, query: str, top_k: int,
) -> tuple[list[object], float]:
    retriever = BaselineLexicalRetriever()
    hits, ms = retriever.search(repo_path, query, top_k=top_k)
    return hits, float(ms)


def _run_bm25_only(
    repo_path: Path, state: dict[str, object], top_k: int,
) -> tuple[list[object], float, float]:
    chunks, _, _ = chunk_repository(repo_path)
    bm25 = BM25Retriever(chunks)
    build_ms = float(bm25.build_duration_ms)

    rq = build_query(state)
    t0 = time.perf_counter()
    hits, _ = bm25.search(rq.normalized_terms, top_k=top_k)
    query_ms = (time.perf_counter() - t0) * 1000
    return hits, query_ms, build_ms


def _run_hybrid_with_params(
    repo_path: Path,
    state: dict[str, object],
    top_k: int,
    rrf_k: int = DEFAULT_RRF_K,
    symbol_weight: float = 1.5,
) -> tuple[list[object], float, float, dict[str, object]]:
    """Run hybrid with custom params.

    Returns (hits, total_ms, build_ms, symbol_diag).
    symbol_diag contains activation info for diagnostics.
    """
    t0 = time.perf_counter()

    # Build query (uses issue_analysis.extracted_symbols from state).
    query = build_query(state)

    # Chunk.
    chunks, _, _ = chunk_repository(repo_path)
    bm25 = BM25Retriever(chunks)
    build_ms = float(bm25.build_duration_ms)

    # Baseline.
    baseline_query = (
        " ".join(query.normalized_terms)
        if query.normalized_terms else query.raw_text
    )
    baseline = BaselineLexicalRetriever()
    baseline_hits, _ = baseline.search(repo_path, baseline_query, top_k=top_k)

    # BM25.
    bm25_hits: list[object] = []
    with contextlib.suppress(Exception):
        bm25_hits, _ = bm25.search(query.normalized_terms, top_k=top_k)

    # Symbol (uses query.exact_symbols from build_query, NOT expected_symbols).
    symbol = SymbolRetriever()
    symbol_hits, _ = symbol.search(repo_path, query.exact_symbols, top_k=top_k)

    symbol_diag: dict[str, object] = {
        "activated": len(query.exact_symbols) > 0,
        "input_symbols": query.exact_symbols[:20],
        "symbol_hit_count": len(symbol_hits),
    }

    # Fuse.
    channels: dict[str, list[object]] = {}
    if baseline_hits:
        channels["baseline"] = baseline_hits
    if bm25_hits:
        channels["bm25"] = bm25_hits
    if symbol_hits:
        channels["symbol"] = symbol_hits

    weights = {
        "baseline": DEFAULT_WEIGHT_BASELINE,
        "bm25": DEFAULT_WEIGHT_BM25,
        "symbol": symbol_weight,
    }
    fused, _ = reciprocal_rank_fusion(
        channels, k=rrf_k, weights=weights, top_k=top_k,  # type: ignore[arg-type]
    )
    if not fused and baseline_hits:
        fused = baseline_hits[:top_k]  # type: ignore[assignment]

    total_ms = (time.perf_counter() - t0) * 1000
    return fused, total_ms, build_ms, symbol_diag


# ---------------------------------------------------------------------------
# Per-case ranking diagnostics
# ---------------------------------------------------------------------------

def _hit_detail(hit: object) -> dict[str, object]:
    """Extract diagnostic info from a RetrievalHit."""
    c = hit.chunk  # type: ignore[attr-defined]
    return {
        "chunk_id": c.chunk_id,
        "file": c.file,
        "symbol_name": c.symbol_name,
        "line_range": [c.start_line, c.end_line],
        "chunk_type": c.chunk_type,
        "sources": getattr(hit, "sources", []),
        "source_ranks": getattr(hit, "source_ranks", {}),
        "fused_score": round(getattr(hit, "fused_score", 0.0), 6),
        "matched_terms": getattr(hit, "matched_terms", [])[:10],
    }


def _channel_diagnostics(
    hits: list[object], expected_files: list[str],
) -> dict[str, object]:
    expected_set = set(expected_files)
    top5: list[dict[str, object]] = []
    first_relevant = -1
    for i, h in enumerate(hits[:TOP_K]):
        detail = _hit_detail(h)
        if h.chunk.file in expected_set and first_relevant < 0:  # type: ignore[attr-defined]
            first_relevant = i
        top5.append(detail)
    return {"top5": top5, "first_relevant_rank": first_relevant}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _eval_case(
    case: dict[str, object],
    rrf_k: int = DEFAULT_RRF_K,
    symbol_weight: float = 1.5,
) -> dict[str, object]:
    case_id = str(case["case_id"])
    repo_rel = str(case["repository"])
    query_text = str(case["query"])
    expected_files = list(case.get("expected_files", []))
    split = str(case.get("split", "development"))

    repo_path = (PROJECT_ROOT / repo_rel).resolve()
    if not repo_path.is_dir():
        return {"case_id": case_id, "split": split, "error": f"repo not found: {repo_path}"}

    state = _make_state(case)
    results: dict[str, object] = {"case_id": case_id, "split": split}

    # Record query terms for diagnostics.
    rq = build_query(state)
    results["query_terms"] = rq.normalized_terms[:20]
    results["exact_symbols"] = rq.exact_symbols[:20]

    # Baseline.
    try:
        bl_hits, bl_ms = _run_baseline(repo_path, query_text, TOP_K)
        results["baseline"] = {
            "recall@1": _recall_at_k(expected_files, bl_hits, 1),
            "recall@3": _recall_at_k(expected_files, bl_hits, 3),
            "recall@5": _recall_at_k(expected_files, bl_hits, 5),
            "mrr@10": _mrr_at_n(expected_files, bl_hits, 10),
            "query_ms": round(bl_ms, 3),
            "hits": len(bl_hits),
            "files": _files_in_hits(bl_hits)[:10],
            "diagnostics": _channel_diagnostics(bl_hits, expected_files),
        }
    except Exception as e:  # noqa: BLE001
        results["baseline"] = {"error": f"{type(e).__name__}: {e}"}

    # BM25.
    try:
        bm_hits, bm_ms, bm_build = _run_bm25_only(repo_path, state, TOP_K)
        results["bm25"] = {
            "recall@1": _recall_at_k(expected_files, bm_hits, 1),
            "recall@3": _recall_at_k(expected_files, bm_hits, 3),
            "recall@5": _recall_at_k(expected_files, bm_hits, 5),
            "mrr@10": _mrr_at_n(expected_files, bm_hits, 10),
            "query_ms": round(bm_ms, 3),
            "build_ms": round(bm_build, 3),
            "hits": len(bm_hits),
            "files": _files_in_hits(bm_hits)[:10],
            "diagnostics": _channel_diagnostics(bm_hits, expected_files),
        }
    except Exception as e:  # noqa: BLE001
        results["bm25"] = {"error": f"{type(e).__name__}: {e}"}

    # Symbol (standalone diagnostics, uses build_query output, NOT expected_symbols).
    try:
        sym = SymbolRetriever()
        sym_hits, sym_ms = sym.search(repo_path, rq.exact_symbols, top_k=TOP_K)
        results["symbol"] = {
            "activated": len(rq.exact_symbols) > 0,
            "input_symbols": rq.exact_symbols[:20],
            "hits": len(sym_hits),
            "query_ms": round(sym_ms, 3),
            "diagnostics": _channel_diagnostics(sym_hits, expected_files),
        }
    except Exception as e:  # noqa: BLE001
        results["symbol"] = {"error": f"{type(e).__name__}: {e}"}

    # Hybrid.
    try:
        hy_hits, hy_ms, hy_build, sym_diag = _run_hybrid_with_params(
            repo_path, state, TOP_K, rrf_k=rrf_k, symbol_weight=symbol_weight,
        )
        results["hybrid"] = {
            "recall@1": _recall_at_k(expected_files, hy_hits, 1),
            "recall@3": _recall_at_k(expected_files, hy_hits, 3),
            "recall@5": _recall_at_k(expected_files, hy_hits, 5),
            "mrr@10": _mrr_at_n(expected_files, hy_hits, 10),
            "query_ms": round(hy_ms, 3),
            "build_ms": round(hy_build, 3),
            "hits": len(hy_hits),
            "files": _files_in_hits(hy_hits)[:10],
            "diagnostics": _channel_diagnostics(hy_hits, expected_files),
            "symbol_channel": sym_diag,
        }
    except Exception as e:  # noqa: BLE001
        results["hybrid"] = {"error": f"{type(e).__name__}: {e}"}

    return results


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(channel_results: list[dict[str, object]]) -> dict[str, object]:
    recall_1: list[float] = []
    recall_3: list[float] = []
    recall_5: list[float] = []
    mrr: list[float] = []
    query_ms: list[float] = []
    build_ms: list[float] = []

    for r in channel_results:
        if "error" in r:
            continue
        recall_1.append(float(r.get("recall@1", 0)))
        recall_3.append(float(r.get("recall@3", 0)))
        recall_5.append(float(r.get("recall@5", 0)))
        mrr.append(float(r.get("mrr@10", 0)))
        query_ms.append(float(r.get("query_ms", 0)))
        if "build_ms" in r:
            build_ms.append(float(r["build_ms"]))

    n = len(recall_1)
    small_sample = n < 10
    return {
        "cases_evaluated": n,
        "small_sample": small_sample,
        "recall@1": round(statistics.mean(recall_1), 4) if recall_1 else 0,
        "recall@3": round(statistics.mean(recall_3), 4) if recall_3 else 0,
        "recall@5": round(statistics.mean(recall_5), 4) if recall_5 else 0,
        "mrr@10": round(statistics.mean(mrr), 4) if mrr else 0,
        "mean_query_ms": round(statistics.mean(query_ms), 3) if query_ms else 0,
        "p95_query_ms": round(_p95(query_ms), 3) if query_ms else 0,
        "mean_build_ms": round(statistics.mean(build_ms), 3) if build_ms else 0,
    }


def _aggregate_by_split(
    case_results: list[dict[str, object]],
) -> dict[str, dict[str, dict[str, object]]]:
    """Aggregate metrics per (split, channel)."""
    splits: dict[str, dict[str, list[dict[str, object]]]] = {}
    for cr in case_results:
        sp = str(cr.get("split", "development"))
        splits.setdefault(sp, {"baseline": [], "bm25": [], "hybrid": []})
        for ch in ("baseline", "bm25", "hybrid"):
            splits[sp][ch].append(dict(cr.get(ch, {})))

    return {
        sp: {ch: _aggregate(data) for ch, data in ch_data.items()}
        for sp, ch_data in splits.items()
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _render_markdown(
    case_results: list[dict[str, object]],
    split_summary: dict[str, dict[str, dict[str, object]]],
    params: dict[str, object],
) -> str:
    lines: list[str] = []
    lines.append("# M3 Retrieval Evaluation Report")
    lines.append("")
    lines.append(f"- Cases: {len(case_results)}")
    lines.append(f"- Top-K: {TOP_K}")
    lines.append(f"- RRF k: {params.get('rrf_k', DEFAULT_RRF_K)}")
    lines.append(f"- Symbol weight: {params.get('symbol_weight', 1.5)}")
    lines.append(f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    for split_name in ("development", "holdout"):
        if split_name not in split_summary:
            continue
        lines.append(f"## {split_name.capitalize()} Metrics")
        lines.append("")
        s_data = split_summary[split_name]
        lines.append("| Channel | Recall@1 | Recall@3 | Recall@5 | MRR@10 | Mean Query (ms) | P95 Query (ms) |")
        lines.append("|---------|----------|----------|----------|--------|-----------------|----------------|")
        for ch_name in ("baseline", "bm25", "hybrid"):
            s = s_data.get(ch_name, {})
            small = " *" if s.get("small_sample") else ""
            lines.append(
                f"| {ch_name}{small} "
                f"| {s.get('recall@1', 0):.4f} "
                f"| {s.get('recall@3', 0):.4f} "
                f"| {s.get('recall@5', 0):.4f} "
                f"| {s.get('mrr@10', 0):.4f} "
                f"| {s.get('mean_query_ms', 0):.3f} "
                f"| {s.get('p95_query_ms', 0):.3f} |"
            )
        lines.append("")

    lines.append("## Per-Case Details")
    lines.append("")
    for cr in case_results:
        cid = cr.get("case_id", "?")
        sp = cr.get("split", "")
        lines.append(f"### {cid} ({sp})")
        lines.append("")
        if "error" in cr:
            lines.append(f"- ERROR: {cr['error']}")
            lines.append("")
            continue

        # Query terms and exact symbols.
        qt = cr.get("query_terms", [])
        es = cr.get("exact_symbols", [])
        lines.append(f"- query_terms: {qt[:10]}")
        lines.append(f"- exact_symbols: {es[:10]}")
        lines.append("")

        for ch_name in ("baseline", "bm25", "symbol", "hybrid"):
            ch = cr.get(ch_name, {})
            if "error" in ch:
                lines.append(f"- **{ch_name}**: ERROR: {ch['error']}")
                continue

            # Symbol channel has different structure.
            if ch_name == "symbol":
                activated = ch.get("activated", False)
                sym_hits = ch.get("hits", 0)
                lines.append(
                    f"- **symbol**: activated={activated}, "
                    f"hits={sym_hits}, "
                    f"input={ch.get('input_symbols', [])[:5]}"
                )
                diag = ch.get("diagnostics", {})
                first_rel = diag.get("first_relevant_rank", -1)
                lines.append(f"  - first_relevant_rank: {first_rel}")
                for rank_i, detail in enumerate(diag.get("top5", [])[:5]):
                    lines.append(
                        f"  - [{rank_i}] {detail.get('file', '?')} "
                        f"L{detail.get('line_range', [0,0])[0]}-{detail.get('line_range', [0,0])[1]} "
                        f"({detail.get('chunk_type', '?')}, "
                        f"score={detail.get('fused_score', 0):.4f}, "
                        f"sources={detail.get('sources', [])})"
                    )
                continue

            if "recall@1" not in ch:
                continue
            lines.append(
                f"- **{ch_name}**: "
                f"R@1={ch.get('recall@1', 0):.2f} "
                f"R@3={ch.get('recall@3', 0):.2f} "
                f"R@5={ch.get('recall@5', 0):.2f} "
                f"MRR={ch.get('mrr@10', 0):.2f} "
                f"({ch.get('query_ms', 0):.3f}ms, {ch.get('hits', 0)} hits)"
            )
            # Symbol channel info in hybrid.
            if ch_name == "hybrid":
                sc = ch.get("symbol_channel", {})
                lines.append(
                    f"  - symbol_activated={sc.get('activated', False)}, "
                    f"symbol_hits={sc.get('symbol_hit_count', 0)}"
                )
            diag = ch.get("diagnostics", {})
            first_rel = diag.get("first_relevant_rank", -1)
            lines.append(f"  - first_relevant_rank: {first_rel}")
            for rank_i, detail in enumerate(diag.get("top5", [])[:5]):
                lines.append(
                    f"  - [{rank_i}] {detail.get('file', '?')} "
                    f"L{detail.get('line_range', [0,0])[0]}-{detail.get('line_range', [0,0])[1]} "
                    f"({detail.get('chunk_type', '?')}, "
                    f"score={detail.get('fused_score', 0):.4f}, "
                    f"sources={detail.get('sources', [])})"
                )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- BM25 is **lexical (keyword) retrieval**, not semantic search.")
    lines.append("- Hybrid improves Top-K recall completeness; "
                 "Top-1 improvement depends on holdout data.")
    lines.append("- Symbol channel is activated by `issue_analysis.extracted_symbols` "
                 "from the query builder, NOT by expected_symbols (gold standard).")
    lines.append("- Retrieval benchmark does NOT measure Agent root-cause accuracy.")
    lines.append("- Development data used for parameter selection; "
                 "holdout data used for limited validation only.")
    lines.append("- Sample size is small; P95 values are indicative, "
                 "not production performance claims.")
    if any(
        s.get("small_sample") for sp in split_summary.values()
        for s in sp.values()
    ):
        lines.append("- * = small sample (<10 cases), P95 is indicative only.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parameter comparison
# ---------------------------------------------------------------------------

def _run_parameter_comparison(
    cases: list[dict[str, object]],
) -> dict[str, object]:
    """Run limited parameter grid on development cases only."""
    dev_cases = [c for c in cases if c.get("split", "development") == "development"]
    if not dev_cases:
        return {"error": "no development cases"}

    print(f"\n=== Parameter Comparison ({len(dev_cases)} dev cases) ===")
    print(f"RRF k: {RRF_K_VALUES}")
    print(f"Symbol weight: {SYMBOL_WEIGHT_VALUES}")
    print()

    results: list[dict[str, object]] = []
    for rrf_k, sym_w in itertools.product(RRF_K_VALUES, SYMBOL_WEIGHT_VALUES):
        hy_r1: list[float] = []
        hy_r3: list[float] = []
        hy_mrr: list[float] = []
        sym_activated_count = 0
        for case in dev_cases:
            cr = _eval_case(case, rrf_k=rrf_k, symbol_weight=sym_w)
            hy = cr.get("hybrid", {})
            if "error" not in hy and "recall@1" in hy:
                hy_r1.append(float(hy["recall@1"]))
                hy_r3.append(float(hy["recall@3"]))
                hy_mrr.append(float(hy["mrr@10"]))
            # Count symbol activations.
            sc = hy.get("symbol_channel", {}) if isinstance(hy, dict) else {}
            if sc.get("activated"):
                sym_activated_count += 1

        entry = {
            "rrf_k": rrf_k,
            "symbol_weight": sym_w,
            "hybrid_r@1": round(statistics.mean(hy_r1), 4) if hy_r1 else 0,
            "hybrid_r@3": round(statistics.mean(hy_r3), 4) if hy_r3 else 0,
            "hybrid_mrr@10": round(statistics.mean(hy_mrr), 4) if hy_mrr else 0,
            "symbol_activated_cases": sym_activated_count,
        }
        results.append(entry)
        print(
            f"  k={rrf_k:>3} w_sym={sym_w:.2f}  "
            f"R@1={entry['hybrid_r@1']:.4f}  "
            f"R@3={entry['hybrid_r@3']:.4f}  "
            f"MRR={entry['hybrid_mrr@10']:.4f}  "
            f"sym_active={sym_activated_count}"
        )

    # Select best by priority: R@3, then MRR@10, then R@1.
    best = max(results, key=lambda r: (
        r["hybrid_r@3"],  # type: ignore[index]
        r["hybrid_mrr@10"],  # type: ignore[index]
        r["hybrid_r@1"],  # type: ignore[index]
    ))
    print(f"\n  Best: k={best['rrf_k']}, w_sym={best['symbol_weight']}")
    print(f"        R@1={best['hybrid_r@1']:.4f}  R@3={best['hybrid_r@3']:.4f}  "
          f"MRR={best['hybrid_mrr@10']:.4f}")

    return {"grid": results, "best": best}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    cases = _load_cases()
    n_dev = sum(1 for c in cases if c.get("split", "development") == "development")
    n_hold = sum(1 for c in cases if c.get("split") == "holdout")
    print(f"Loaded {len(cases)} evaluation cases ({n_dev} dev, {n_hold} holdout)")
    print(f"Top-K: {TOP_K}, RRF k: {DEFAULT_RRF_K}")
    print()

    # 1. Run default parameters on all cases.
    case_results: list[dict[str, object]] = []
    for i, case in enumerate(cases, start=1):
        cid = case.get("case_id", f"case-{i}")
        sp = case.get("split", "development")
        print(f"[{i}/{len(cases)}] {cid} ({sp}) ...", end=" ", flush=True)
        result = _eval_case(case)
        case_results.append(result)
        if "error" in result:
            print(f"ERROR: {result['error']}")
        else:
            bl = result.get("baseline", {})
            bm = result.get("bm25", {})
            hy = result.get("hybrid", {})
            sym = result.get("symbol", {})
            bl_r1 = bl.get("recall@1", 0) if isinstance(bl, dict) and "error" not in bl else -1
            bm_r1 = bm.get("recall@1", 0) if isinstance(bm, dict) and "error" not in bm else -1
            hy_r1 = hy.get("recall@1", 0) if isinstance(hy, dict) and "error" not in hy else -1
            sym_active = "Y" if isinstance(sym, dict) and sym.get("activated") else "N"
            print(f"BL R@1={bl_r1:.2f}  BM25 R@1={bm_r1:.2f}  "
                  f"Hybrid R@1={hy_r1:.2f}  Sym={sym_active}")

    print()

    # 2. Aggregate by split.
    split_summary = _aggregate_by_split(case_results)

    for split_name in ("development", "holdout"):
        if split_name not in split_summary:
            continue
        print(f"=== {split_name.capitalize()} Summary ===")
        print(f"{'Channel':<10} {'R@1':>8} {'R@3':>8} {'R@5':>8} {'MRR@10':>8} "
              f"{'Avg Q(ms)':>10} {'P95 Q(ms)':>10}")
        for ch_name in ("baseline", "bm25", "hybrid"):
            s = split_summary[split_name].get(ch_name, {})
            print(
                f"{ch_name:<10} "
                f"{s.get('recall@1', 0):>8.4f} "
                f"{s.get('recall@3', 0):>8.4f} "
                f"{s.get('recall@5', 0):>8.4f} "
                f"{s.get('mrr@10', 0):>8.4f} "
                f"{s.get('mean_query_ms', 0):>10.3f} "
                f"{s.get('p95_query_ms', 0):>10.3f}"
            )
        print()

    # 3. Parameter comparison (development only).
    param_results = _run_parameter_comparison(cases)

    # 4. Run holdout with best parameters.
    best = param_results.get("best", {})
    best_k = int(best.get("rrf_k", DEFAULT_RRF_K))
    best_w = float(best.get("symbol_weight", 1.5))

    holdout_cases = [c for c in cases if c.get("split") == "holdout"]
    if holdout_cases:
        print(f"\n=== Holdout Validation (k={best_k}, w_sym={best_w}) ===")
        holdout_results: list[dict[str, object]] = []
        for case in holdout_cases:
            cr = _eval_case(case, rrf_k=best_k, symbol_weight=best_w)
            holdout_results.append(cr)
            cid = cr.get("case_id", "?")
            hy = cr.get("hybrid", {})
            hy_r1 = hy.get("recall@1", 0) if isinstance(hy, dict) and "error" not in hy else -1
            sym = cr.get("symbol", {})
            sym_active = "Y" if isinstance(sym, dict) and sym.get("activated") else "N"
            print(f"  {cid}: Hybrid R@1={hy_r1:.2f}  Sym={sym_active}")

        holdout_agg = _aggregate_by_split(holdout_results)
        if "holdout" in holdout_agg:
            print("\n=== Holdout Final ===")
            for ch_name in ("baseline", "bm25", "hybrid"):
                s = holdout_agg["holdout"].get(ch_name, {})
                print(
                    f"  {ch_name:<10} "
                    f"R@1={s.get('recall@1', 0):.4f}  "
                    f"R@3={s.get('recall@3', 0):.4f}  "
                    f"R@5={s.get('recall@5', 0):.4f}  "
                    f"MRR={s.get('mrr@10', 0):.4f}"
                )
        # Update split_summary with holdout validation results.
        split_summary["holdout_validated"] = holdout_agg.get("holdout", {})

    # 5. Write outputs.
    output_dir = PROJECT_ROOT / "artifacts" / "retrieval-eval"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_output = {
        "cases": case_results,
        "split_summary": split_summary,
        "parameter_comparison": param_results,
        "frozen_params": {"rrf_k": best_k, "symbol_weight": best_w},
        "config": {"top_k": TOP_K, "cases_file": "tests/fixtures/retrieval/benchmark/retrieval_cases.jsonl"},
    }
    json_path = output_dir / "metrics.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)
    print(f"\nJSON written to {json_path}")

    params_info = {"rrf_k": best_k, "symbol_weight": best_w}
    md = _render_markdown(case_results, split_summary, params_info)
    md_path = output_dir / "report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Markdown written to {md_path}")

    print()
    print("Retrieval metrics are NOT Agent accuracy.")
    print("BM25 is lexical retrieval, not semantic search.")
    print("Hybrid improves Top-K recall; Top-1 depends on holdout data.")


if __name__ == "__main__":
    main()
