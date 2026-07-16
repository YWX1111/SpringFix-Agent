"""Symbol extraction: deterministic Java identifier mining.

No LLM. Rules:
    1. If error_log contains a Java stack trace, parse class and method names
       from "at <package>.<Class>.<method>(<file>:<line>)" frames.
    2. From issue_description, extract tokens that look like Java identifiers:
       - At least 3 chars
       - Not pure lowercase English (must contain an uppercase letter or digit)
       - Not a common English stopword
    3. De-dup, cap at MAX_SYMBOLS (10), preserve insertion order.

Returned symbols are best-effort hints for find_java_symbol. When empty,
the calling node skips find_java_symbol entirely.
"""

from __future__ import annotations

import re

MAX_SYMBOLS = 10

_STACK_FRAME_RE = re.compile(
    r"at\s+(?P<qualified>[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\.(?P<method>[A-Za-z_][\w]*)\s*\(",
)

# Plain English stopwords to filter out of issue_description mining.
# Short list; kept conservative so we don't reject real Java identifiers.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "but", "for", "with", "from", "into", "this", "that",
        "these", "those", "when", "then", "than", "what", "which", "whose",
        "how", "why", "who", "where", "after", "before", "during", "while",
        "has", "have", "had", "was", "were", "are", "been", "being", "can", "could", "should", "would", "might", "must", "shall",
        "not", "nor", "yet", "either", "neither", "both", "all", "any",
        "some", "such", "very", "much", "many", "more", "most", "less",
        "least", "few", "several", "fewer", "fewest",
        "about", "above", "across", "against", "along", "among",
        "around", "at", "because", "behind", "below", "beneath", "beside",
        "between", "by", "down", "except", "in",
        "inside", "near", "of", "off", "on", "out", "outside",
        "over", "past", "through", "throughout", "to", "toward", "under",
        "underneath", "until", "up", "upon", "within", "without",
        "you", "your", "yours", "their", "theirs", "its", "our", "ours",
        "his", "her", "hers", "him", "them", "they", "she", "get", "got", "let", "try", "make", "made", "do", "did", "done",
        "see", "seen", "say", "said", "tell", "told", "ask", "asked",
        "put", "set", "run", "ran", "go", "went", "gone", "come", "came",
        "look", "took", "take", "taken", "give", "gave", "given", "find",
        "found", "know", "knew", "known", "think", "thought", "feel", "felt",
        "want", "wanted", "use", "used", "using", "uses",
    }
)


def extract_symbols(issue_description: str, error_log: str | None) -> list[str]:
    """Return at most MAX_SYMBOLS Java-identifier-shaped symbols."""
    seen: set[str] = set()
    out: list[str] = []

    if error_log:
        for m in _STACK_FRAME_RE.finditer(error_log):
            qualified = m.group("qualified")
            method = m.group("method")
            cls_name = qualified.rsplit(".", 1)[-1]
            for sym in (cls_name, method):
                if _is_valid_symbol(sym) and sym not in seen:
                    seen.add(sym)
                    out.append(sym)
                    if len(out) >= MAX_SYMBOLS:
                        return out

    if issue_description:
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", issue_description)
        for tok in tokens:
            if not _is_valid_symbol(tok):
                continue
            if tok in seen:
                continue
            seen.add(tok)
            out.append(tok)
            if len(out) >= MAX_SYMBOLS:
                return out

    return out


def _is_valid_symbol(token: str) -> bool:
    """Return True if token looks like a real Java identifier worth searching."""
    if len(token) < 3:
        return False
    if token.lower() == token and token not in {"int", "long", "char"}:
        # Pure-lowercase token; reject unless it is a primitive keyword.
        # Exception: stack-derived method names that are lowercase are
        # already filtered by _STACK_FRAME_RE upstream, so this is mostly
        # an issue_description-side filter.
        return False
    if token in _STOPWORDS:
        return False
    # Reject if all-uppercase and short (likely acronym noise)
    return not (token.upper() == token and len(token) <= 4)
