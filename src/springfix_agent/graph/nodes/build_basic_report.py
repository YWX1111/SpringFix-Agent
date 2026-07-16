"""build_basic_report node: deterministic summary, no root-cause claims.

Renders a structured dict and a Markdown report from the AgentState.
The report explicitly disclaims that it is NOT a root-cause diagnosis;
that capability lands in M2 with LLM-backed RootCauseAnalyzer.
"""

from __future__ import annotations

from typing import Any

from springfix_agent.graph.state import AgentState

DISCLAIMER = (
    "当前报告由确定性代码检索流程生成,仅用于展示相关代码证据,"
    "不代表已经完成根因诊断。根因分析在 M2 阶段接入 LLM 后实现。"
)


def build_basic_report(state: AgentState) -> dict[str, Any]:
    """Produce a deterministic basic report. No LLM, no root-cause claims."""
    if not state["validation_ok"]:
        return _failed_report(state)

    return _success_report(state)


def _failed_report(state: AgentState) -> dict[str, Any]:
    errors = state.get("validation_errors", [])
    md_lines = [
        "# 诊断报告",
        "",
        f"- task_id: `{state['task_id']}`",
        "- status: **failed**",
        "",
        "## 校验错误",
        "",
    ]
    if errors:
        for e in errors:
            md_lines.append(f"- {e}")
    else:
        md_lines.append("- (未知错误)")
    md_lines.extend(["", f"> {DISCLAIMER}"])

    report: dict[str, object] = {
        "task_id": state["task_id"],
        "status": "failed",
        "validation_errors": errors,
        "disclaimer": DISCLAIMER,
    }
    return {
        "basic_report": report,
        "markdown_report": "\n".join(md_lines),
        "status": "failed",
    }


def _success_report(state: AgentState) -> dict[str, Any]:
    snippets_meta = [
        {
            "file": s["file"],
            "line_range": list(s["line_range"]),
            "score": s["score"],
            "symbols": s["symbols"],
        }
        for s in state["retrieved_snippets"]
    ]
    tool_calls_meta = [
        {
            "tool": tc["tool_name"],
            "node": tc["node"],
            "status": tc["status"],
            "duration_ms": tc["duration_ms"],
            "error": tc.get("error"),
        }
        for tc in state["tool_calls"]
    ]

    report: dict[str, object] = {
        "task_id": state["task_id"],
        "status": state["status"],
        "issue_description": state["issue_description"],
        "extracted_symbols": state["extracted_symbols"],
        "candidate_files": state["candidate_files"],
        "retrieved_snippets": snippets_meta,
        "tool_calls_summary": tool_calls_meta,
        "disclaimer": DISCLAIMER,
    }

    md_lines: list[str] = []
    md_lines.append("# 诊断报告")
    md_lines.append("")
    md_lines.append(f"> {DISCLAIMER}")
    md_lines.append("")
    md_lines.append("## 任务信息")
    md_lines.append(f"- task_id: `{state['task_id']}`")
    md_lines.append(f"- status: `{state['status']}`")
    md_lines.append("")
    md_lines.append("## 问题描述")
    md_lines.append(state["issue_description"])
    md_lines.append("")
    md_lines.append("## 提取到的符号")
    if state["extracted_symbols"]:
        for sym in state["extracted_symbols"]:
            md_lines.append(f"- `{sym}`")
    else:
        md_lines.append("(未提取到符合 Java 标识符特征的符号)")
    md_lines.append("")
    md_lines.append("## 候选文件")
    if state["candidate_files"]:
        for f in state["candidate_files"]:
            md_lines.append(f"- `{f}`")
    else:
        md_lines.append("(未通过符号检索到候选文件)")
    md_lines.append("")
    md_lines.append("## 检索到的代码片段")
    if state["retrieved_snippets"]:
        for s in state["retrieved_snippets"]:
            md_lines.append(
                f"### `{s['file']}` (行 {s['line_range'][0]}-{s['line_range'][1]}, "
                f"score {s['score']:.2f})"
            )
            md_lines.append("```java")
            md_lines.append(s["content"])
            md_lines.append("```")
            md_lines.append("")
    else:
        md_lines.append("(未检索到代码片段)")
    md_lines.append("## 工具调用记录")
    if state["tool_calls"]:
        for tc in state["tool_calls"]:
            md_lines.append(
                f"- `{tc['tool_name']}` (node: {tc['node']}): "
                f"{tc['status']} in {tc['duration_ms']}ms"
            )
            if tc.get("error"):
                md_lines.append(f"  - error: {tc['error']}")
    else:
        md_lines.append("(无工具调用)")
    md_lines.append("")
    md_lines.append("## 后续检查方向")
    md_lines.append("- 本报告不包含根因分析(根因推理在 M2 阶段接入 LLM 后实现)")
    md_lines.append("- 建议人工查看候选文件中的 `@Transactional` 等注解使用方式")
    md_lines.append("- 当前未运行 Maven 测试,无法验证事务是否真的失效")
    md_lines.append("- 检索基于词法评分,非语义检索;M3 阶段将接入 BM25 对比 Recall@K")

    return {
        "basic_report": report,
        "markdown_report": "\n".join(md_lines),
        "status": "completed",
    }
