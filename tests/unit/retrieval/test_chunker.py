"""Chunker tests for Java and config code chunking.

Covers:
    8.  Java class block
    9.  method block
    10. constructor block
    11. interface, enum, record
    12. comments and strings with braces
    13. oversized method split
    14. Java parse failure fallback
    15. XML/YAML/Properties windows
    16. real line numbers
    17. stable chunk_id
"""

from __future__ import annotations

from pathlib import Path

from springfix_agent.retrieval.chunker import (
    _chunk_java,
    _chunk_windows,
    _find_block_end,
    chunk_file,
    chunk_repository,
)
from springfix_agent.retrieval.models import CodeChunk

# -- 8. Java class block --

_SIMPLE_CLASS = """\
package com.example;

public class OrderService {
    public void createOrder() {}
}
"""


def test_java_class_block() -> None:
    chunks = _chunk_java("OrderService.java", _SIMPLE_CLASS, max_lines=60, max_chars=4000, overlap_lines=5)
    class_chunks = [c for c in chunks if c.chunk_type == "class"]
    assert len(class_chunks) >= 1
    assert class_chunks[0].symbol_name == "OrderService"


# -- 9. method block --

_METHOD_CLASS = """\
public class Svc {
    public void doWork() {
        System.out.println("working");
    }
}
"""


def test_java_method_block() -> None:
    chunks = _chunk_java("Svc.java", _METHOD_CLASS, max_lines=60, max_chars=4000, overlap_lines=5)
    method_chunks = [c for c in chunks if c.chunk_type == "method"]
    assert any(c.symbol_name == "doWork" for c in method_chunks)


# -- 10. constructor block --

_CTOR_CLASS = """\
public class Svc {
    private final String name;
    public Svc(String name) {
        this.name = name;
    }
}
"""


def test_java_constructor_block() -> None:
    chunks = _chunk_java("Svc.java", _CTOR_CLASS, max_lines=60, max_chars=4000, overlap_lines=5)
    ctor_chunks = [c for c in chunks if c.chunk_type == "constructor"]
    assert any(c.symbol_name == "Svc" for c in ctor_chunks)


# -- 11. interface, enum, record --

_INTERFACE = """\
public interface Greeter {
    String greet();
}
"""
_ENUM = "public enum Status { ACTIVE, INACTIVE }"
_RECORD = "public record Point(int x, int y) {}"


def test_java_interface() -> None:
    chunks = _chunk_java("G.java", _INTERFACE, max_lines=60, max_chars=4000, overlap_lines=5)
    assert any(c.chunk_type == "interface" for c in chunks)


def test_java_enum() -> None:
    chunks = _chunk_java("E.java", _ENUM, max_lines=60, max_chars=4000, overlap_lines=5)
    # Enum might produce a class-like chunk or window; just ensure no crash.
    assert len(chunks) >= 1


def test_java_record() -> None:
    chunks = _chunk_java("R.java", _RECORD, max_lines=60, max_chars=4000, overlap_lines=5)
    assert len(chunks) >= 1


# -- 12. comments and strings with braces --

_BRACES_IN_STRINGS = """\
public class Svc {
    public void test() {
        String s = "{ not a block }";
        // { also not a block }
        /* { still not } */
        char c = '{';
    }
}
"""


def test_braces_in_strings_and_comments() -> None:
    chunks = _chunk_java("Svc.java", _BRACES_IN_STRINGS, max_lines=60, max_chars=4000, overlap_lines=5)
    method_chunks = [c for c in chunks if c.chunk_type == "method" and c.symbol_name == "test"]
    assert len(method_chunks) >= 1
    # The method block should end at the real closing brace.
    m = method_chunks[0]
    assert m.end_line >= 7


# -- 13. oversized method split --

def _make_long_method(n_lines: int) -> str:
    body = "\n".join(f'        System.out.println("line {i}");' for i in range(n_lines))
    return f"""\
public class Svc {{
    public void longMethod() {{
{body}
    }}
}}
"""


def test_oversized_method_splits() -> None:
    code = _make_long_method(100)
    chunks = _chunk_java("Svc.java", code, max_lines=20, max_chars=4000, overlap_lines=5)
    # Should produce multiple chunks for a 100-line method.
    method_chunks = [c for c in chunks if c.chunk_type == "method"]
    assert len(method_chunks) >= 2
    # Each chunk should not exceed max_lines + small tolerance.
    for c in method_chunks:
        assert c.end_line - c.start_line + 1 <= 25


# -- 14. Java parse failure fallback --

_MALFORMED_JAVA = "not valid java at all @#$"


