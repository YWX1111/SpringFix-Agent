"""Prompt template loader.

Prompts are stored as ``.md`` files under ``llm/prompts/``. This module
loads them via ``importlib.resources`` so they ship with the package
and remain easy to edit without touching Python code.

Templates use ``{{variable}}`` substitution. Only a small curated set of
variables is expected per template; missing variables raise a clear
``KeyError`` so the failure is visible in tests rather than silently
producing an empty prompt.
"""

from __future__ import annotations

from importlib import resources
from typing import Any


def render_prompt(template_name: str, **variables: Any) -> str:
    """Load ``llm/prompts/<template_name>.md`` and render ``{{var}}``."""
    prompt_pkg = "springfix_agent.llm.prompts"
    with resources.files(prompt_pkg).joinpath(f"{template_name}.md").open(
        "r", encoding="utf-8"
    ) as f:
        template = f.read()

    for key, value in variables.items():
        if value is None:
            value = "(none)"
        template = template.replace("{{" + key + "}}", str(value))

    # Surface any leftover placeholders so broken templates fail loudly.
    if "{{" in template:
        raise KeyError(f"unrendered placeholder(s) in {template_name}: {template}")
    return template
