"""
Static analysis gate: Bandit + grep for hardcoded config/credentials.

PLAN-N-008 TASK-005 — TDD: tests written before src/ contains violations.
On a clean src/ tree these tests pass immediately.
As other plans add source files, these tests act as a ratchet.

Bandit rules enforced:
  B105 — hardcoded password string
  B106 — hardcoded password function argument
  B107 — hardcoded password in function default

Custom grep patterns (each is a parameterised test case):
  - No 'localhost' literal in src/ Python files
  - No '127.0.0.1' literal in src/ Python files
  - No 'postgres://' or 'postgresql://' URI scheme in src/ Python files
  - No 'redis://' URI scheme in src/ Python files
  - No 'http://localhost' in src/ Python files
  - No hardcoded JWT secret pattern (SECRET_KEY = "...") in src/

Acceptance criteria: AC-005 (zero hardcoded connection strings, credentials, or
env-specific values in src/)

DEV-STANDARDS §8: Secrets only in environment variables; never in source or
committed config.
Architecture P-06: No hardcoded configuration.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

# ---------------------------------------------------------------------------
# Bandit scan parameters
# ---------------------------------------------------------------------------

BANDIT_TARGETS = ["B105", "B106", "B107"]

# ---------------------------------------------------------------------------
# Custom grep patterns — each becomes a separate parametrised test case.
# pattern: human-readable name -> (regex, description)
# ---------------------------------------------------------------------------

GREP_PATTERNS: list[tuple[str, str, str]] = [
    (
        "no_localhost_literal",
        r"[\"'].*localhost.*[\"']",
        "No 'localhost' string literal in src/ Python files "
        "(use env-var references instead — P-06, DEV-STANDARDS §8)",
    ),
    (
        "no_127_0_0_1",
        r"[\"'].*127\.0\.0\.1.*[\"']",
        "No '127.0.0.1' hardcoded string literal in src/ Python files",
    ),
    (
        "no_postgres_uri",
        r"[\"']postgresql?://[^\"']*[\"']",
        "No 'postgres://' or 'postgresql://' URI scheme string literal in src/ Python files",
    ),
    (
        "no_redis_uri",
        r"[\"']redis://[^\"']*[\"']",
        "No 'redis://' URI scheme string literal in src/ Python files",
    ),
    (
        "no_http_localhost",
        r"[\"']http://localhost[^\"']*[\"']",
        "No 'http://localhost' hardcoded string literal in src/ Python files",
    ),
    (
        "no_hardcoded_secret_key",
        r'(SECRET_KEY|JWT_SECRET_KEY)\s*=\s*["\'][^${\(]',
        "No hardcoded JWT/secret key assignment in src/ Python files "
        "(must use os.environ or pydantic-settings — DEV-STANDARDS §8)",
    ),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _collect_py_files(root: Path) -> list[Path]:
    """Return all .py files under root."""
    if not root.exists():
        return []
    return sorted(root.rglob("*.py"))


def _is_comment_or_docstring_example_line(line: str) -> bool:
    """Return True if the line is a comment or a docstring example placeholder.

    This prevents false positives on documentation-only strings that describe
    URI format without actually using them as values.

    Heuristics (conservative — real code-assignment lines pass through):
    - Line stripped starts with '#' (Python line comment)
    - Line stripped starts with '``' (reST inline code in a docstring)
    - Line contains a string literal ending in '...' (placeholder example)
      e.g.:  factory = CheckpointerFactory(db_url="postgresql://...")
    """
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    if stripped.startswith("``") and stripped.endswith("``"):
        return True
    # Placeholder example pattern: the string value ends with '...' (clearly not real)
    if re.search(r'["\'](?:postgresql?|redis|http)://[^"\']*\.\.\.["\']', stripped):
        return True
    return False


def _scan_file_for_pattern(path: Path, compiled: re.Pattern) -> list[tuple[int, str]]:
    """Return list of (line_number, line_text) where the pattern matches.

    Excludes pure comment lines and docstring example stubs to reduce false positives.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    hits = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if _is_comment_or_docstring_example_line(line):
            continue
        if compiled.search(line):
            hits.append((lineno, line.rstrip()))
    return hits


# ---------------------------------------------------------------------------
# Bandit scan test
# ---------------------------------------------------------------------------

class TestBanditScanPasses:
    """
    Run Bandit against src/ and assert zero B105/B106/B107 findings.

    Bandit is run in a subprocess so its exit code and JSON output are captured
    independently of the pytest process.
    """

    def test_bandit_scan_passes(self) -> None:
        if not SRC_ROOT.exists():
            pytest.skip("src/ directory does not exist yet — greenfield pass")

        py_files = _collect_py_files(SRC_ROOT)
        if not py_files:
            pytest.skip("src/ has no .py files yet — greenfield pass")

        cmd = [
            sys.executable, "-m", "bandit",
            "-r", str(SRC_ROOT),
            "-t", ",".join(BANDIT_TARGETS),
            "--exit-zero",   # always exit 0 — we inspect JSON output ourselves
            "-f", "json",
            "-q",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )

        # Parse JSON output
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"Bandit JSON output could not be parsed: {exc}\n"
                f"stdout: {result.stdout[:2000]}\n"
                f"stderr: {result.stderr[:2000]}"
            )

        findings = report.get("results", [])
        high_findings = [
            {
                "file": f.get("filename"),
                "line": f.get("line_number"),
                "test_id": f.get("test_id"),
                "issue_text": f.get("issue_text"),
                "code": f.get("code"),
            }
            for f in findings
            if f.get("test_id") in BANDIT_TARGETS
        ]

        assert not high_findings, (
            f"Bandit found {len(high_findings)} hardcoded password/secret finding(s) "
            f"in src/ (B105/B106/B107). Findings:\n"
            + "\n".join(
                f"  [{h['test_id']}] {h['file']}:{h['line']} — {h['issue_text']}"
                for h in high_findings
            )
        )


# ---------------------------------------------------------------------------
# Custom grep pattern tests (parameterised)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pattern_id,pattern,description",
    GREP_PATTERNS,
    ids=[p[0] for p in GREP_PATTERNS],
)
class TestNoHardcodedLiterals:
    """
    Parameterised tests — one per custom grep pattern.
    Each test scans all .py files under src/ and asserts zero matches.

    These tests pass on a clean src/ directory and enforce invariants as
    source files are added by subsequent plans.
    """

    def test_no_hardcoded_literals(
        self,
        pattern_id: str,
        pattern: str,
        description: str,
    ) -> None:
        if not SRC_ROOT.exists():
            pytest.skip("src/ directory does not exist yet — greenfield pass")

        py_files = _collect_py_files(SRC_ROOT)
        if not py_files:
            pytest.skip("src/ has no .py files yet — greenfield pass")

        compiled = re.compile(pattern)
        offenders: list[tuple[str, list[tuple[int, str]]]] = []

        for py_file in py_files:
            hits = _scan_file_for_pattern(py_file, compiled)
            if hits:
                offenders.append((str(py_file.relative_to(PROJECT_ROOT)), hits))

        assert not offenders, (
            f"Hardcoded config violation [{pattern_id}]: {description}\n"
            f"Pattern: {pattern!r}\n"
            f"Matches found in src/:\n"
            + "\n".join(
                f"  {filepath}:\n" + "\n".join(
                    f"    line {lineno}: {line}"
                    for lineno, line in hits
                )
                for filepath, hits in offenders
            )
        )
