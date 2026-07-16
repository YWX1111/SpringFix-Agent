"""validate_input node: defensive re-validation of request inputs.

The API layer already validates, but the Graph re-checks so a caller
that bypasses the API (e.g. direct TaskService.run_task_sync in tests)
still gets safe behavior. On failure, sets status=failed and subsequent
nodes short-circuit (they check validation_ok and return {}).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from springfix_agent.graph.state import AgentState
from springfix_agent.tools._path_safety import PathSafetyError, canonicalize_repository

MIN_ISSUE_LEN = 10
MAX_ISSUE_LEN = 2000
MAX_ERROR_LOG_LEN = 10000


def validate_input(
    state: AgentState,
    *,
    repository_path: Path,
    allow_root: Path,
) -> dict[str, Any]:
    """Re-validate repository_path, issue_description, error_log."""
    errors: list[str] = []

    repo_str = state["repository_path"]
    repo_path = Path(repo_str)
    try:
        canonicalize_repository(repo_path, allow_root)
    except PathSafetyError as e:
        errors.append(f"repository_path: {e}")

    issue = state["issue_description"].strip()
    if not (MIN_ISSUE_LEN <= len(issue) <= MAX_ISSUE_LEN):
        errors.append(
            f"issue_description length must be {MIN_ISSUE_LEN}-{MAX_ISSUE_LEN}, "
            f"got {len(issue)}"
        )

    error_log = state.get("error_log")
    if error_log is not None and len(error_log) > MAX_ERROR_LOG_LEN:
        errors.append(f"error_log too long: {len(error_log)} > {MAX_ERROR_LOG_LEN}")

    validation_ok = not errors
    new_status = "running" if validation_ok else "failed"
    return {
        "validation_ok": validation_ok,
        "validation_errors": errors,
        "errors": errors,
        "status": new_status,
    }
