"""Generic deterministic Java import correctness fixtures."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.repair.java_import_validator import check_java_import_completeness
from springfix_agent.repair.models import EvidenceSnippet, PatchEdit, PatchProposal
from springfix_agent.repair.validator import validate_patch_proposal


def _proposal(*edits: PatchEdit) -> PatchProposal:
    return PatchProposal(
        status="proposed",
        summary="import correctness fixture",
        root_cause_reference="candidate:0",
        edits=list(edits),
    )


def _edit(start: int, end: int, old: str, new: str) -> PatchEdit:
    return PatchEdit(
        file="src/main/java/example/App.java",
        start_line=start,
        end_line=end,
        old_code=old,
        new_code=new,
        rationale="fixture-backed Java edit",
    )


def _root(tmp_path: Path, source: str) -> Path:
    root = tmp_path / "repo"
    path = root / "src/main/java/example/App.java"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    return root


def _evidence(start: int, end: int) -> list[EvidenceSnippet]:
    return [
        EvidenceSnippet(
            file="src/main/java/example/App.java",
            start_line=start,
            end_line=end,
            content="fixture",
        )
    ]


def test_missing_import_is_rejected_with_symbol(tmp_path: Path) -> None:
    source = "package example;\n\npublic class App {\n    void run() {}\n}\n"
    root = _root(tmp_path, source)
    result = validate_patch_proposal(
        _proposal(_edit(4, 4, "    void run() {}", "    SomeFrameworkAnnotation value;")),
        root,
        _evidence(4, 4),
    )
    assert not result.passed
    assert result.proposal.status == "insufficient_evidence"
    rejected = result.rejected_edits[0]
    assert rejected.reason == "missing_required_import"
    assert rejected.affected_symbol == "SomeFrameworkAnnotation"
    assert result.java_import_checks[0].status == "fail"


def test_existing_import_passes(tmp_path: Path) -> None:
    source = (
        "package example;\n\n"
        "import example.framework.SomeFrameworkAnnotation;\n\n"
        "public class App {\n    SomeFrameworkAnnotation value;\n}\n"
    )
    root = _root(tmp_path, source)
    result = validate_patch_proposal(
        _proposal(_edit(6, 6, "    SomeFrameworkAnnotation value;", "    SomeFrameworkAnnotation value; // kept")),
        root,
        _evidence(6, 6),
    )
    assert result.passed
    assert result.java_import_checks[0].status == "pass"


def test_added_import_passes_as_supporting_edit(tmp_path: Path) -> None:
    source = (
        "package example;\n\n"
        "import java.util.List;\n\n"
        "public class App {\n    void run() {}\n}\n"
    )
    root = _root(tmp_path, source)
    result = validate_patch_proposal(
        _proposal(
            _edit(6, 6, "    void run() {}", "    SomeFrameworkAnnotation value;"),
            _edit(
                3,
                3,
                "import java.util.List;",
                "import example.framework.SomeFrameworkAnnotation;\nimport java.util.List;",
            ),
        ),
        root,
        _evidence(6, 6),
    )
    assert result.passed
    assert result.accepted_edit_count == 2
    assert result.java_import_checks[0].status == "pass"


def test_import_edit_must_match_primary_symbol(tmp_path: Path) -> None:
    source = (
        "package example;\n\n"
        "import java.util.List;\n\n"
        "public class App {\n    void run() {}\n}\n"
    )
    root = _root(tmp_path, source)
    result = validate_patch_proposal(
        _proposal(
            _edit(6, 6, "    void run() {}", "    SomeFrameworkAnnotation value;"),
            _edit(
                3,
                3,
                "import java.util.List;",
                "import example.framework.OtherAnnotation;\nimport java.util.List;",
            ),
        ),
        root,
        _evidence(6, 6),
    )
    assert not result.passed
    assert {item.reason for item in result.rejected_edits} >= {"unrelated_import"}


def test_fully_qualified_symbol_passes_without_import(tmp_path: Path) -> None:
    source = "package example;\n\npublic class App {\n    void run() {}\n}\n"
    root = _root(tmp_path, source)
    result = validate_patch_proposal(
        _proposal(
            _edit(
                4,
                4,
                "    void run() {}",
                "    example.framework.SomeFrameworkAnnotation value;",
            )
        ),
        root,
        _evidence(4, 4),
    )
    assert result.passed
    assert result.java_import_checks[0].status == "pass"


def test_same_file_declaration_passes(tmp_path: Path) -> None:
    source = "package example;\n\nclass LocalAnnotation {}\n\npublic class App {\n    void run() {}\n}\n"
    root = _root(tmp_path, source)
    result = validate_patch_proposal(
        _proposal(_edit(6, 6, "    void run() {}", "    LocalAnnotation value;")),
        root,
        _evidence(6, 6),
    )
    assert result.passed
    assert result.java_import_checks[0].status == "pass"


def test_unknown_identifier_is_non_fatal(tmp_path: Path) -> None:
    source = "package example;\n\npublic class App {\n    void run() {}\n}\n"
    root = _root(tmp_path, source)
    result = validate_patch_proposal(
        _proposal(_edit(4, 4, "    void run() {}", "    returnValue = compute();")),
        root,
        _evidence(4, 4),
    )
    assert result.passed
    assert result.java_import_checks[0].status == "unknown"


def test_standalone_helper_returns_unknown_for_ambiguous_old_code() -> None:
    result = check_java_import_completeness(
        "void run() {}",
        "SomeFrameworkAnnotation value;",
        "void run() {}\nvoid run() {}\n",
    )
    assert result.status == "unknown"
