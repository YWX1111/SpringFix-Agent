"""Deterministic Java identifier tokenizer.

Handles camelCase, PascalCase, snake_case, kebab-case, package paths,
Spring annotations, and exception class names. All output tokens are
lowercase. Natural-language stopwords are removed; Java / Spring keywords
are retained.

This is NOT an NLP tokenizer. It is a deterministic identifier splitter
designed for code search relevance.
"""

from __future__ import annotations

import re

MAX_TOKENS_PER_CHUNK = 200
MAX_QUERY_TERMS = 50
MIN_TOKEN_LEN = 2

# Natural-language stopwords to drop (lowercase).
_NL_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "but", "for", "with", "from", "into", "this", "that",
    "these", "those", "when", "then", "than", "what", "which", "whose",
    "how", "why", "who", "where", "after", "before", "during", "while",
    "has", "have", "had", "was", "were", "are", "been", "being",
    "can", "could", "should", "would", "might", "must", "shall",
    "not", "nor", "yet", "either", "neither", "both", "all", "any",
    "some", "such", "very", "much", "many", "more", "most", "less",
    "least", "few", "several", "fewer", "fewest",
    "about", "above", "across", "against", "along", "among",
    "around", "because", "behind", "below", "beneath", "beside",
    "between", "down", "except", "inside", "near",
    "off", "outside", "over", "past", "through", "throughout",
    "toward", "under", "underneath", "until", "upon", "within", "without",
    "you", "your", "yours", "their", "theirs", "its", "our", "ours",
    "his", "her", "hers", "him", "them", "they", "she",
    "get", "got", "let", "try", "make", "made", "did", "done",
    "see", "seen", "say", "said", "tell", "told", "ask", "asked",
    "put", "set", "ran", "gone", "come", "came",
    "look", "took", "take", "taken", "give", "gave", "given", "find",
    "found", "know", "knew", "known", "think", "thought", "feel", "felt",
    "want", "wanted", "use", "used", "using", "uses",
    "also", "just", "only", "each", "every", "other", "another",
    "here", "there", "now", "too", "own", "same", "well", "back",
    "even", "still", "already", "always", "never", "often",
})

# Separator pattern: split on non-alphanumeric boundaries.
_SEP_RE = re.compile(r"[^A-Za-z0-9]+")

# camelCase / PascalCase split: insert boundary before uppercase runs.
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_RE = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")


def tokenize_identifier(identifier: str) -> list[str]:
    """Split a single Java identifier into lowercase sub-tokens.

    Supports camelCase, PascalCase, snake_case, kebab-case, and mixed forms.
    Returns de-duplicated tokens preserving first-seen order.
    """
    if not identifier:
        return []

    # Strip leading @ for annotations.
    raw = identifier.lstrip("@")
    if not raw:
        return []

    # Phase 1: split on explicit separators (_, -, ., spaces, etc.).
    parts = [p for p in _SEP_RE.split(raw) if p]

    # Phase 2: split each part on camelCase / PascalCase boundaries.
    sub_tokens: list[str] = []
    for part in parts:
        # Split acronym boundaries first: "XMLParser" -> "XML", "Parser"
        segments = _ACRONYM_RE.split(part)
        for seg in segments:
            # Then split camelCase: "createOrder" -> "create", "Order"
            words = _CAMEL_RE.split(seg)
            for w in words:
                if w:
                    sub_tokens.append(w.lower())

    # De-duplicate preserving order.
    seen: set[str] = set()
    result: list[str] = []
    for tok in sub_tokens:
        if len(tok) < MIN_TOKEN_LEN:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        result.append(tok)

    return result


def tokenize_text(text: str) -> list[str]:
    """Tokenize a free-form text string (e.g. issue description).

    Splits on whitespace and non-alphanumeric boundaries, then applies
    identifier tokenization to each fragment.
    """
    if not text:
        return []
    fragments = [f for f in _SEP_RE.split(text) if f]
    seen: set[str] = set()
    result: list[str] = []
    for frag in fragments:
        for tok in tokenize_identifier(frag):
            if tok not in seen:
                seen.add(tok)
                result.append(tok)
    return result


def tokenize_chunk_content(content: str, *, max_tokens: int = MAX_TOKENS_PER_CHUNK) -> list[str]:
    """Tokenize a code chunk's content, dropping stopwords and enforcing limits.

    Preserves valuable raw identifiers (lowercased) alongside sub-tokens
    so that exact matches like ``orderservice`` remain searchable.
    """
    if not content:
        return []

    # Extract all identifier-like sequences from source code.
    raw_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", content)

    seen: set[str] = set()
    result: list[str] = []

    for raw in raw_tokens:
        lowered = raw.lower()
        # Add sub-tokens from identifier splitting.
        for tok in tokenize_identifier(raw):
            if tok in _NL_STOPWORDS:
                continue
            if tok in seen:
                continue
            seen.add(tok)
            result.append(tok)
            if len(result) >= max_tokens:
                return result

        # Also keep the full lowered identifier if it is compound and valuable.
        if len(lowered) >= MIN_TOKEN_LEN and lowered not in seen and lowered not in _NL_STOPWORDS:
            seen.add(lowered)
            result.append(lowered)
            if len(result) >= max_tokens:
                return result

    return result


def normalize_query_terms(terms: list[str], *, max_terms: int = MAX_QUERY_TERMS) -> tuple[list[str], int]:
    """Normalize and de-duplicate query terms, returning (accepted, discarded_count).

    Each term is tokenized (identifier-split) and filtered. The result
    is capped at ``max_terms``.
    """
    seen: set[str] = set()
    result: list[str] = []
    discarded = 0

    for term in terms:
        if not term or not term.strip():
            continue
        sub_tokens = tokenize_identifier(term.strip())
        if not sub_tokens:
            # Keep the lowered raw form if it has value.
            lowered = term.strip().lower()
            if len(lowered) >= MIN_TOKEN_LEN and lowered not in _NL_STOPWORDS:
                sub_tokens = [lowered]
            else:
                discarded += 1
                continue

        for tok in sub_tokens:
            if tok in _NL_STOPWORDS:
                discarded += 1
                continue
            if tok in seen:
                continue
            seen.add(tok)
            result.append(tok)
            if len(result) >= max_terms:
                return result, len(terms) - terms.index(term) - 1

    return result, discarded
