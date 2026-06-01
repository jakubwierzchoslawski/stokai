"""
Azure isolation verification test.

PLAN-N-008 TASK-003 — Architecture P-10: No Azure-specific code in MVP default path.
Decision D6: Docker Compose primary; no Azure-specific code.
Decision C-005: Anthropic-only LLM in MVP; no Azure OpenAI.

This test verifies that the azure_vault_provider module (the ONLY permitted
Azure file) is not imported anywhere in the default code path. It scans all
.py files under src/ (excluding the azure vault provider itself) for azure
import lines.

Passes immediately on a greenfield or clean src/ directory.
Acts as a ratchet as other plans add source files.

Acceptance criteria: AC-002 (no Azure SDK in default code path)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

AZURE_VAULT_PROVIDER_PATH = SRC_ROOT / "providers" / "vault" / "azure_vault_provider.py"

# Pattern to detect azure-related import lines (case-insensitive)
# Matches: import azure, from azure, import azure_identity, etc.
AZURE_IMPORT_PATTERN = re.compile(
    r"^\s*(import|from)\s+(azure|azure[\.\-]identity|azure[\.\-]keyvault)",
    re.IGNORECASE | re.MULTILINE,
)

# azure_vault_provider.py is the ONLY permitted Azure file —
# but it must NOT appear in any __init__.py or module-level import in src/.
AZURE_VAULT_IMPORT_PATTERN = re.compile(
    r"azure_vault_provider",
    re.IGNORECASE,
)


def _collect_py_files(root: Path, exclude: Path | None = None) -> list[Path]:
    """Recursively collect all .py files under root, optionally excluding one path."""
    files = []
    for path in root.rglob("*.py"):
        if exclude is not None and path.resolve() == exclude.resolve():
            continue
        files.append(path)
    return sorted(files)


def _collect_init_files(root: Path) -> list[Path]:
    """Collect all __init__.py files under root."""
    return sorted(root.rglob("__init__.py"))


class TestNoAzureImportInDefaultCodePath:
    """
    Assert that no .py file under src/ (except azure_vault_provider.py itself)
    contains an import line referencing azure, azure-identity, or azure-keyvault.
    """

    def test_no_azure_import_in_src_excluding_vault_provider(self) -> None:
        if not SRC_ROOT.exists():
            pytest.skip("src/ directory does not exist yet — greenfield pass")

        py_files = _collect_py_files(SRC_ROOT, exclude=AZURE_VAULT_PROVIDER_PATH)
        offenders: list[tuple[str, list[int]]] = []

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            hits = []
            for lineno, line in enumerate(content.splitlines(), start=1):
                if AZURE_IMPORT_PATTERN.match(line):
                    hits.append(lineno)

            if hits:
                offenders.append((str(py_file.relative_to(PROJECT_ROOT)), hits))

        assert not offenders, (
            "Azure SDK imports found in default code path (P-10 violation). "
            "Azure imports are only permitted in src/providers/vault/azure_vault_provider.py. "
            f"Offending files: {offenders}"
        )

    def test_azure_vault_provider_not_imported_in_inits(self) -> None:
        """
        azure_vault_provider.py must not be imported in any __init__.py or
        module-level import elsewhere in src/. It must remain an optional,
        non-imported module (architecture P-10).
        """
        if not SRC_ROOT.exists():
            pytest.skip("src/ directory does not exist yet — greenfield pass")

        init_files = _collect_init_files(SRC_ROOT)
        offenders: list[tuple[str, list[int]]] = []

        for init_file in init_files:
            try:
                content = init_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            hits = []
            for lineno, line in enumerate(content.splitlines(), start=1):
                if AZURE_VAULT_IMPORT_PATTERN.search(line):
                    hits.append(lineno)

            if hits:
                offenders.append((str(init_file.relative_to(PROJECT_ROOT)), hits))

        assert not offenders, (
            "azure_vault_provider is imported in __init__.py files — this violates P-10. "
            "The azure vault provider must never appear in default import paths. "
            f"Offending files: {offenders}"
        )

    def test_azure_vault_provider_not_in_any_src_module_import(self) -> None:
        """
        No .py file under src/ (other than azure_vault_provider.py itself) may
        reference 'azure_vault_provider' in an import statement.
        """
        if not SRC_ROOT.exists():
            pytest.skip("src/ directory does not exist yet — greenfield pass")

        py_files = _collect_py_files(SRC_ROOT, exclude=AZURE_VAULT_PROVIDER_PATH)
        offenders: list[tuple[str, list[int]]] = []

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            hits = []
            for lineno, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                # Only flag import lines that reference the azure vault provider
                if (stripped.startswith("import") or stripped.startswith("from")) and \
                        AZURE_VAULT_IMPORT_PATTERN.search(stripped):
                    hits.append(lineno)

            if hits:
                offenders.append((str(py_file.relative_to(PROJECT_ROOT)), hits))

        assert not offenders, (
            "azure_vault_provider is referenced in import statements outside of "
            "src/providers/vault/azure_vault_provider.py (P-10 violation). "
            f"Offending files: {offenders}"
        )

    def test_azure_vault_provider_file_location_is_correct(self) -> None:
        """
        If azure_vault_provider.py exists, it must be located at
        src/providers/vault/azure_vault_provider.py — nowhere else.
        This prevents accidental placement in a default-loaded location.
        """
        if not SRC_ROOT.exists():
            pytest.skip("src/ directory does not exist yet — greenfield pass")

        # Find all files named azure_vault_provider.py anywhere under src/
        all_azure_files = list(SRC_ROOT.rglob("azure_vault_provider.py"))

        for azure_file in all_azure_files:
            assert azure_file.resolve() == AZURE_VAULT_PROVIDER_PATH.resolve(), (
                f"azure_vault_provider.py found at unexpected location: "
                f"{azure_file.relative_to(PROJECT_ROOT)}. "
                f"It must only exist at src/providers/vault/azure_vault_provider.py."
            )
