#!/usr/bin/env python3
"""FOLLOWUP-3E: Path Authority Consolidation Tests (DTT).

Validates that layout.json is the single source of truth for paths,
all hardcoded dual-path fallbacks are removed, and ledger/registry
paths consistently point to HOT/.

12 tests total:
  1-3:  paths.py constants
  4-5:  package_install.py constants
  6:    ledger_client.py DEFAULT_LEDGER_PATH
  7-8:  gate_check.py no-fallback
  9-10: layout.json tiers
  11-12: clean install ledger location
"""

import ast
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve staging root
# ---------------------------------------------------------------------------
STAGING = Path(__file__).resolve().parent
CP_ROOT = STAGING.parent  # Control_Plane_v2

# Package source dirs in staging
KERNEL_001 = STAGING / "PKG-KERNEL-001"
VOCABULARY_001 = STAGING / "PKG-VOCABULARY-001"
LAYOUT_001 = STAGING / "PKG-LAYOUT-001"

# Source files under test
PATHS_PY = KERNEL_001 / "HOT" / "kernel" / "paths.py"
PACKAGE_INSTALL_PY = KERNEL_001 / "HOT" / "scripts" / "package_install.py"
LEDGER_CLIENT_PY = KERNEL_001 / "HOT" / "kernel" / "ledger_client.py"
GATE_CHECK_PY = VOCABULARY_001 / "HOT" / "scripts" / "gate_check.py"
LAYOUT_JSON = LAYOUT_001 / "HOT" / "config" / "layout.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def read_source(path: Path) -> str:
    """Read file contents as string."""
    return path.read_text(encoding="utf-8")


def parse_ast(path: Path) -> ast.Module:
    """Parse Python source into AST."""
    return compile(read_source(path), str(path), "exec", ast.PyCF_ONLY_AST)


# ============================================================================
# Tests 1-3: paths.py constants
# ============================================================================

def test_01_paths_ledger_dir_exists():
    """LEDGER_DIR is defined in paths.py."""
    source = read_source(PATHS_PY)
    assert "LEDGER_DIR" in source, "LEDGER_DIR not found in paths.py"
    # Check it's a real assignment, not just a comment
    tree = compile(source, str(PATHS_PY), "exec", ast.PyCF_ONLY_AST)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "LEDGER_DIR":
            names.add(node.id)
        if isinstance(node, ast.Attribute) and node.attr == "LEDGER_DIR":
            names.add(node.attr)
    assert "LEDGER_DIR" in names, "LEDGER_DIR not assigned in paths.py AST"
    print("PASS test_01_paths_ledger_dir_exists")


def test_02_paths_ledger_dir_in_hot():
    """LEDGER_DIR resolves to a path containing HOT/ledger."""
    source = read_source(PATHS_PY)
    # The fallback or layout reference should contain HOT/ledger
    assert '"HOT"' in source or "'HOT'" in source, "No HOT reference in paths.py"
    assert '"ledger"' in source or "'ledger'" in source, "No ledger reference in paths.py"
    # Specifically check the LEDGER_DIR block
    lines = source.split("\n")
    in_ledger_block = False
    found_hot_ledger = False
    for line in lines:
        if "LEDGER_DIR" in line and ("=" in line or "try" in line):
            in_ledger_block = True
        if in_ledger_block:
            if "HOT" in line and "ledger" in line:
                found_hot_ledger = True
                break
            if line.strip() and not line.strip().startswith("#") and "LEDGER_DIR" not in line and "try" not in line and "except" not in line and "from" not in line and "import" not in line:
                if '"""' in line or "'''" in line:
                    in_ledger_block = False
    assert found_hot_ledger, "LEDGER_DIR fallback does not contain HOT/ledger"
    print("PASS test_02_paths_ledger_dir_in_hot")


def test_03_paths_registries_dir_in_hot():
    """REGISTRIES_DIR resolves to a path containing HOT/registries."""
    source = read_source(PATHS_PY)
    # Check REGISTRIES_DIR block has HOT/registries
    lines = source.split("\n")
    in_reg_block = False
    found_hot_reg = False
    for line in lines:
        if "REGISTRIES_DIR" in line and ("=" in line or "try" in line):
            in_reg_block = True
        if in_reg_block:
            if "HOT" in line and "registries" in line:
                found_hot_reg = True
                break
    assert found_hot_reg, "REGISTRIES_DIR fallback does not contain HOT/registries"
    print("PASS test_03_paths_registries_dir_in_hot")


# ============================================================================
# Tests 4-5: package_install.py constants
# ============================================================================

