"""Schema, path, evidence, source, and safety tests for M5A."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from springfix_agent.repair.models import EvidenceSnippet, PatchEdit, PatchProposal
from springfix_agent.repair.validator import validate_patch_proposal


def _proposal(*edits: PatchEdit, status: str = "proposed") -> PatchProposal:
    return PatchProposal(
        status=status,  # type: ignore[arg-type]
        summary="minimal proposal",
        root_cause_reference="candidate:0",
        edits=list(edits),
    )


def _edit(file: str, start: int, end: int, old: str = "line two") -> PatchEdit:
    return PatchEdit(
        file=file,
        start_line=start,
        end_line=end,
        old_code=old,
        new_code="line changed",
        rationale="addresses the validated cause",
    )


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    (root / "src" / "main" / "java").mkdir(parents=True)
    (root / "src" / "main" / "resources").mkdir(parents=True)
    (root / "src" / "test").mkdir(parents=True)
    (root / "target").mkdir()
    (root / "src" / "main" / "java" / "App.java").write_text(
        "line one\nline two\nline three\nline four\n", encoding="utf-8"
    )
    (root / "src" / "main" / "resources" / "application.yml").write_text(
        "springfix:\n  email:\n", encoding="utf-8"
    )
    return root


def _evidence(file: str = "src/main/java/App.java", start: int = 2, end: int = 3) -> list[EvidenceSnippet]:
    return [
        EvidenceSnippet(
            file=file,
            start_line=start,
            end_line=end,
            content="line two\nline three",
        )
    ]


def test_valid_patch_edit_passes_and_normalizes_path(source_root: Path) -> None:
    result = validate_patch_proposal(
        _proposal(_edit("src\\main\\java\\App.java", 2, 2)), source_root, _evidence()
    )
    assert result.passed
    assert result.proposal.edits[0].file == "src/main/java/App.java"
    assert result.rejected_edit_count == 0


def test_schema_rejects_invalid_status_empty_edit_and_invalid_range() -> None:
    with pytest.raises(ValidationError):
        _proposal(status="invalid")
    with pytest.raises(ValidationError):
        PatchEdit(
            file="src/main/java/App.java",
            start_line=1,
            end_line=1,
            old_code="",
            new_code="x",
            rationale="r",
        )
    with pytest.raises(ValidationError):
        PatchEdit(
            file="src/main/java/App.java",
            start_line=3,
            end_line=2,
            old_code="x",
            new_code="y",
            rationale="r",
        )


@pytest.mark.parametrize(
    ("file", "reason"),
    [
        ("README.md", "path_not_allowed"),
        ("src/test/AppTest.java", "path_not_allowed"),
        ("target/App.java", "path_not_allowed"),
        ("../App.java", "path_not_allowed"),
    ],
)
def test_forbidden_paths_are_rejected(source_root: Path, file: str, reason: str) -> None:
    edit = _edit(file, 2, 2)
    result = validate_patch_proposal(_proposal(edit), source_root, _evidence())
    assert result.proposal.status == "insufficient_evidence"
    assert result.rejected_edits[0].reason == reason


def test_absolute_path_is_rejected(source_root: Path) -> None:
    result = validate_patch_proposal(
        _proposal(_edit(str((source_root / "src/main/java/App.java").resolve()), 2, 2)),
        source_root,
        _evidence(),
    )
    assert result.rejected_edits[0].reason == "path_not_allowed"


def test_resources_are_allowed(source_root: Path) -> None:
    edit = _edit("src/main/resources/application.yml", 2, 2, "  email:")
    result = validate_patch_proposal(
        _proposal(edit),
        source_root,
        [EvidenceSnippet(file=edit.file, start_line=1, end_line=2, content="springfix:\n  email:")],
    )
    assert result.passed


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        ([], "file_not_in_validated_evidence"),
        (_evidence("src/main/java/Other.java"), "file_not_in_validated_evidence"),
        (_evidence(start=4, end=4), "line_range_outside_evidence"),
    ],
)
def test_evidence_gate_rejects_wrong_or_outside_ranges(
    source_root: Path, evidence: list[EvidenceSnippet], reason: str
) -> None:
    result = validate_patch_proposal(_proposal(_edit("src/main/java/App.java", 2, 2)), source_root, evidence)
    assert result.rejected_edits[0].reason == reason


def test_old_code_exact_match_is_required(source_root: Path) -> None:
    result = validate_patch_proposal(
        _proposal(_edit("src/main/java/App.java", 2, 2, "line three")), source_root, _evidence()
    )
    assert result.rejected_edits[0].reason == "old_code_mismatch"


def test_crlf_old_code_is_normalized(source_root: Path) -> None:
    path = source_root / "src/main/java/App.java"
    path.write_bytes(b"line one\r\nline two\r\nline three\r\n")
    result = validate_patch_proposal(
        _proposal(_edit("src/main/java/App.java", 2, 2, "line two\r\n")), source_root, _evidence()
    )
    assert result.passed


def test_old_code_out_of_file_range_is_rejected(source_root: Path) -> None:
    result = validate_patch_proposal(
        _proposal(_edit("src/main/java/App.java", 99, 99, "line two")), source_root, _evidence(start=1, end=99)
    )
    assert result.rejected_edits[0].reason == "line_range_invalid"


@pytest.mark.parametrize(
    "new_code",
    [
        "new ProcessBuilder(\"bash\")",
        "Runtime.getRuntime().exec(\"curl x\")",
        "System.exit(1)",
        "Files.deleteIfExists(path)",
        "curl https://example.com",
        'String API_KEY = "sk-test-key-123456";',
    ],
)
def test_dangerous_new_code_is_rejected(source_root: Path, new_code: str) -> None:
    edit = _edit("src/main/java/App.java", 2, 2)
    edit = edit.model_copy(update={"new_code": new_code})
    result = validate_patch_proposal(_proposal(edit), source_root, _evidence())
    assert result.proposal.status == "unsafe_to_propose"
    assert result.rejected_edits[0].reason == "dangerous_new_code"


def test_normal_spring_annotation_is_allowed(source_root: Path) -> None:
    edit = _edit("src/main/java/App.java", 2, 2)
    edit = edit.model_copy(update={"new_code": "@Transactional\nline two"})
    result = validate_patch_proposal(_proposal(edit), source_root, _evidence())
    assert result.passed


def test_duplicate_conflicting_and_independent_edits(source_root: Path) -> None:
    duplicate = _edit("src/main/java/App.java", 2, 2)
    conflicting = _edit("src/main/java/App.java", 2, 3, "line two\nline three")
    independent = _edit("src/main/java/App.java", 4, 4, "line four")
    result = validate_patch_proposal(
        _proposal(duplicate, duplicate, conflicting, independent),
        source_root,
        [EvidenceSnippet(file="src/main/java/App.java", start_line=1, end_line=4, content="code")],
    )
    assert result.accepted_edit_count == 2
    assert {item.reason for item in result.rejected_edits} == {"duplicate_edit", "conflicting_edit"}
