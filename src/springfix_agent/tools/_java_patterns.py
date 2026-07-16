"""Java regex patterns, centralized for M3 swap-out.

M1 uses these patterns for ``find_java_symbol``. M3 will replace the
implementation with Tree-sitter AST without changing the public API
exposed by ``match_symbol``.
"""

from __future__ import annotations

import re

_COMMON_MODIFIERS = (
    r"(?:public|protected|private|abstract|final|static|synchronized|"
    r"native|default|strictfp|\s)*"
)

SYMBOL_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "class": re.compile(
        rf"^{_COMMON_MODIFIERS}class\s+(?P<name>[A-Z][A-Za-z0-9_]*)",
        re.MULTILINE,
    ),
    "interface": re.compile(
        rf"^{_COMMON_MODIFIERS}interface\s+(?P<name>[A-Z][A-Za-z0-9_]*)",
        re.MULTILINE,
    ),
    "enum": re.compile(
        rf"^{_COMMON_MODIFIERS}enum\s+(?P<name>[A-Z][A-Za-z0-9_]*)",
        re.MULTILINE,
    ),
    "record": re.compile(
        rf"^{_COMMON_MODIFIERS}record\s+(?P<name>[A-Z][A-Za-z0-9_]*)",
        re.MULTILINE,
    ),
    "method": re.compile(
        rf"^{_COMMON_MODIFIERS}"
        r"(?:[A-Z][A-Za-z0-9_<>\[\],\s]*|[a-z][A-Za-z0-9_<>\[\],\s]*|void)\s+"
        r"(?P<name>[a-z][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    ),
    "annotation": re.compile(
        r"@(?P<name>[A-Z][A-Za-z0-9_]*)\s*(?:\(|\s|$)",
    ),
}

ANY_TYPES = ["class", "interface", "enum", "record", "method", "annotation"]


def match_symbol(
    symbol_name: str,
    symbol_type: str,
    content: str,
) -> list[tuple[int, str, str]]:
    """Find matches of ``symbol_name`` in ``content``.

    Args:
        symbol_name: Exact Java identifier to match (case-sensitive).
        symbol_type: One of class|interface|enum|record|method|annotation|any.
        content: File content as a string.

    Returns:
        List of (line_number, matched_symbol_type, context_line) tuples,
        sorted by (line_number, symbol_type). ``line_number`` is 1-based.
        ``context_line`` is the matched source line (without trailing newline).
    """
    if symbol_type == "any":
        types_to_check = ANY_TYPES
    else:
        if symbol_type not in SYMBOL_TYPE_PATTERNS:
            return []
        types_to_check = [symbol_type]

    matches: list[tuple[int, str, str]] = []
    seen: set[tuple[int, str]] = set()

    for stype in types_to_check:
        pattern = SYMBOL_TYPE_PATTERNS[stype]
        for m in pattern.finditer(content):
            if m.group("name") != symbol_name:
                continue
            line_no = content.count("\n", 0, m.start()) + 1
            key = (line_no, stype)
            if key in seen:
                continue
            seen.add(key)
            line_start = content.rfind("\n", 0, m.start()) + 1
            line_end = content.find("\n", m.start())
            if line_end == -1:
                line_end = len(content)
            context_line = content[line_start:line_end]
            matches.append((line_no, stype, context_line))

    matches.sort(key=lambda x: (x[0], x[1]))
    return matches