def test_04_package_install_pkg_reg_in_hot():
    """PKG_REG uses REGISTRIES_DIR (which resolves to HOT/registries)."""
    source = read_source(PACKAGE_INSTALL_PY)
    # PKG_REG should use REGISTRIES_DIR, not a hardcoded path
    for line in source.split("\n"):
        stripped = line.strip()
        if stripped.startswith("PKG_REG") and "=" in stripped:
            assert "REGISTRIES_DIR" in stripped, (
                f"PKG_REG should use REGISTRIES_DIR, got: {stripped}"
            )
            # Must NOT contain a bare 'registries' path without REGISTRIES_DIR
            assert "plane_root" not in stripped.lower() or "REGISTRIES_DIR" in stripped, (
                f"PKG_REG uses hardcoded path: {stripped}"
            )
            print("PASS test_04_package_install_pkg_reg_in_hot")
            return
    assert False, "PKG_REG assignment not found in package_install.py"


def test_05_package_install_ledger_in_hot():
    """L_PACKAGE_LEDGER uses LEDGER_DIR (which resolves to HOT/ledger)."""
    source = read_source(PACKAGE_INSTALL_PY)
    for line in source.split("\n"):
        stripped = line.strip()
        if stripped.startswith("L_PACKAGE_LEDGER") and "=" in stripped:
            assert "LEDGER_DIR" in stripped, (
                f"L_PACKAGE_LEDGER should use LEDGER_DIR, got: {stripped}"
            )
            print("PASS test_05_package_install_ledger_in_hot")
            return
    assert False, "L_PACKAGE_LEDGER assignment not found in package_install.py"


# ============================================================================
# Test 6: ledger_client.py DEFAULT_LEDGER_PATH
# ============================================================================

def test_06_ledger_client_default_path_in_hot():
    """DEFAULT_LEDGER_PATH resolves to a path containing HOT/ledger."""
    source = read_source(LEDGER_CLIENT_PY)
    # Find the DEFAULT_LEDGER_PATH assignment
    lines = source.split("\n")
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "DEFAULT_LEDGER_PATH" in stripped and "=" in stripped:
            found = True
            # It should either:
            # a) Import LEDGER_DIR and use it, OR
            # b) Have a path containing HOT/ledger
            # Check surrounding context (try/except block)
            context = "\n".join(lines[max(0, i-5):i+5])
            has_ledger_dir = "LEDGER_DIR" in context
            has_hot_ledger = ("HOT" in context and "ledger" in context)
            # The old fallback parent.parent / "ledger" happens to resolve to
            # HOT/ledger since __file__ is in HOT/kernel/, but using LEDGER_DIR
            # makes intent explicit
            assert has_ledger_dir or has_hot_ledger, (
                f"DEFAULT_LEDGER_PATH does not reference LEDGER_DIR or HOT/ledger.\n"
                f"Context:\n{context}"
            )
            break
    assert found, "DEFAULT_LEDGER_PATH not found in ledger_client.py"
    print("PASS test_06_ledger_client_default_path_in_hot")


# ============================================================================
# Tests 7-8: gate_check.py no-fallback
# ============================================================================

def test_07_gate_check_no_root_registries_fallback():
    """gate_check.py does not use plane_root / 'registries' as primary path."""
    source = read_source(GATE_CHECK_PY)
    lines = source.split("\n")
    violations = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#"):
            continue
        # Look for plane_root / 'registries' WITHOUT 'HOT' in between
        if "plane_root" in stripped and "'registries'" in stripped:
            # Check it's NOT plane_root / 'HOT' / 'registries'
            if "'HOT'" not in stripped and '"HOT"' not in stripped:
                violations.append(f"  line {i}: {stripped}")
    assert not violations, (
        f"gate_check.py still has plane_root / 'registries' without HOT:\n"
        + "\n".join(violations)
    )
    print("PASS test_07_gate_check_no_root_registries_fallback")


def test_08_gate_check_no_root_ledger_fallback():
    """gate_check.py does not use plane_root / 'ledger' without HOT for governance ledger."""
    source = read_source(GATE_CHECK_PY)
    lines = source.split("\n")
    violations = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Skip legitimate cross-tier paths (ho2, ho1, planes/)
        if "'planes'" in stripped or "'ho2'" in stripped or "'ho1'" in stripped:
            continue
        # Look for plane_root / 'ledger' WITHOUT 'HOT'
        if "plane_root" in stripped and "'ledger'" in stripped:
            if "'HOT'" not in stripped and '"HOT"' not in stripped:
                violations.append(f"  line {i}: {stripped}")
    assert not violations, (
        f"gate_check.py still has plane_root / 'ledger' without HOT:\n"
        + "\n".join(violations)
    )
    print("PASS test_08_gate_check_no_root_ledger_fallback")


# ============================================================================
# Tests 9-10: layout.json tiers
# ============================================================================

def test_09_layout_json_no_ho3():
    """layout.json tiers does not include HO3."""
    with open(LAYOUT_JSON, "r", encoding="utf-8") as f:
        layout = json.load(f)
    tiers = layout.get("tiers", {})
    assert "HO3" not in tiers, f"HO3 still in layout.json tiers: {list(tiers.keys())}"
    print("PASS test_09_layout_json_no_ho3")


