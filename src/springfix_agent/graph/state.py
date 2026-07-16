"""AgentState for M1 (deterministic vertical slice).

This state holds only fields that M1 nodes actually read or write.
M2 will extend with issue_class / plan_steps / root_causes; M3 with
retrieval scoring metadata. Each new field must have a real consumer
node — no placeholder fields.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

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
    """M1 state shape. Fields use overwrite semantics unless annotated with operator.add."""

    # Inputs (written once at task creation)
    task_id: str
    repository_path: str
    issue_description: str
    error_log: str | None

    # validate_input outputs
    validation_ok: bool
    validation_errors: list[str]

    # explore_repository outputs
    extracted_symbols: list[str]
    project_tree_summary: str
    candidate_files: list[str]

    # retrieve_code outputs
    retrieved_snippets: list[RetrievedSnippet]
    retrieval_summary: str

    # build_basic_report outputs
    basic_report: dict[str, object]
    markdown_report: str

    # Tracing accumulators (append reducer)
    tool_calls: Annotated[list[ToolCall], operator.add]
    node_timings: Annotated[list[NodeTiming], operator.add]
    errors: Annotated[list[str], operator.add]

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
        extracted_symbols=[],
        project_tree_summary="",
        candidate_files=[],
        retrieved_snippets=[],
        retrieval_summary="",
        basic_report={},
        markdown_report="",
        tool_calls=[],
        node_timings=[],
        errors=[],
        status="pending",
        current_node="",
    )
