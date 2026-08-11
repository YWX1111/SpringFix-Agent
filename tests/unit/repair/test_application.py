"""M5B isolated workspace, applier, encoding, diff, and runner tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from springfix_agent.repair.application_models import PatchApplicationResult
from springfix_agent.repair.application_runner import PatchApplicationRunner
from springfix_agent.repair.applier import PatchApplier
from springfix_agent.repair.diff import generate_unified_diff
from springfix_agent.repair.models import (
    EvidenceSnippet,
    PatchEdit,
    PatchProposal,
    PatchValidationResult,
)
from springfix_agent.repair.validator import validate_patch_proposal
from springfix_agent.repair.workspace import (
    compute_sha256_manifest,
    create_isolated_patch_workspace,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _edit(file: str, start: int, end: int, old: str, new: str) -> PatchEdit:
    return PatchEdit(
        file=file,
        start_line=start,
        end_line=end,
        old_code=old,
        new_code=new,
        rationale="deterministic M5B test edit",
    )


def _proposal(*edits: PatchEdit) -> PatchProposal:
    return PatchProposal(
        status="proposed",
        summary="test proposal",
        root_cause_reference="candidate:0",
        edits=list(edits),
    )


def _repository(tmp_path: Path, *, text: str = "one\ntwo\nthree\nfour\nfive\n") -> Path:
    root = tmp_path / "repository"
    java = root / "src" / "main" / "java" / "App.java"
    java.parent.mkdir(parents=True)
    java.write_text(text, encoding="utf-8")
    (root / "src" / "main" / "resources").mkdir(parents=True)
    (root / "src" / "main" / "resources" / "application.yml").write_text(
        "springfix:\n  mail:\n", encoding="utf-8"
    )
    (root / "src" / "test").mkdir(parents=True)
    (root / "src" / "test" / "AppTest.java").write_text("class AppTest {}\n", encoding="utf-8")
    (root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (root / "README.md").write_text("answer-bearing documentation\n", encoding="utf-8")
    for directory in (".git", "target", "build", "node_modules", "artifacts", "benchmark"):
        (root / directory).mkdir()
        (root / directory / "hidden.txt").write_text("excluded\n", encoding="utf-8")
    (root / "compiled.class").write_bytes(b"excluded")
    (root / "archive.jar").write_bytes(b"excluded")
    (root / "debug.log").write_text("excluded\n", encoding="utf-8")
    return root


def _validated(root: Path, *edits: PatchEdit) -> PatchValidationResult:
    evidence = [
        EvidenceSnippet(file=edit.file, start_line=1, end_line=50, content="fixture")
        for edit in edits
    ]
    return validate_patch_proposal(_proposal(*edits), root, evidence)


def _manual_validation(*edits: PatchEdit) -> PatchValidationResult:
    proposal = _proposal(*edits)
    return PatchValidationResult(
        proposal=proposal,
        original_edit_count=len(edits),
        accepted_edit_count=len(edits),
    )


def _apply(root: Path, validation: PatchValidationResult) -> PatchApplicationResult:
    with create_isolated_patch_workspace(root) as workspace:
        result = PatchApplier().apply(validation, workspace)
        assert workspace.path is not None
        result = result.model_copy(update={"workspace_cleaned": True})
        assert result.original_repository_unchanged
    return result


def test_workspace_copies_project_content_and_cleans_up(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    before = compute_sha256_manifest(root)
    with create_isolated_patch_workspace(root) as workspace:
        assert workspace.path is not None
        copied = {path.relative_to(workspace.path).as_posix() for path in workspace.path.rglob("*")}
        assert "pom.xml" in copied
        assert "src/main/java/App.java" in copied
        assert "src/main/resources/application.yml" in copied
        assert "src/test/AppTest.java" in copied
        assert "README.md" not in copied
        assert "compiled.class" not in copied
        assert "debug.log" not in copied
        assert all(not name.startswith(".git/") for name in copied)
        assert all(not name.startswith("target/") for name in copied)
        temporary_root = workspace.path.parent
    assert workspace.path is None
    assert not temporary_root.exists()
    assert compute_sha256_manifest(root) == before


def test_manifest_detects_source_mutation_addition_and_deletion(tmp_path: Path) -> None:
    for operation in ("mutate", "add", "delete"):
        root = _repository(tmp_path / operation)
        validation = _validated(root, _edit("src/main/java/App.java", 2, 2, "two", "changed"))
        with create_isolated_patch_workspace(root) as workspace:
            if operation == "mutate":
                (root / "src/main/java/App.java").write_text("changed source\n", encoding="utf-8")
            elif operation == "add":
                (root / "new.txt").write_text("new\n", encoding="utf-8")
            else:
                (root / "pom.xml").unlink()
            result = PatchApplier().apply(validation, workspace)
            assert not result.original_repository_unchanged
            assert result.status == "rejected"
            assert result.workspace_integrity == "failed"


def test_valid_application_is_all_or_nothing_and_preserves_source(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    before = compute_sha256_manifest(root)
    result = _apply(root, _validated(root, _edit("src/main/java/App.java", 2, 2, "two", "changed")))
    assert result.status == "applied"
    assert result.edits_requested == result.edits_applied == 1
    assert result.edits_rejected == 0
    assert result.changed_files == ["src/main/java/App.java"]
    assert result.unified_diff.startswith("--- a/src/main/java/App.java")
    assert compute_sha256_manifest(root) == before


def test_unvalidated_proposal_is_rejected_without_writes(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    before = (root / "src/main/java/App.java").read_bytes()
    invalid = validate_patch_proposal(
        _proposal(_edit("src/main/java/App.java", 2, 2, "two", "changed")), root, []
    )
    result = _apply(root, invalid)
    assert result.status == "rejected"
    assert result.application_error == "proposal_not_validated"
    assert (root / "src/main/java/App.java").read_bytes() == before


@pytest.mark.parametrize(
    ("reason", "edit"),
    [
        ("new_file_not_supported", _edit("src/main/java/Missing.java", 1, 1, "x", "y")),
        ("invalid_range", _edit("src/main/java/App.java", 1, 99, "one", "y")),
        ("path_not_allowed", _edit("src/test/AppTest.java", 1, 1, "class AppTest {}", "x")),
        ("path_not_allowed", _edit("README.md", 1, 1, "x", "y")),
    ],
)
def test_preflight_rejects_invalid_edit_without_writing(
    tmp_path: Path, reason: str, edit: PatchEdit
) -> None:
    root = _repository(tmp_path)
    result = _apply(root, _manual_validation(edit))
    assert result.status == "rejected"
    assert result.edits_applied == 0
    assert result.rejected_edits[0].reason == reason


def test_stale_old_code_is_rejected_against_temporary_snapshot(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    validation = _validated(root, _edit("src/main/java/App.java", 2, 2, "two", "changed"))
    with create_isolated_patch_workspace(root) as workspace:
        assert workspace.path is not None
        (workspace.path / "src/main/java/App.java").write_text(
            "one\nchanged elsewhere\nthree\nfour\nfive\n", encoding="utf-8"
        )
        result = PatchApplier().apply(validation, workspace)
        assert result.status == "rejected"
        assert result.rejected_edits[0].reason == "stale_patch"


def test_same_file_edits_use_descending_original_line_order(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    edits = (
        _edit("src/main/java/App.java", 1, 1, "one", "one\ninserted"),
        _edit("src/main/java/App.java", 5, 5, "five", "FIVE"),
    )
    with create_isolated_patch_workspace(root) as workspace:
        assert workspace.path is not None
        result = PatchApplier().apply(_validated(root, *edits), workspace)
        assert result.status == "applied"
        assert (workspace.path / "src/main/java/App.java").read_text(encoding="utf-8") == (
            "one\ninserted\ntwo\nthree\nfour\nFIVE\n"
        )


def test_two_files_and_adjacent_ranges_are_allowed(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    edits = (
        _edit("src/main/java/App.java", 1, 1, "one", "ONE"),
        _edit("src/main/java/App.java", 2, 2, "two", "TWO"),
        _edit("src/main/resources/application.yml", 2, 2, "  mail:", "  email:"),
    )
    result = _apply(root, _validated(root, *edits))
    assert result.status == "applied"
    assert result.edits_applied == 3
    assert result.changed_files == ["src/main/java/App.java", "src/main/resources/application.yml"]


def test_overlapping_and_duplicate_edits_reject_the_whole_proposal(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    overlapping = (
        _edit("src/main/java/App.java", 2, 3, "two\nthree", "x"),
        _edit("src/main/java/App.java", 3, 4, "three\nfour", "y"),
    )
    result = _apply(root, _manual_validation(*overlapping))
    assert result.status == "rejected"
    assert result.edits_applied == 0
    assert {item.reason for item in result.rejected_edits} >= {"conflicting_edit"}

    duplicate_root = _repository(tmp_path / "duplicate")
    duplicate = _edit("src/main/java/App.java", 2, 2, "two", "changed")
    duplicate_result = _apply(duplicate_root, _manual_validation(duplicate, duplicate))
    assert duplicate_result.status == "rejected"
    assert {item.reason for item in duplicate_result.rejected_edits} >= {"duplicate_edit"}


@pytest.mark.parametrize(
    ("raw", "expected_newline", "expected_trailing", "bom"),
    [
        (b"one\ntwo\n", b"\n", True, False),
        (b"one\r\ntwo\r\n", b"\r\n", True, False),
        (b"one\ntwo", b"\n", False, False),
        (b"\xef\xbb\xbfone\ntwo\n", b"\n", True, True),
    ],
)
def test_encoding_newline_trailing_and_bom_state_are_preserved(
    tmp_path: Path, raw: bytes, expected_newline: bytes, expected_trailing: bool, bom: bool
) -> None:
    root = _repository(tmp_path, text="placeholder\n")
    path = root / "src/main/java/App.java"
    path.write_bytes(raw)
    old = "one\ntwo" if b"two" in raw else "one"
    edit = _edit("src/main/java/App.java", 1, 1, old.split("\n")[0], "changed")
    result = _apply(root, _manual_validation(edit))
    assert result.status == "applied"
    with create_isolated_patch_workspace(root) as workspace:
        assert workspace.path is not None
        copied = workspace.path / "src/main/java/App.java"
        copied_bytes = copied.read_bytes()
        assert copied_bytes.startswith(b"\xef\xbb\xbf") is bom
        body = copied_bytes[3:] if bom else copied_bytes
        assert expected_newline in body
        assert body.endswith(b"\n") is expected_trailing


def test_unsupported_encoding_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    path = root / "src/main/java/App.java"
    path.write_bytes(b"one\n\xff\n")
    edit = _edit("src/main/java/App.java", 1, 1, "one", "changed")
    with create_isolated_patch_workspace(root) as workspace:
        result = PatchApplier().apply(_manual_validation(edit), workspace)
        assert result.status == "rejected"
        assert result.rejected_edits[0].reason == "unsupported_encoding"


def test_atomic_write_failure_does_not_touch_source_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path)
    before = compute_sha256_manifest(root)
    import springfix_agent.repair.applier as applier_module

    def fail(_path: Path, _payload: bytes) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(applier_module, "_atomic_write", fail)
    result = _apply(root, _validated(root, _edit("src/main/java/App.java", 2, 2, "two", "changed")))
    assert result.status == "rejected"
    assert result.application_error == "atomic_write_failed: OSError"
    assert compute_sha256_manifest(root) == before


def test_unified_diff_is_relative_changed_only_and_deterministic() -> None:
    before = {"src/main/A.java": "one\ntwo\n", "src/main/B.java": "same\n"}
    after = {"src/main/A.java": "one\nchanged\n", "src/main/B.java": "same\n"}
    first = generate_unified_diff(before, after)
    second = generate_unified_diff(before, after)
    assert first == second
    assert "a/src/main/A.java" in first
    assert "b/src/main/A.java" in first
    assert "B.java" not in first
    assert "springfix-patch-" not in first


def test_m5b_mock_runner_applies_three_cases_and_keeps_samples_unchanged(tmp_path: Path) -> None:
    sample_roots = [
        PROJECT_ROOT / "samples" / "sample-springboot-bug-transaction-self-invocation",
        PROJECT_ROOT / "samples" / "sample-springboot-bug-no-unique-bean-definition",
        PROJECT_ROOT / "samples" / "sample-springboot-bug-configuration-properties-prefix-mismatch",
    ]
    before = {str(root): compute_sha256_manifest(root) for root in sample_roots}
    result = PatchApplicationRunner(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "benchmark/agent_cases.jsonl",
        repair_gold_path=PROJECT_ROOT / "benchmark/repair_gold.jsonl",
        output_dir=tmp_path / "artifacts",
        mode="mock",
    ).run()
    assert result.aggregate.sample_size == 3
    assert result.aggregate.application_success_rate == 1.0
    assert result.aggregate.all_edits_applied_rate == 1.0
    assert result.aggregate.original_repository_integrity_rate == 1.0
    assert result.aggregate.diff_generation_rate == 1.0
    assert result.aggregate.workspace_cleanup_rate == 1.0
    for root in sample_roots:
        assert compute_sha256_manifest(root) == before[str(root)]
    summary = (tmp_path / "artifacts/mock/summary.json").read_text(encoding="utf-8")
    assert "springfix-patch-" not in summary
    assert "acceptable_change_concepts" not in summary


def test_application_artifact_is_structured_and_does_not_embed_diff(tmp_path: Path) -> None:
    result = PatchApplicationRunner(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "benchmark/agent_cases.jsonl",
        repair_gold_path=PROJECT_ROOT / "benchmark/repair_gold.jsonl",
        output_dir=tmp_path / "artifacts",
        mode="mock",
        case_id="configuration-properties-prefix-mismatch",
    ).run()
    assert result.cases[0].expected_changed_file_hit
    payload = json.loads(
        (tmp_path / "artifacts/mock/configuration-properties-prefix-mismatch/application.json")
        .read_text(encoding="utf-8")
    )
    assert payload["status"] == "applied"
    assert payload["changed_files"] == ["src/main/resources/application.yml"]
    assert "unified_diff" not in payload
    assert (tmp_path / "artifacts/mock/configuration-properties-prefix-mismatch/patch.diff").read_text(
        encoding="utf-8"
    ).startswith("--- a/")


def test_proposal_file_true_flag_does_not_skip_m5a_validation(tmp_path: Path) -> None:
    file = "src/main/java/com/springfix/sample/transaction/service/OrderService.java"
    source = PROJECT_ROOT / "samples/sample-springboot-bug-transaction-self-invocation"
    source_lines = (source / file).read_text(encoding="utf-8").splitlines()
    proposal = _proposal(
        _edit(
            file,
            31,
            31,
            "    public void createOrder() {",
            "    @Transactional\n    public void createOrder() {",
        )
    )
    evidence = EvidenceSnippet(
        file=file,
        start_line=31,
        end_line=37,
        content="\n".join(source_lines[30:37]),
    )
    proposal_file = tmp_path / "proposal.json"
    proposal_file.write_text(
        json.dumps(
            {
                "validated": True,
                "proposal": proposal.model_dump(),
                "validated_evidence": [evidence.model_dump()],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = PatchApplicationRunner(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "benchmark/agent_cases.jsonl",
        repair_gold_path=PROJECT_ROOT / "benchmark/repair_gold.jsonl",
        output_dir=tmp_path / "artifacts",
        mode="mock",
        case_id="transaction-self-invocation",
        proposal_file=proposal_file,
    ).run()
    assert result.cases[0].proposal_valid
    assert result.cases[0].application_status == "applied"
