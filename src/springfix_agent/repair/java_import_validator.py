"""Conservative, deterministic Java import consistency heuristics.

This module intentionally does not resolve Java names or prove compilation.
It catches the narrow, high-confidence case where a patch introduces a simple
capitalized type/annotation name without an import, same-file declaration, or
fully-qualified spelling. Maven remains the authoritative compiler oracle.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Literal

from springfix_agent.repair.models import JavaImportCheckResult

_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:static\s+)?(?P<name>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)\s*;\s*$"
)
_DECLARATION_RE = re.compile(
    r"\b(?:class|interface|enum|record)\s+([A-Z][A-Za-z0-9_$]*)\b"
)
_ANNOTATION_DECLARATION_RE = re.compile(r"\b@interface\s+([A-Z][A-Za-z0-9_$]*)\b")
_CAPITALIZED_RE = re.compile(r"\b[A-Z][A-Za-z0-9_$]*\b")
_ANNOTATION_RE = re.compile(r"(?<![\w.$])@([A-Z][A-Za-z0-9_$]*)\b")
_FQN_RE = re.compile(r"(?:[a-z_$][\w$]*\.)+([A-Z][A-Za-z0-9_$]*)\b")
_TYPE_CONTEXT_RES = (
    re.compile(r"\bnew\s+([A-Z][A-Za-z0-9_$]*)\b"),
    re.compile(r"\b(?:extends|implements|instanceof|throws)\s+([A-Z][A-Za-z0-9_$]*)\b"),
    re.compile(r"<\s*([A-Z][A-Za-z0-9_$]*)\s*(?:[,>])"),
    re.compile(
        r"\b([A-Z][A-Za-z0-9_$]*)\s*(?:<[^>\n]*>)?\s+[a-z_$][A-Za-z0-9_$]*\s*(?:[=;,({]|$)"
    ),
    re.compile(r"(?<![\w.$])([A-Z][A-Za-z0-9_$]*)\s*\."),
)
_JAVA_FILE_MARKER_RE = re.compile(
    r"(?m)^\s*(?:package\s+|import\s+|(?:public\s+)?(?:class|interface|enum|record)\s+)|[{}]"
)

_JAVA_KEYWORDS = frozenset(
    {
        "abstract",
        "assert",
        "boolean",
        "break",
        "byte",
        "case",
        "catch",
        "char",
        "class",
        "const",
        "continue",
        "default",
        "do",
        "double",
        "else",
        "enum",
        "extends",
        "final",
        "finally",
        "float",
        "for",
        "goto",
        "if",
        "implements",
        "import",
        "instanceof",
        "int",
        "interface",
        "long",
        "native",
        "new",
        "package",
        "private",
        "protected",
        "public",
        "return",
        "short",
        "static",
        "strictfp",
        "super",
        "switch",
        "synchronized",
        "this",
        "throw",
        "throws",
        "transient",
        "try",
        "void",
        "volatile",
        "while",
        "true",
        "false",
        "null",
        "record",
        "sealed",
        "permits",
        "non-sealed",
        "var",
        "yield",
    }
)
_JAVA_LANG_TYPES = frozenset(
    {
        "Appendable",
        "AutoCloseable",
        "Boolean",
        "Byte",
        "CharSequence",
        "Character",
        "Class",
        "Cloneable",
        "Comparable",
        "Double",
        "Enum",
        "Error",
        "Exception",
        "Float",
        "IllegalArgumentException",
        "IllegalStateException",
        "IndexOutOfBoundsException",
        "Iterable",
        "Long",
        "Math",
        "Number",
        "Object",
        "Override",
        "Runnable",
        "RuntimeException",
        "SafeVarargs",
        "Short",
        "String",
        "StringBuffer",
        "StringBuilder",
        "SuppressWarnings",
        "System",
        "Thread",
        "Throwable",
        "Void",
        "Deprecated",
        "FunctionalInterface",
    }
)


def _strip_comments_and_literals(source: str) -> str:
    """Blank comments and literals while preserving line structure."""
    pattern = re.compile(
        r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*.*?\*/)',
        re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return pattern.sub(replace, source)


def _without_import_lines(source: str) -> str:
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join("" if _IMPORT_RE.match(line) else line for line in lines)


def _simple_imports(source: str) -> set[str]:
    result: set[str] = set()
    for line in source.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = _IMPORT_RE.match(line)
        if match is None:
            continue
        name = match.group("name")
        if name.endswith(".*"):
            continue
        result.add(name.rsplit(".", 1)[-1])
    return result


def imported_simple_symbols(source: str) -> set[str]:
    """Return simple names declared by non-wildcard import declarations."""
    return _simple_imports(source)


def _declared_symbols(source: str) -> set[str]:
    code = _strip_comments_and_literals(source)
    return set(_DECLARATION_RE.findall(code)) | set(_ANNOTATION_DECLARATION_RE.findall(code))


def _capitalized_symbols(source: str) -> tuple[set[str], set[str]]:
    code = _strip_comments_and_literals(_without_import_lines(source))
    confident = set(_ANNOTATION_RE.findall(code))
    confident.update(_DECLARATION_RE.findall(code))
    confident.update(_ANNOTATION_DECLARATION_RE.findall(code))
    for pattern in _TYPE_CONTEXT_RES:
        confident.update(pattern.findall(code))
    candidates = set(_CAPITALIZED_RE.findall(code))
    fqn_symbols = set(_FQN_RE.findall(code))
    for match in _CAPITALIZED_RE.finditer(code):
        before = code[: match.start()].rstrip()
        if before.endswith("."):
            candidates.discard(match.group(0))

    def keep(symbol: str) -> bool:
        return (
            symbol not in _JAVA_KEYWORDS
            and symbol not in _JAVA_LANG_TYPES
            and symbol not in fqn_symbols
        )

    confident = {symbol for symbol in confident if keep(symbol)}
    uncertain = {symbol for symbol in candidates - confident if keep(symbol)}
    return confident, uncertain


def fully_qualified_symbols(source: str) -> set[str]:
    """Return final segments of fully-qualified capitalized names."""
    return set(_FQN_RE.findall(_strip_comments_and_literals(source)))


def _introduced_symbols(
    changes: Iterable[tuple[str, str]],
) -> tuple[set[str], set[str], set[str]]:
    confident: set[str] = set()
    uncertain: set[str] = set()
    qualified: set[str] = set()
    for old_code, new_code in changes:
        old_confident, old_uncertain = _capitalized_symbols(old_code)
        new_confident, new_uncertain = _capitalized_symbols(new_code)
        confident.update(new_confident - old_confident)
        uncertain.update(new_uncertain - old_uncertain)
        qualified.update(
            fully_qualified_symbols(new_code) - fully_qualified_symbols(old_code)
        )
    return confident, uncertain, qualified


def check_java_import_completeness_for_file(
    existing_full_file: str,
    proposed_full_file: str,
    changes: Sequence[tuple[str, str]],
) -> JavaImportCheckResult:
    """Check a composed Java file after the supplied non-overlapping edits."""
    if not _JAVA_FILE_MARKER_RE.search(existing_full_file) and not _JAVA_FILE_MARKER_RE.search(
        proposed_full_file
    ):
        return JavaImportCheckResult(
            introduced_symbols=[],
            already_resolved_symbols=[],
            unresolved_symbols=[],
            status="unknown",
        )
    confident_introduced, uncertain_introduced, qualified_introduced = _introduced_symbols(changes)
    introduced = confident_introduced | uncertain_introduced | qualified_introduced
    if not introduced:
        has_java_code_change = any(
            _strip_comments_and_literals(new_code).strip()
            != _strip_comments_and_literals(old_code).strip()
            for old_code, new_code in changes
            if not all(_IMPORT_RE.match(line) for line in new_code.splitlines() if line.strip())
        )
        return JavaImportCheckResult(
            introduced_symbols=[],
            already_resolved_symbols=[],
            unresolved_symbols=[],
            status="unknown" if has_java_code_change else "pass",
        )

    imports = _simple_imports(proposed_full_file)
    declarations = _declared_symbols(proposed_full_file)
    fqn_resolved = fully_qualified_symbols(proposed_full_file)
    resolved = {
        symbol
        for symbol in introduced
        if symbol in imports
        or symbol in declarations
        or symbol in _JAVA_LANG_TYPES
        or symbol in fqn_resolved
        or symbol in qualified_introduced
    }
    unresolved = confident_introduced - resolved
    uncertain_unresolved = uncertain_introduced - resolved
    status: Literal["pass", "fail", "unknown"] = (
        "fail" if unresolved else "unknown" if uncertain_unresolved else "pass"
    )
    return JavaImportCheckResult(
        introduced_symbols=sorted(introduced),
        already_resolved_symbols=sorted(resolved),
        unresolved_symbols=sorted(unresolved),
        status=status,
    )


def check_java_import_completeness(
    old_code: str,
    new_code: str,
    existing_full_file: str,
) -> JavaImportCheckResult:
    """Check one replacement against an existing Java file.

    If the old segment is absent or ambiguous, return ``unknown`` rather than
    guessing.  The production validator uses the composed-file helper when a
    proposal contains multiple edits.
    """
    normalized_file = existing_full_file.replace("\r\n", "\n").replace("\r", "\n")
    old_normalized = old_code.replace("\r\n", "\n").replace("\r", "\n")
    new_normalized = new_code.replace("\r\n", "\n").replace("\r", "\n")
    if not old_normalized or normalized_file.count(old_normalized) != 1:
        return JavaImportCheckResult(
            introduced_symbols=[],
            already_resolved_symbols=[],
            unresolved_symbols=[],
            status="unknown",
        )
    proposed = normalized_file.replace(old_normalized, new_normalized, 1)
    return check_java_import_completeness_for_file(
        normalized_file,
        proposed,
        [(old_normalized, new_normalized)],
    )


__all__ = [
    "check_java_import_completeness",
    "check_java_import_completeness_for_file",
    "fully_qualified_symbols",
    "imported_simple_symbols",
]