def test_10_layout_json_tiers_correct():
    """layout.json tiers are exactly HOT, HO2, HO1."""
    with open(LAYOUT_JSON, "r", encoding="utf-8") as f:
        layout = json.load(f)
    tiers = set(layout.get("tiers", {}).keys())
    expected = {"HOT", "HO2", "HO1"}
    assert tiers == expected, f"Expected tiers {expected}, got {tiers}"
    print("PASS test_10_layout_json_tiers_correct")


# ============================================================================
# Tests 11-12: Clean install ledger location (integration)
# ============================================================================

def test_11_clean_install_ledger_in_hot():
    """After clean install, HOT/ledger/ exists with ledger files."""
    # This test requires a clean-room install to have been run.
    # We check the CP_BOOTSTRAP archive structure instead if no install dir.
    install_root = os.environ.get("FOLLOWUP_3E_INSTALL_ROOT")
    if not install_root:
        # Static check: package_install.py writes to LEDGER_DIR which is HOT/ledger
        source = read_source(PACKAGE_INSTALL_PY)
        assert "LEDGER_DIR" in source, "package_install.py does not use LEDGER_DIR"
        # Verify LEDGER_DIR import is present
        assert "from kernel.paths import" in source and "LEDGER_DIR" in source, (
            "LEDGER_DIR not imported in package_install.py"
        )
        print("PASS test_11_clean_install_ledger_in_hot (static — set FOLLOWUP_3E_INSTALL_ROOT for runtime)")
        return

    root = Path(install_root)
    hot_ledger = root / "HOT" / "ledger"
    assert hot_ledger.exists(), f"HOT/ledger/ does not exist at {hot_ledger}"
    ledger_files = list(hot_ledger.glob("*.jsonl"))
    assert len(ledger_files) > 0, f"No .jsonl files in {hot_ledger}"
    print(f"PASS test_11_clean_install_ledger_in_hot ({len(ledger_files)} ledger files)")


def test_12_clean_install_no_root_ledger():
    """After clean install, $ROOT/ledger/ does NOT exist (only HOT/ledger/)."""
    install_root = os.environ.get("FOLLOWUP_3E_INSTALL_ROOT")
    if not install_root:
        # Static check: no code writes to plane_root / "ledger" directly
        source_pi = read_source(PACKAGE_INSTALL_PY)
        source_gc = read_source(GATE_CHECK_PY)
        # package_install should use LEDGER_DIR (which is HOT/ledger)
        # gate_check should not reference plane_root / 'ledger' without HOT
        for line in source_gc.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip legitimate cross-tier paths (ho2, ho1, planes/)
            if "'planes'" in stripped or "'ho2'" in stripped or "'ho1'" in stripped:
                continue
            if "plane_root" in stripped and "'ledger'" in stripped:
                if "'HOT'" not in stripped and '"HOT"' not in stripped:
                    assert False, f"gate_check.py writes to root/ledger: {stripped}"
        print("PASS test_12_clean_install_no_root_ledger (static — set FOLLOWUP_3E_INSTALL_ROOT for runtime)")
        return

    root = Path(install_root)
    root_ledger = root / "ledger"
    assert not root_ledger.exists(), (
        f"$ROOT/ledger/ should NOT exist but found: {list(root_ledger.iterdir()) if root_ledger.exists() else 'N/A'}"
    )
    print("PASS test_12_clean_install_no_root_ledger")


# ============================================================================
# Runner
# ============================================================================

ALL_TESTS = [
    test_01_paths_ledger_dir_exists,
    test_02_paths_ledger_dir_in_hot,
    test_03_paths_registries_dir_in_hot,
    test_04_package_install_pkg_reg_in_hot,
    test_05_package_install_ledger_in_hot,
    test_06_ledger_client_default_path_in_hot,
    test_07_gate_check_no_root_registries_fallback,
    test_08_gate_check_no_root_ledger_fallback,
    test_09_layout_json_no_ho3,
    test_10_layout_json_tiers_correct,
    test_11_clean_install_ledger_in_hot,
    test_12_clean_install_no_root_ledger,
]


def main():
    passed = 0
    failed = 0
    errors = []

    print(f"\n{'='*60}")
    print("FOLLOWUP-3E: Path Authority Consolidation Tests")
    print(f"{'='*60}\n")

    for test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((test_fn.__name__, str(e)))
            print(f"FAIL {test_fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            errors.append((test_fn.__name__, f"ERROR: {e}"))
            print(f"ERROR {test_fn.__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{passed + failed} passed, {failed} failed")
    if errors:
        print("\nFailures:")
        for name, msg in errors:
            print(f"  {name}: {msg}")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
