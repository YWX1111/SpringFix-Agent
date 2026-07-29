"""Prompt template rendering tests."""

from __future__ import annotations

import pytest

from springfix_agent.llm.prompts import render_prompt


def test_render_issue_parser_template() -> None:
    rendered = render_prompt(
        "issue_parser",
        issue_description="calling createOrder throws RuntimeException",
        error_log="java.lang.RuntimeException: simulated failure",
    )
    assert "createOrder" in rendered
    assert "RuntimeException" in rendered


def test_render_task_planner_template() -> None:
    rendered = render_prompt(
        "task_planner",
        issue_description="calling createOrder throws",
        issue_category="transaction",
        extracted_symbols='["OrderService"]',
        search_terms='["@Transactional"]',
    )
    assert "transaction" in rendered
    assert "OrderService" in rendered


def test_render_root_cause_analyzer_template() -> None:
    rendered = render_prompt(
        "root_cause_analyzer",
        issue_description="calling createOrder throws",
        issue_category="transaction",
        symptoms='["no rollback"]',
        exception_types='["RuntimeException"]',
        investigation_plan='{"steps":[]}',
        project_tree_summary="root/",
        retrieved_snippets="--- file.java ---\ncode",
    )
    assert "transaction" in rendered
    assert "RuntimeException" in rendered


def test_missing_placeholder_raises() -> None:
    with pytest.raises(KeyError):
        render_prompt("issue_parser", issue_description="x")


def test_none_value_rendered_as_none_placeholder() -> None:
    rendered = render_prompt(
        "issue_parser",
        issue_description="x",
        error_log=None,
    )
    assert "(none)" in rendered


def test_template_includes_injection_protection_clause() -> None:
    rendered = render_prompt(
        "issue_parser",
        issue_description="x",
        error_log="log",
    )
    assert "ignored" in rendered.lower() or "instruction" in rendered.lower()
