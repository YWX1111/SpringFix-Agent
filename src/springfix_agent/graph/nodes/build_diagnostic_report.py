"""build_diagnostic_report node: deterministic template-driven report.

This node renders a structured JSON + Markdown report from the full
AgentState. It is purely deterministic (no LLM).

The report distinguishes three diagnosis statuses:

- ``complete``
- ``partial``
- ``insufficient_evidence``

When the status is not ``complete`` the report MUST NOT read as a
"root cause has been determined" statement.
"""

from __future__ import annotations

from typing import Any

from springfix_agent.graph.state import AgentState


def build_diagnostic_report(state: AgentState) -> dict[str, Any]:
    """Render JSON + Markdown report. Deterministic."""
    issue_analysis = dict(state.get("issue_analysis") or {})
    plan = dict(state.get("investigation_plan") or {})
    rca_raw = dict(state.get("root_cause_analysis") or {})
    snippets = list(state.get("retrieved_snippets") or [])
    candidate_files = list(state.get("candidate_files") or [])
    extracted_symbols = list(state.get("extracted_symbols") or [])
    warnings = list(state.get("warnings") or [])
    errors = list(state.get("errors") or [])

    diagnosis_status = str(rca_raw.get("diagnosis_status", "insufficient_evidence"))
    if diagnosis_status not in ("complete", "partial", "insufficient_evidence"):
        diagnosis_status = "insufficient_evidence"

    # Layered evidence audit: full records live only in the trace store;
    # the user-facing report exposes only counts and short warnings.
    raw_rejected = rca_raw.get("rejected_evidence")
    rejected_evidence: list[object] = list(raw_rejected) if isinstance(raw_rejected, list) else []
    rejected_evidence_count = len(rejected_evidence)
    raw_candidates = rca_raw.get("candidates")
    raw_missing = rca_raw.get("missing_information")
    rca_public: dict[str, object] = {
        "diagnosis_status": rca_raw.get("diagnosis_status", diagnosis_status),
        "summary": rca_raw.get("summary", ""),
        "candidates": list(raw_candidates) if isinstance(raw_candidates, list) else [],
        "missing_information": list(raw_missing) if isinstance(raw_missing, list) else [],
        "rejected_evidence_count": rejected_evidence_count,
    }

    snippets_meta = [
        {
            "file": s["file"],
            "line_range": list(s["line_range"]),
            "score": s["score"],
            "symbols": list(s.get("symbols", [])),
        }
        for s in snippets
    ]

    tool_calls_summary = [
        {
            "tool": tc["tool_name"],
            "node": tc["node"],
            "status": tc["status"],
            "duration_ms": tc["duration_ms"],
            "error": tc.get("error"),
        }
        for tc in state.get("tool_calls", []) or []
    ]
    llm_calls_summary = [
        {
            "node": lc["node"],
            "provider": lc["provider"],
            "model": lc["model"],
            "status": lc["status"],
            "duration_ms": lc["duration_ms"],
            "prompt_chars": lc["prompt_chars"],
            "response_chars": lc["response_chars"],
            "input_tokens": lc["input_tokens"],
            "output_tokens": lc["output_tokens"],
            "error_message": lc.get("error_message"),
        }
        for lc in state.get("llm_calls", []) or []
    ]

    json_report: dict[str, Any] = {
        "task_id": state["task_id"],
        "status": state["status"],
        "diagnosis_status": diagnosis_status,
        "issue_description": state["issue_description"],
        "issue_analysis": issue_analysis,
        "investigation_plan": plan,
        "extracted_symbols": extracted_symbols,
        "candidate_files": candidate_files,
        "retrieved_snippets": snippets_meta,
        "root_cause_analysis": rca_public,
        "warnings": warnings,
        "errors": errors,
        "tool_calls_summary": tool_calls_summary,
        "llm_calls_summary": llm_calls_summary,
    }

    md_lines = _render_markdown(state, diagnosis_status, json_report)
    final_status = "failed" if not state.get("validation_ok", True) else "completed"
    return {
        "diagnostic_report": json_report,
        "basic_report": json_report,
        "markdown_report": "\n".join(md_lines),
        "status": final_status,
    }


