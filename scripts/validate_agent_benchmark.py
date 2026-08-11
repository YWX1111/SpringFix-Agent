"""Validate the M4B manifest and its repository/evidence gold data.

The validator is deterministic and offline.  It never imports the graph, calls
an LLM, or passes gold fields to any agent component.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path, PureWindowsPath

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "benchmark" / "agent_cases.jsonl"
EXPECTED_CASE_IDS = {
    "transaction-self-invocation",
    "no-unique-bean-definition",
    "configuration-properties-prefix-mismatch",
}
_TEST_METHOD_RE = re.compile(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from springfix_agent.benchmark.loader import BenchmarkManifestError, load_cases  # noqa: E402
from springfix_agent.benchmark.models import BenchmarkCase  # noqa: E402


def _is_absolute_like(value: str) -> bool:
    """Recognize POSIX, UNC, and Windows absolute paths on every host."""
    return (
        Path(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or value.startswith(("/", "\\"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    )


def _has_parent_traversal(value: str) -> bool:
    """Reject parent components regardless of slash style."""
    return ".." in value.replace("\\", "/").split("/")


def _iter_strings(value: object) -> Iterable[str]:
    """Yield all string values from a nested manifest object."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _safe_relative_path(value: str, label: str, errors: list[str]) -> bool:
    """Check a manifest path before resolving it against the repository."""
    if _is_absolute_like(value):
        errors.append(f"{label} must be relative: {value}")
        return False
    if _has_parent_traversal(value):
        errors.append(f"{label} contains path traversal: {value}")
        return False
    if not value.strip():
        errors.append(f"{label} must not be blank")
        return False
    return True


def _resolve_relative(root: Path, value: str) -> Path:
    """Resolve a POSIX-style manifest path on the current operating system."""
    normalized = value.replace("\\", "/")
    return (root / Path(normalized)).resolve()


def _inside(path: Path, root: Path) -> bool:
    """Return whether a canonical path is inside a canonical root."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _repository_files(repo_path: Path) -> Iterable[Path]:
    """Yield source/config files while skipping build and VCS output."""
    excluded = {".git", "target", "build", ".idea", ".qoder"}
    for path in repo_path.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        yield path


def _contains_symbol(repo_path: Path, symbol: str) -> bool:
    """Find a gold symbol in real repository text, excluding documentation."""
    for path in _repository_files(repo_path):
        if path.name.lower() == "readme.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if symbol in text:
            return True
    return False


def _test_files(repo_path: Path) -> list[Path]:
    """Return Java test files used for the expected testcase lookup."""
    test_root = repo_path / "src" / "test"
    return sorted(test_root.rglob("*.java")) if test_root.is_dir() else []


def _validate_case(case: BenchmarkCase) -> list[str]:
    """Return all validation errors for one manifest case."""
    errors: list[str] = []
    payload = case.model_dump()
    for value in _iter_strings(payload):
        if _is_absolute_like(value):
            errors.append(f"manifest contains an absolute path-like value: {value}")
            break

    if not _safe_relative_path(case.repository, "repository", errors):
        return errors
    repo_path = _resolve_relative(PROJECT_ROOT, case.repository)
    samples_root = (PROJECT_ROOT / "samples").resolve()
    if not _inside(repo_path, samples_root):
        errors.append("repository must resolve inside samples/")
    if not repo_path.is_dir():
        errors.append(f"repository does not exist: {case.repository}")
        return errors
    if not (repo_path / "pom.xml").is_file():
        errors.append("repository is missing pom.xml")

    expected_paths: set[str] = set()
    for relative_file in case.expected_files:
        if not _safe_relative_path(relative_file, "expected_files entry", errors):
            continue
        expected_paths.add(relative_file.replace("\\", "/"))
        resolved = _resolve_relative(repo_path, relative_file)
        if not _inside(resolved, repo_path) or not resolved.is_file():
            errors.append(f"expected file does not exist: {relative_file}")

    for target in case.evidence_targets:
        if not _safe_relative_path(target.file, "evidence target file", errors):
            continue
        resolved = _resolve_relative(repo_path, target.file)
        if not _inside(resolved, repo_path) or not resolved.is_file():
            errors.append(f"evidence file does not exist: {target.file}")
            continue
        try:
            lines = resolved.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"cannot read evidence file {target.file}: {exc}")
            continue
        if target.end_line > len(lines):
            errors.append(
                f"evidence line range exceeds {target.file}: "
                f"{target.start_line}-{target.end_line}, file has {len(lines)} lines"
            )
            continue
        evidence_text = "\n".join(lines[target.start_line - 1 : target.end_line])
        for required_text in target.required_text:
            if required_text not in evidence_text:
                errors.append(
                    f"required_text not found in {target.file} lines "
                    f"{target.start_line}-{target.end_line}: {required_text}"
                )

    for symbol in case.expected_symbols:
        if not _contains_symbol(repo_path, symbol):
            errors.append(f"expected symbol not found in repository: {symbol}")

    test_files = _test_files(repo_path)
    if not test_files:
        errors.append("repository has no src/test Java file")
    elif not any(
        _TEST_METHOD_RE.search(path.read_text(encoding="utf-8"))
        and re.search(rf"\b{re.escape(case.expected_maven.test_name)}\s*\(", path.read_text(encoding="utf-8"))
        for path in test_files
    ):
        errors.append(
            f"expected Maven test is not locatable: {case.expected_maven.test_name}"
        )

    # This projection is an explicit guard against accidental gold leakage.
    agent_keys = set(case.agent_input())
    gold_keys = {
        "expected_issue_category",
        "expected_diagnosis_status",
        "expected_root_cause_keywords",
        "expected_files",
        "expected_symbols",
        "evidence_targets",
        "expected_maven",
    }
    if agent_keys & gold_keys:
        errors.append("agent input projection contains benchmark gold fields")
    return errors


def validate_manifest(manifest_path: Path = DEFAULT_MANIFEST) -> tuple[bool, list[str]]:
    """Validate the complete manifest and return printable diagnostics."""
    try:
        cases = load_cases(manifest_path)
    except BenchmarkManifestError as exc:
        return False, [f"manifest load failed: {exc}"]

    diagnostics: list[str] = []
    all_ok = True
    case_ids = {case.case_id for case in cases}
    if len(cases) != 3:
        diagnostics.append(f"[FAIL] expected exactly 3 cases, found {len(cases)}")
        all_ok = False
    missing = sorted(EXPECTED_CASE_IDS - case_ids)
    unexpected = sorted(case_ids - EXPECTED_CASE_IDS)
    if missing:
        diagnostics.append(f"[FAIL] missing required case(s): {', '.join(missing)}")
        all_ok = False
    if unexpected:
        diagnostics.append(f"[FAIL] unexpected case(s): {', '.join(unexpected)}")
        all_ok = False

    for case in cases:
        errors = _validate_case(case)
        if errors:
            all_ok = False
            diagnostics.append(f"[FAIL] {case.case_id}")
            diagnostics.extend(f"  - {error}" for error in errors)
        else:
            diagnostics.append(f"[PASS] {case.case_id}")
    return all_ok, diagnostics


def main() -> int:
    """CLI entrypoint for deterministic manifest validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    passed, diagnostics = validate_manifest(args.manifest.resolve())
    print(f"Manifest: {args.manifest}")
    for diagnostic in diagnostics:
        print(diagnostic)
    if passed:
        print("Agent benchmark manifest validated")
        return 0
    print("Agent benchmark manifest validation failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
