"""Tokenizer tests for Java identifier splitting.

Covers:
    1. camelCase
    2. PascalCase
    3. snake_case
    4. package path
    5. annotation
    6. exception class
    7. dedup and limit
"""

from __future__ import annotations

from springfix_agent.retrieval.tokenizer import (
    normalize_query_terms,
    tokenize_chunk_content,
    tokenize_identifier,
    tokenize_text,
)


# -- 1. camelCase --
def test_camel_case_split() -> None:
    result = tokenize_identifier("createOrderInTransaction")
    assert "create" in result
    assert "order" in result
    assert "transaction" in result


# -- 2. PascalCase --
def test_pascal_case_split() -> None:
    result = tokenize_identifier("OrderService")
    assert "order" in result
    assert "service" in result


# -- 3. snake_case --
def test_snake_case_split() -> None:
    result = tokenize_identifier("order_service")
    assert "order" in result
    assert "service" in result


# -- 4. package path --
def test_package_path_split() -> None:
    result = tokenize_identifier("com.springfix.sample.transaction")
    assert "com" in result
    assert "springfix" in result
    assert "sample" in result
    assert "transaction" in result


# -- 5. annotation --
def test_annotation_split() -> None:
    result = tokenize_identifier("@Transactional")
    assert "transactional" in result


# -- 6. exception class --
def test_exception_class_split() -> None:
    result = tokenize_identifier("NoUniqueBeanDefinitionException")
    assert "unique" in result or "bean" in result
    assert "exception" in result


# -- 7. dedup and limit --
def test_dedup_preserves_order() -> None:
    result = tokenize_identifier("OrderOrderService")
    # "order" should appear only once.
    assert result.count("order") == 1


def test_normalize_query_terms_dedup_and_cap() -> None:
    terms = ["OrderService", "OrderService", "@Transactional"] * 20
    accepted, discarded = normalize_query_terms(terms, max_terms=10)
    assert len(accepted) <= 10


def test_normalize_drops_stopwords() -> None:
    terms = ["the", "and", "OrderService"]
    accepted, _ = normalize_query_terms(terms)
    assert "the" not in accepted
    assert "order" in accepted or "orderservice" in accepted


def test_tokenize_empty() -> None:
    assert tokenize_identifier("") == []
    assert tokenize_identifier("@") == []


def test_tokenize_kebab_case() -> None:
    result = tokenize_identifier("spring-boot-starter")
    assert "spring" in result
    assert "boot" in result
    assert "starter" in result


def test_tokenize_chunk_content_basic() -> None:
    code = "public class OrderService { public void createOrder() {} }"
    tokens = tokenize_chunk_content(code)
    assert "order" in tokens
    assert "service" in tokens
    assert "create" in tokens


def test_tokenize_chunk_content_max_tokens() -> None:
    # Create content with many identifiers.
    code = " ".join(f"var{i}" for i in range(500))
    tokens = tokenize_chunk_content(code, max_tokens=50)
    assert len(tokens) <= 50


def test_tokenize_text_basic() -> None:
    result = tokenize_text("Spring Transactional bypass")
    assert "spring" in result
    assert "transactional" in result


def test_tokenize_identifier_acronym() -> None:
    """XMLParser should split into 'xml' and 'parser'."""
    result = tokenize_identifier("XMLParser")
    assert "xml" in result
    assert "parser" in result


def test_min_token_length_filter() -> None:
    """Single-char tokens should be dropped."""
    result = tokenize_identifier("aBC")
    # 'a' is too short (len < 2), should be dropped.
    assert "a" not in result
    assert "bc" in result
