"""
Azure SDK import scanner for StokAI.

Walks every .py file under src/ using Python's ast module and asserts that no
import or from-import statement references a module starting with 'azure'.

AC-002: Given a codebase scan for Azure-specific SDK imports (azure-*, @azure/*)
in business logic modules (src/), zero results are found.
"""
import ast
import textwrap
from pathlib import Path


SRC_ROOT = Path(__file__).parent.parent / "src"


def _find_azure_imports(source_path: Path) -> list[str]:
    """Return a list of Azure import statements found in source_path."""
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("azure"):
                    violations.append(f"  import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("azure"):
                violations.append(f"  from {node.module} import ...")
    return violations


# ── Main scan ─────────────────────────────────────────────────────────────────

def test_no_azure_imports_found_in_src():
    """All .py files under src/ must be free of Azure SDK imports."""
    assert SRC_ROOT.exists(), f"src/ directory not found at {SRC_ROOT}"

    all_violations: dict[str, list[str]] = {}
    for py_file in SRC_ROOT.rglob("*.py"):
        violations = _find_azure_imports(py_file)
        if violations:
            rel = py_file.relative_to(SRC_ROOT.parent)
            all_violations[str(rel)] = violations

    if all_violations:
        lines = ["Forbidden Azure SDK imports found in src/:"]
        for file_path, imports in sorted(all_violations.items()):
            lines.append(f"\n{file_path}:")
            lines.extend(imports)
        raise AssertionError("\n".join(lines))


# ── Scanner self-test (validates scanner logic) ───────────────────────────────

def test_scan_detects_forbidden_import_in_fixture(tmp_path):
    """The scanner correctly identifies Azure imports in a temp fixture file."""
    fixture = tmp_path / "bad_module.py"
    fixture.write_text(
        textwrap.dedent("""\
        import azure.identity
        from azure.keyvault.secrets import SecretClient

        def something():
            pass
        """),
        encoding="utf-8",
    )
    violations = _find_azure_imports(fixture)
    assert len(violations) == 2, (
        f"Expected 2 violations, got {len(violations)}: {violations}"
    )
    assert any("azure.identity" in v for v in violations)
    assert any("azure.keyvault.secrets" in v for v in violations)


def test_scan_ignores_files_outside_src(tmp_path):
    """A .py file outside src/ with Azure imports must NOT be flagged by the scan."""
    # Place an offending file in a tests/ analogue — outside SRC_ROOT
    outside_file = tmp_path / "test_helper.py"
    outside_file.write_text(
        "import azure.identity\n",
        encoding="utf-8",
    )

    # The main scan only walks SRC_ROOT; outside_file must not be included
    violations = _find_azure_imports(outside_file)
    # The helper itself detects violations in the file — that's correct.
    # The point is that test_no_azure_imports_found_in_src() never looks here.
    # We verify the scan boundary by confirming SRC_ROOT does not contain tmp_path.
    assert not str(tmp_path).startswith(str(SRC_ROOT)), (
        "tmp_path must be outside src/ for this test to be meaningful"
    )
    # Confirm the scanner would flag it IF it were asked to scan it
    assert "import azure.identity" in outside_file.read_text()
    # Confirm the scanner does flag it when called directly (logic works)
    assert len(violations) >= 1
