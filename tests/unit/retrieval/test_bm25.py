"""BM25 retriever tests.

Covers:
    18. normal recall
    19. empty query
    20. empty repo
    21. top-K
    22. stable sort
    23. exception class name recall
    24. method name token recall
"""

from __future__ import annotations

from springfix_agent.retrieval.bm25 import BM25Retriever
from springfix_agent.retrieval.models import CodeChunk
from springfix_agent.retrieval.tokenizer import tokenize_chunk_content, tokenize_identifier


def _make_chunk(
    file: str,
    content: str,
    chunk_type: str = "method",
    symbol_name: str | None = None,
    start_line: int = 1,
    end_line: int = 10,
) -> CodeChunk:
    tokens = tokenize_chunk_content(content)
    cid = CodeChunk.make_chunk_id(file, chunk_type, start_line, end_line, symbol_name)
    return CodeChunk(
        chunk_id=cid,
        file=file,
        language="java",
        chunk_type=chunk_type,  # type: ignore[arg-type]
        symbol_name=symbol_name,
        start_line=start_line,
        end_line=end_line,
        content=content,
        tokens=tokens,
    )


def _bg_chunk(i: int) -> CodeChunk:
    """Create a background chunk that doesn't match typical queries."""
    return _make_chunk(
        f"Bg{i}.java",
        f"public class Background{i} {{\n"
        f"    public void run{i}() {{\n"
        f"        System.out.println(\"background task {i}\");\n"
        f"    }}\n"
        f"}}",
        symbol_name=f"run{i}", start_line=1, end_line=5,
    )


# -- 18. normal recall --
def test_normal_recall() -> None:
    chunks = [
        _make_chunk("OrderService.java",
                     "public class OrderService {\n"
                     "    public void createOrder() {\n"
                     "        createOrderInTransaction();\n"
                     "        throw new RuntimeException(\"simulated failure\");\n"
                     "    }\n"
                     "}",
                     symbol_name="createOrder", start_line=1, end_line=6),
        _make_chunk("OtherService.java",
                     "public class OtherService {\n"
                     "    public void doSomething() {\n"
                     "        System.out.println(\"hello\");\n"
                     "    }\n"
                     "}",
                     symbol_name="doSomething", start_line=1, end_line=5),
    ] + [_bg_chunk(i) for i in range(5)]
    bm25 = BM25Retriever(chunks)
    query_tokens = tokenize_identifier("createOrder")
    hits, ms = bm25.search(query_tokens, top_k=5)
    assert len(hits) >= 1
    assert hits[0].chunk.file == "OrderService.java"


# -- 19. empty query --
def test_empty_query() -> None:
    chunks = [_make_chunk("A.java", "public class A {}")]
    bm25 = BM25Retriever(chunks)
    hits, ms = bm25.search([], top_k=5)
    assert hits == []


# -- 20. empty repo --
def test_empty_repo() -> None:
    bm25 = BM25Retriever([])
    hits, ms = bm25.search(["test"], top_k=5)
    assert hits == []


# -- 21. top-K --
def test_top_k_limit() -> None:
    chunks = [
        _make_chunk(f"File{i}.java", f"public class Class{i} {{ void m{i}() {{}} }}",
                     start_line=1, end_line=3)
        for i in range(20)
    ]
    bm25 = BM25Retriever(chunks)
    hits, ms = bm25.search(["class"], top_k=5)
    assert len(hits) <= 5


# -- 22. stable sort --
def test_stable_sort() -> None:
    """Same query should produce same ordering on repeated runs."""
    chunks = [
        _make_chunk("A.java", "public class AlphaService { void alpha() {} }", start_line=1, end_line=2),
        _make_chunk("B.java", "public class BetaService { void beta() {} }", start_line=1, end_line=2),
        _make_chunk("C.java", "public class GammaService { void gamma() {} }", start_line=1, end_line=2),
    ]
    bm25 = BM25Retriever(chunks)
    q = tokenize_identifier("Service")
    h1, _ = bm25.search(q, top_k=3)
    h2, _ = bm25.search(q, top_k=3)
    assert [h.chunk.chunk_id for h in h1] == [h.chunk.chunk_id for h in h2]


# -- 23. exception class name recall --
def test_exception_class_name_recall() -> None:
    chunks = [
        _make_chunk("Svc.java",
                     "public class Svc {\n"
                     "    public void handle() {\n"
                     "        throw new RuntimeException(\"operation failed\");\n"
                     "    }\n"
                     "}",
                     symbol_name="handle", start_line=1, end_line=5),
        _make_chunk("Other.java",
                     "public class Other {\n"
                     "    public void greet() {\n"
                     "        System.out.println(\"hello world\");\n"
                     "    }\n"
                     "}",
                     symbol_name="greet", start_line=1, end_line=5),
    ] + [_bg_chunk(i) for i in range(5)]
    bm25 = BM25Retriever(chunks)
    query_tokens = tokenize_identifier("RuntimeException")
    hits, ms = bm25.search(query_tokens, top_k=5)
    assert any(h.chunk.file == "Svc.java" for h in hits)


# -- 24. method name token recall --
def test_method_name_token_recall() -> None:
    chunks = [
        _make_chunk("Svc.java",
                     "public class Svc {\n"
                     "    public void createOrderInTransaction() {\n"
                     "        jdbcTemplate.update(\"INSERT INTO orders\");\n"
                     "        throw new RuntimeException(\"fail\");\n"
                     "    }\n"
                     "}",
                     symbol_name="createOrderInTransaction", start_line=1, end_line=6),
        _make_chunk("Other.java",
                     "public class Other {\n"
                     "    public void doSomething() {\n"
                     "        System.out.println(\"unrelated\");\n"
                     "    }\n"
                     "}",
                     symbol_name="doSomething", start_line=1, end_line=5),
    ] + [_bg_chunk(i) for i in range(5)]
    bm25 = BM25Retriever(chunks)
    query_tokens = ["transaction", "order"]
    hits, _ = bm25.search(query_tokens, top_k=5)
    assert any(h.chunk.file == "Svc.java" for h in hits)


def test_build_duration_recorded() -> None:
    chunks = [_make_chunk("A.java", "public class A {}")]
    bm25 = BM25Retriever(chunks)
    assert bm25.build_duration_ms >= 0


def test_indexed_count() -> None:
    chunks = [
        _make_chunk("A.java", "public class Alpha {}"),
        _make_chunk("B.java", ""),  # empty content → no tokens
    ]
    bm25 = BM25Retriever(chunks)
    # Only A.java should be indexed (B.java has no tokens).
    assert bm25.indexed_count >= 1
