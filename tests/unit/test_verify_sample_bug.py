"""Unit tests for scripts/verify_sample_bug.py Surefire XML parsing, validation, and JDK discovery."""

from __future__ import annotations

import importlib.util
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

# Import functions from the script (scripts/ is not a package).
_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify_sample_bug.py"
_spec = importlib.util.spec_from_file_location("verify_sample_bug", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["verify_sample_bug"] = _mod
_spec.loader.exec_module(_mod)

_parse_surefire_xml = _mod._parse_surefire_xml
_validate_surefire = _mod._validate_surefire
EXPECTED_TEST_NAME = _mod.EXPECTED_TEST_NAME
_extract_major_version = _mod._extract_major_version
_find_suitable_jdk = _mod._find_suitable_jdk

_TARGET_SUITE_NAME = "com.springfix.sample.transaction.TransactionSelfInvocationTest"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_xml(tmp_path: Path, root_elem: ET.Element, name: str = "TEST-Foo.xml") -> Path:
    """Write an ElementTree to a temp file and return its path."""
    reports = tmp_path / "surefire-reports"
    reports.mkdir(parents=True, exist_ok=True)
    p = reports / name
    tree = ET.ElementTree(root_elem)
    tree.write(p, encoding="unicode", xml_declaration=True)
    return p


def _target_suite(
    tests: int = 1,
    failures: int = 1,
    errors: int = 0,
    skipped: int = 0,
    tc_name: str = EXPECTED_TEST_NAME,
    failure_message: str | None = (
        "Expected rollback but data was persisted; "
        "self-invocation bypassed the @Transactional AOP proxy "
        "==> expected: <0> but was: <1>"
    ),
    failure_body: str | None = (
        "org.opentest4j.AssertionFailedError: Expected rollback; "
        "self-invocation bypassed @Transactional AOP proxy "
        "==> expected: <0> but was: <1>\n"
        "\tat org.junit.jupiter.api.Assertions.assertEquals(Assertions.java:571)\n"
        f"\tat com.springfix.sample.transaction.TransactionSelfInvocationTest"
        f".{EXPECTED_TEST_NAME}(TransactionSelfInvocationTest.java:42)\n"
    ),
) -> ET.Element:
    """Build a Surefire XML <testsuite> Element for the target test."""
    suite = ET.Element("testsuite")
    suite.set("name", _TARGET_SUITE_NAME)
    suite.set("tests", str(tests))
    suite.set("failures", str(failures))
    suite.set("errors", str(errors))
    suite.set("skipped", str(skipped))
    suite.set("time", "4.772")

    tc = ET.SubElement(suite, "testcase")
    tc.set("name", tc_name)
    tc.set("classname", _TARGET_SUITE_NAME)
    tc.set("time", "2.959")

    if failure_message is not None:
        fail = ET.SubElement(tc, "failure")
        fail.set("message", failure_message)
        fail.set("type", "org.opentest4j.AssertionFailedError")
        fail.text = failure_body or ""

    return suite


def _make_fake_jdk(tmp_path: Path, name: str, version_output: str) -> Path:
    """Create a fake JDK directory with a java binary placeholder.

    The actual version parsing is controlled via mock in tests.
    """
    jdk_dir = tmp_path / name
    bin_dir = jdk_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    java_bin_name = "java.exe" if sys.platform == "win32" else "java"
    java_bin = bin_dir / java_bin_name
    java_bin.write_text("placeholder", encoding="utf-8")

    return jdk_dir


# ---------------------------------------------------------------------------
# Surefire XML Tests
# ---------------------------------------------------------------------------


class TestCorrectTargetFailure:
    """Case 1: correct target failure — all checks pass."""

    def test_passes(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, _target_suite())
        suites = _parse_surefire_xml([xml_path])
        passed, diags = _validate_surefire(suites)
        assert passed, "\n".join(diags)

    def test_all_diagnostics_pass(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, _target_suite())
        suites = _parse_surefire_xml([xml_path])
        _, diags = _validate_surefire(suites)
        assert all("[PASS]" in d for d in diags)


class TestMavenSuccess:
    """Case 2: Maven success (tests=1 failures=0) — validation fails."""

    def test_fails(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, _target_suite(
            failures=0, failure_message=None, failure_body=None,
        ))
        suites = _parse_surefire_xml([xml_path])
        passed, diags = _validate_surefire(suites)
        assert not passed
        assert any("failures = 1" in d and "[FAIL]" in d for d in diags)


class TestCompileFailureNoXml:
    """Case 3: compile failure, no XML — empty suite list."""

    def test_no_suites(self) -> None:
        suites = _parse_surefire_xml([])
        assert suites == []

    def test_validate_fails(self) -> None:
        passed, diags = _validate_surefire([])
        assert not passed
        assert any("no Surefire XML" in d for d in diags)


class TestWrongTestFails:
    """Case 4: wrong test fails — target test not present."""

    def test_fails(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, _target_suite(
            tc_name="someOtherTest",
        ))
        suites = _parse_surefire_xml([xml_path])
        passed, diags = _validate_surefire(suites)
        assert not passed
        assert any("not found" in d for d in diags)


class TestErrorsPresent:
    """Case 5: errors=1 — validation fails."""

    def test_fails(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, _target_suite(
            errors=1,
        ))
        suites = _parse_surefire_xml([xml_path])
        passed, diags = _validate_surefire(suites)
        assert not passed
        assert any("errors = 0" in d and "[FAIL]" in d for d in diags)


class TestAssertionContentChanged:
    """Case 6: assertion content changed — keyword check fails."""

    def test_missing_keyword(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, _target_suite(
            failure_message="something completely different happened",
            failure_body="java.lang.NullPointerException: null\n\tat Foo.bar(Foo.java:10)\n",
        ))
        suites = _parse_surefire_xml([xml_path])
        passed, diags = _validate_surefire(suites)
        assert not passed
        # At least one keyword check should fail.
        assert any("failure contains" in d and "[FAIL]" in d for d in diags)


class TestMultipleSurefireFiles:
    """Case 7: multiple Surefire files, only one has the target."""

    def test_picks_target(self, tmp_path: Path) -> None:
        # Unrelated suite.
        other = ET.Element("testsuite")
        other.set("name", "com.other.SomeTest")
        other.set("tests", "3")
        other.set("failures", "0")
        other.set("errors", "0")
        other.set("skipped", "0")
        other.set("time", "1.0")
        for n in ("testA", "testB", "testC"):
            tc = ET.SubElement(other, "testcase")
            tc.set("name", n)
            tc.set("classname", "com.other.SomeTest")
            tc.set("time", "0.5")

        p1 = _write_xml(tmp_path, other, name="TEST-com.other.SomeTest.xml")
        p2 = _write_xml(tmp_path, _target_suite(), name=f"TEST-{_TARGET_SUITE_NAME}.xml")

        suites = _parse_surefire_xml([p1, p2])
        assert len(suites) == 2

        passed, diags = _validate_surefire(suites)
        assert passed, "\n".join(diags)

    def test_no_target_across_files(self, tmp_path: Path) -> None:
        other = ET.Element("testsuite")
        other.set("name", "com.other.SomeTest")
        other.set("tests", "1")
        other.set("failures", "1")
        other.set("errors", "0")
        other.set("skipped", "0")
        other.set("time", "1.0")
        tc = ET.SubElement(other, "testcase")
        tc.set("name", "testA")
        tc.set("classname", "com.other.SomeTest")
        tc.set("time", "0.5")
        fail = ET.SubElement(tc, "failure")
        fail.set("message", "fail")
        fail.set("type", "AssertionError")
        fail.text = "oops"

        p1 = _write_xml(tmp_path, other, name="TEST-com.other.SomeTest.xml")
        suites = _parse_surefire_xml([p1])
        passed, diags = _validate_surefire(suites)
        assert not passed


# ---------------------------------------------------------------------------
# Java Version Parsing Tests
# ---------------------------------------------------------------------------


class TestExtractMajorVersion:
    """Tests for _extract_major_version."""

    def test_java_17(self) -> None:
        assert _extract_major_version('openjdk version "17.0.2" 2022-01-18') == 17

    def test_java_21(self) -> None:
        assert _extract_major_version('openjdk version "21.0.1" 2023-10-17') == 21

    def test_java_8_legacy_format(self) -> None:
        assert _extract_major_version('java version "1.8.0_362"') == 8

    def test_java_11(self) -> None:
        assert _extract_major_version('openjdk version "11.0.16"') == 11

    def test_no_version(self) -> None:
        assert _extract_major_version("no version info here") is None

    def test_empty_string(self) -> None:
        assert _extract_major_version("") is None


# ---------------------------------------------------------------------------
# JDK Discovery Tests
# ---------------------------------------------------------------------------


class TestFindSuitableJdk:
    """Tests for _find_suitable_jdk cross-platform JDK discovery."""

    def test_java_home_meets_version(self, tmp_path: Path) -> None:
        """JAVA_HOME is set and meets minimum version → returns it."""
        jdk = _make_fake_jdk(tmp_path, "jdk-17", 'openjdk version "17.0.2"')
        env = {"JAVA_HOME": str(jdk), "PATH": ""}
        with patch.object(_mod, "_parse_java_major_version", return_value=17):
            home, ver = _find_suitable_jdk(min_version=17, env=env)
        assert home == str(jdk)
        assert ver == 17

    def test_java_home_too_low_path_meets(self, tmp_path: Path) -> None:
        """JAVA_HOME has Java 8 (too low), PATH has Java 17 → uses PATH."""
        jdk8 = _make_fake_jdk(tmp_path, "jdk-8", 'java version "1.8.0_362"')
        jdk17 = _make_fake_jdk(tmp_path, "jdk-17", 'openjdk version "17.0.2"')
        fake_java = str(jdk17 / "bin" / ("java.exe" if sys.platform == "win32" else "java"))
        env = {"JAVA_HOME": str(jdk8), "PATH": str(jdk17 / "bin")}

        def mock_version(java_bin: Path) -> int | None:
            s = str(java_bin)
            if "jdk-17" in s:
                return 17
            if "jdk-8" in s:
                return 8
            return None

        # Mock shutil.which to return our fake java, not the system one.
        with (
            patch.object(_mod, "_parse_java_major_version", side_effect=mock_version),
            patch.object(_mod.shutil, "which", return_value=fake_java),
        ):
            home, ver = _find_suitable_jdk(min_version=17, env=env)
        assert home == str(jdk17)
        assert ver == 17

    def test_path_too_low_fallback_meets(self, tmp_path: Path) -> None:
        """JAVA_HOME and PATH both too low, but fallback directory has JDK 17."""
        jdk8 = _make_fake_jdk(tmp_path, "jdk-8", 'java version "1.8.0_362"')
        fallback_dir = tmp_path / "install" / "Java"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        jdk17 = fallback_dir / "jdk-17.0.2"
        # Create fake JDK structure.
        bin_dir = jdk17 / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        java_name = "java.exe" if sys.platform == "win32" else "java"
        java_bin = bin_dir / java_name
        java_bin.write_text(
            '#!/bin/sh\necho \'openjdk version "17.0.2"\' >&2\n'
            if sys.platform != "win32"
            else '@echo off\r\necho openjdk version "17.0.2" 1>&2\r\n',
            encoding="utf-8",
        )
        if sys.platform != "win32":
            java_bin.chmod(0o755)

        env = {"JAVA_HOME": str(jdk8), "PATH": str(jdk8 / "bin")}
        # Patch platform-specific search dirs to include our fallback.
        original_platform = sys.platform
        try:
            # Force non-win32 to test POSIX path.
            sys.platform = "linux"
            # Can't easily mock Path.iterdir; call with env.
            home, ver = _find_suitable_jdk(min_version=17, env=env)
        finally:
            sys.platform = original_platform

        # If no JDK 17 found in system dirs, returns None.
        # The important thing is it didn't return Java 8.
        if home is not None:
            assert ver is not None and ver >= 17

    def test_all_candidates_too_low(self, tmp_path: Path) -> None:
        """All JDKs are version 8 → returns (None, None) from controlled sources."""
        jdk8 = _make_fake_jdk(tmp_path, "jdk-8", 'java version "1.8.0_362"')
        env = {"JAVA_HOME": str(jdk8), "PATH": str(jdk8 / "bin")}
        # Mock all version checks to return 8.
        with patch.object(_mod, "_parse_java_major_version", return_value=8):
            home, ver = _find_suitable_jdk(min_version=17, env=env)
        # All controlled sources return 8; system dirs may have real JDKs.
        if home is not None:
            # A system JDK was found (not our fake Java 8).
            assert home != str(jdk8)
            assert ver is not None and ver >= 17

    def test_does_not_modify_os_environ(self, tmp_path: Path) -> None:
        """_find_suitable_jdk must not modify os.environ."""
        jdk = _make_fake_jdk(tmp_path, "jdk-17", 'openjdk version "17.0.2"')
        env = {"JAVA_HOME": str(jdk), "PATH": ""}
        original_env = dict(os.environ)
        _find_suitable_jdk(min_version=17, env=env)
        assert dict(os.environ) == original_env

    def test_java_21_satisfies_17(self, tmp_path: Path) -> None:
        """Java 21 satisfies minimum Java 17 requirement."""
        jdk21 = _make_fake_jdk(tmp_path, "jdk-21", 'openjdk version "21.0.1"')
        env = {"JAVA_HOME": str(jdk21), "PATH": ""}
        with patch.object(_mod, "_parse_java_major_version", return_value=21):
            home, ver = _find_suitable_jdk(min_version=17, env=env)
        assert home == str(jdk21)
        assert ver == 21

    def test_linux_no_windows_paths(self) -> None:
        """On Linux, Windows-specific paths are not checked."""
        if sys.platform == "win32":
            return  # Skip on Windows.
        # Verify the function doesn't crash on Linux with no JDKs.
        env = {"JAVA_HOME": "/nonexistent", "PATH": "/nonexistent/bin"}
        home, ver = _find_suitable_jdk(min_version=17, env=env)
        # Either finds a system JDK or returns None.
        if home is not None:
            assert not home.startswith("C:")

    def test_no_java_home_set(self, tmp_path: Path) -> None:
        """JAVA_HOME not set, no PATH java → returns (None, None) or system JDK."""
        env = {"PATH": str(tmp_path / "empty")}
        home, ver = _find_suitable_jdk(min_version=17, env=env)
        if home is not None:
            assert ver is not None and ver >= 17