def test_java_parse_failure_fallback() -> None:
    chunks = _chunk_java("Bad.java", _MALFORMED_JAVA, max_lines=60, max_chars=4000, overlap_lines=5)
    # Falls back to file_window.
    assert len(chunks) >= 1
    assert chunks[0].chunk_type == "file_window"


# -- 15. XML/YAML/Properties windows --

_XML = """\
<?xml version="1.0"?>
<project>
  <dependencies>
    <dependency>spring</dependency>
  </dependencies>
</project>
"""

_YAML = """\
spring:
  datasource:
    url: jdbc:h2:mem:testdb
  jpa:
    hibernate:
      ddl-auto: update
"""

_PROPERTIES = "key1=value1\nkey2=value2\nkey3=value3\n"


def test_xml_window_chunking() -> None:
    chunks = _chunk_windows(
        rel_path="pom.xml", lines=_XML.splitlines(),
        language="xml", chunk_type="config_block",
        max_lines=60, max_chars=4000, overlap_lines=5,
    )
    assert len(chunks) >= 1
    assert chunks[0].language == "xml"


def test_yaml_window_chunking() -> None:
    chunks = _chunk_windows(
        rel_path="app.yml", lines=_YAML.splitlines(),
        language="yaml", chunk_type="config_block",
        max_lines=60, max_chars=4000, overlap_lines=5,
    )
    assert len(chunks) >= 1
    assert chunks[0].language == "yaml"


def test_properties_window_chunking() -> None:
    chunks = _chunk_windows(
        rel_path="app.properties", lines=_PROPERTIES.splitlines(),
        language="properties", chunk_type="config_block",
        max_lines=60, max_chars=4000, overlap_lines=5,
    )
    assert len(chunks) >= 1
    assert chunks[0].chunk_type == "config_block"


# -- 16. real line numbers --

def test_real_line_numbers() -> None:
    chunks = _chunk_java("OrderService.java", _SIMPLE_CLASS, max_lines=60, max_chars=4000, overlap_lines=5)
    for c in chunks:
        assert c.start_line >= 1
        assert c.end_line >= c.start_line
        # Verify content lines match.
        content_lines = c.content.splitlines()
        expected_count = c.end_line - c.start_line + 1
        assert len(content_lines) <= expected_count + 1  # tolerance


# -- 17. stable chunk_id --

def test_stable_chunk_id() -> None:
    """Same content produces same chunk_ids."""
    c1 = _chunk_java("Svc.java", _METHOD_CLASS, max_lines=60, max_chars=4000, overlap_lines=5)
    c2 = _chunk_java("Svc.java", _METHOD_CLASS, max_lines=60, max_chars=4000, overlap_lines=5)
    assert len(c1) == len(c2)
    for a, b in zip(c1, c2, strict=True):
        assert a.chunk_id == b.chunk_id


def test_chunk_id_no_absolute_path() -> None:
    """chunk_id must not contain absolute path components."""
    cid = CodeChunk.make_chunk_id("src/Main.java", "class", 1, 10, "Main")
    assert "/" in cid or cid.isalnum()  # It's a hex hash
    assert "src/Main.java" not in cid


def test_find_block_end_basic() -> None:
    lines = ["public class X {", "  void m() {", "  }", "}"]
    end = _find_block_end(lines, 0)
    assert end == 3


def test_chunk_file_nonexistent(tmp_path: Path) -> None:
    chunks, warnings = chunk_file(tmp_path, "NonExistent.java")
    assert chunks == []
    assert len(warnings) >= 1


def test_chunk_repository_empty(tmp_path: Path) -> None:
    chunks, warnings, truncated = chunk_repository(tmp_path)
    assert chunks == []
    assert truncated is False


def test_chunk_repository_with_java_file(tmp_path: Path) -> None:
    (tmp_path / "Test.java").write_text(_SIMPLE_CLASS, encoding="utf-8")
    chunks, warnings, truncated = chunk_repository(tmp_path)
    assert len(chunks) >= 1
    assert truncated is False


def test_chunk_repository_excludes_target_dir(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "Gen.java").write_text("public class Gen {}", encoding="utf-8")
    (tmp_path / "Main.java").write_text(_SIMPLE_CLASS, encoding="utf-8")
    chunks, _, _ = chunk_repository(tmp_path)
    files = {c.file for c in chunks}
    assert not any("target" in f for f in files)


def test_chunk_repository_max_files(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"File{i}.java").write_text(
            f"public class File{i} {{}}", encoding="utf-8"
        )
    chunks, warnings, truncated = chunk_repository(tmp_path, max_files=2)
    assert truncated is True
    assert any("max_files" in w for w in warnings)
