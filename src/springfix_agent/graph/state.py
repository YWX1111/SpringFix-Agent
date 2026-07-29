"""AgentState for M2 (LLM-assisted diagnostic graph).

M2 adds five new fields on top of M1:

- ``issue_analysis``      (IssueParser output)
- ``investigation_plan``  (TaskPlanner output)
- ``root_cause_analysis`` (RootCauseAnalyzer output)
- ``diagnostic_report``   (build_diagnostic_report output, replaces M1 basic_report)
- ``llm_calls``           (append-only LLM trace accumulator)
- ``warnings``            (append-only node-level warnings)

M1 fields that remain in active use:

- ``extracted_symbols`` is merged from deterministic + IssueParser output.
- ``project_tree_summary``, ``candidate_files``, ``retrieved_snippets``,
  ``retrieval_summary`` continue to flow through the existing tools.
- ``errors``, ``tool_calls``, ``node_timings`` continue to accumulate.

State volume limits (100 KB total, 10 snippets, 60 lines / 4000 chars
each, 500-char trace summaries) remain in force.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from springfix_agent.llm.trace import LLMCall
from springfix_agent.observability.tracer import NodeTiming
from springfix_agent.storage.models import TaskStatus
from springfix_agent.tools.base import ToolCall

MAX_SNIPPETS = 10
MAX_SNIPPET_LINES = 60
MAX_SNIPPET_CHARS = 4000
MAX_TRACE_SUMMARY_CHARS = 500
MAX_STATE_TOTAL_CHARS = 100_000


class RetrievedSnippet(TypedDict):
    """A code snippet retrieved from the repository, with truncation applied."""

    file: str
    line_range: tuple[int, int]
    content: str
    score: float
    symbols: list[str]


class AgentState(TypedDict):
    """M2 state shape. Append-reducer fields use ``Annotated[..., operator.add]``."""

    # Inputs (written once at task creation)
    task_id: str
    repository_path: str
    issue_description: str
    error_log: str | None

    # validate_input outputs
    validation_ok: bool
    validation_errors: list[str]

    # IssueParser outputs (M2)
    issue_analysis: dict[str, object]

    # explore_repository outputs
    extracted_symbols: list[str]
    project_tree_summary: str
    candidate_files: list[str]

    # TaskPlanner outputs (M2)
    investigation_plan: dict[str, object]

    # retrieve_code outputs
    retrieved_snippets: list[RetrievedSnippet]
    retrieval_summary: str

    # RootCauseAnalyzer outputs (M2)
    root_cause_analysis: dict[str, object]

    # build_diagnostic_report outputs (M2)
    diagnostic_report: dict[str, object]
    markdown_report: str

    # Back-compat alias used by M1 report path; M2 report node writes both.
    basic_report: dict[str, object]

    # Tracing accumulators (append reducer)
    tool_calls: Annotated[list[ToolCall], operator.add]
    node_timings: Annotated[list[NodeTiming], operator.add]
    errors: Annotated[list[str], operator.add]
    warnings: Annotated[list[str], operator.add]
    llm_calls: Annotated[list[LLMCall], operator.add]

    # Task status
    status: TaskStatus
    current_node: str


def make_initial_state(
    task_id: str,
    repository_path: str,
    issue_description: str,
    error_log: str | None,
) -> AgentState:
    """Construct a fully-initialized AgentState with no missing keys."""
    return AgentState(
        task_id=task_id,
        repository_path=repository_path,
        issue_description=issue_description,
        error_log=error_log,
        validation_ok=False,
        validation_errors=[],
        issue_analysis={},
        extracted_symbols=[],
        project_tree_summary="",
        candidate_files=[],
        investigation_plan={},
        retrieved_snippets=[],
        retrieval_summary="",
        root_cause_analysis={},
        diagnostic_report={},
        markdown_report="",
        basic_report={},
        tool_calls=[],
        node_timings=[],
        errors=[],
        warnings=[],
        llm_calls=[],
        status="pending",
        current_node="",
    )