def _render_markdown(state: AgentState, status: str, json_report: dict[str, Any]) -> list[str]:
    md: list[str] = []
    md.append("# 诊断报告")
    md.append("")
    md.append(f"- task_id: `{state['task_id']}`")
    md.append(f"- status: `{state['status']}`")
    md.append(f"- diagnosis_status: **{status}**")
    md.append("")

    if status == "insufficient_evidence":
        md.append("> 证据不足，未提出明确的根因诊断。以下是已收集到的线索，供人工研判。")
    elif status == "partial":
        md.append("> 证据部分充分，提出了候选根因但尚未形成完整诊断。")
    else:
        md.append("> 诊断完成。以下是基于检索证据得出的根因候选及修复建议。")
    md.append("")

    md.append("## 问题描述")
    md.append(state["issue_description"])
    md.append("")

    md.append("## 问题分类")
    issue_analysis = json_report.get("issue_analysis") or {}
    md.append(f"- issue_category: `{issue_analysis.get('issue_category', 'unknown')}`")
    md.append(f"- summary: {issue_analysis.get('summary', '(none)')}")
    symptoms = list(issue_analysis.get("symptoms") or [])
    if symptoms:
        md.append("- symptoms:")
        for s in symptoms[:10]:
            md.append(f"  - {s}")
    exception_types = list(issue_analysis.get("exception_types") or [])
    if exception_types:
        md.append("- exception_types:")
        for et in exception_types[:10]:
            md.append(f"  - `{et}`")
    md.append("")

    md.append("## 调查计划")
    plan = json_report.get("investigation_plan") or {}
    steps = list(plan.get("steps") or [])
    if steps:
        for step in steps[:6]:
            md.append(
                f"{step.get('step_id', '?')}. **{step.get('objective', '')}** "
                f"— {step.get('rationale', '')}"
            )
    else:
        md.append("(未生成调查计划)")
    md.append("")

    md.append("## 提取到的符号")
    extracted = list(json_report.get("extracted_symbols") or [])
    if extracted:
        for sym in extracted[:10]:
            md.append(f"- `{sym}`")
    else:
        md.append("(未提取到符合 Java 标识符特征的符号)")
    md.append("")

    md.append("## 检索到的代码片段")
    snippets = list(json_report.get("retrieved_snippets") or [])
    if snippets:
        for s in snippets:
            lr = list(s.get("line_range", [1, 1]))
            md.append(
                f"### `{s['file']}` (行 {lr[0]}-{lr[1]}, score {s.get('score', 0):.2f})"
            )
            md.append("```java")
            md.append(str(s.get("content", "")))
            md.append("```")
            md.append("")
    else:
        md.append("(未检索到代码片段)")

    md.append("## 根因候选")
    rca = json_report.get("root_cause_analysis") or {}
    # rca_public already excludes rejected_evidence full records
    _ = rca
    candidates = list(rca.get("candidates") or [])
    missing = list(rca.get("missing_information") or [])
    if candidates:
        for i, c in enumerate(candidates[:3], start=1):
            md.append(f"### 候选 {i}: {c.get('title', '(无标题)')}")
            md.append(f"- confidence: **{c.get('confidence', 'low')}**")
            md.append(f"- description: {c.get('description', '')}")
            evidence = list(c.get("evidence") or [])
            if evidence:
                md.append("- evidence:")
                for ev in evidence[:5]:
                    md.append(
                        f"  - `{ev.get('file')}` lines {ev.get('start_line')}-"
                        f"{ev.get('end_line')}: {ev.get('explanation', '')}"
                    )
            md.append(f"- recommended_fix: {c.get('recommended_fix', '')}")
            vsteps = list(c.get("verification_steps") or [])
            if vsteps:
                md.append("- verification_steps:")
                for vs in vsteps[:5]:
                    md.append(f"  - {vs}")
            md.append("")
    else:
        md.append("(未生成根因候选)")
        md.append("")
    if missing:
        md.append("## 缺失信息")
        for m in missing[:8]:
            md.append(f"- {m}")
        md.append("")

    md.append("## 工具调用记录")
    tool_calls = list(json_report.get("tool_calls_summary") or [])
    if tool_calls:
        for tc in tool_calls:
            md.append(
                f"- `{tc.get('tool')}` (node: {tc.get('node')}): "
                f"{tc.get('status')} in {tc.get('duration_ms')}ms"
            )
            if tc.get("error"):
                md.append(f"  - error: {tc['error']}")
    else:
        md.append("(无工具调用)")
    md.append("")

    md.append("## LLM 调用记录")
    llm_calls = list(json_report.get("llm_calls_summary") or [])
    if llm_calls:
        for lc in llm_calls:
            md.append(
                f"- node `{lc.get('node')}` ({lc.get('provider')}/{lc.get('model')}): "
                f"{lc.get('status')} in {lc.get('duration_ms')}ms "
                f"(prompt={lc.get('prompt_chars')}c, "
                f"response={lc.get('response_chars')}c, "
                f"in={lc.get('input_tokens')}, out={lc.get('output_tokens')})"
            )
            if lc.get("error_message"):
                md.append(f"  - error: {lc['error_message']}")
    else:
        md.append("(无 LLM 调用)")
    md.append("")

    md.append("## 警告")
    warnings_list = list(json_report.get("warnings") or [])
    if warnings_list:
        for w in warnings_list[:10]:
            md.append(f"- {w}")
    else:
        md.append("(无警告)")
    md.append("")

    md.append("## 后续检查方向")
    md.append("- 当前检索基于 M1 简单词法评分；M3 将接入 BM25 对比 Recall@K")
    md.append("- 当前不会修改或执行用户代码；自动修复留到阶段 3+")
    md.append("- 单个 Case 的诊断结果不代表整体准确率；完整评测留到 M4")
    md.append("")

    return md
