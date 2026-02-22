#!/usr/bin/env python3
"""
verify.py -- Control Plane v2 Verification Harness.

Single command to verify an installed Control Plane root:
  Level 1: Gates (governance integrity via gate_check.py)
  Level 2: Unit Tests (pytest discovery and execution)
  Level 3: Import Smoke (key module imports)
  Level 4: E2E Smoke (opt-in, requires ANTHROPIC_API_KEY)

READ-ONLY: This script NEVER writes to the install root.
All checks run as isolated subprocesses.

Usage:
    python3 verify.py --root <dir>
    python3 verify.py --root <dir> --e2e
    python3 verify.py --root <dir> --gates-only
    python3 verify.py --root <dir> --json

Exit codes:
    0  All checks passed
    1  One or more checks failed
    2  Script error (bad arguments, missing root, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Constants ────────────────────────────────────────────────────────

IMPORT_SMOKE_MODULES = [
    "shell",
    "session_host_v2",
    "ho2_supervisor",
    "ho1_executor",
    "llm_gateway",
    "work_order",
    "contract_loader",
    "token_budgeter",
    "ledger_client",
    "anthropic_provider",
]

DEFAULT_E2E_TIMEOUT = 30


# ── Parsing Functions ────────────────────────────────────────────────

def parse_gate_output(output: str) -> List[Dict[str, Any]]:
    """Parse gate_check.py stdout into per-gate results.

    Args:
        output: Raw stdout from gate_check.py --all

    Returns:
        List of dicts with keys: gate (str), passed (bool)
    """
    results = []
    pattern = re.compile(r'^(G[0-9A-Z_-]+):\s*(PASS|FAIL)', re.MULTILINE)
    for match in pattern.finditer(output):
        gate_name = match.group(1)
        status = match.group(2)
        results.append({
            "gate": gate_name,
            "passed": status == "PASS",
        })
    return results


def parse_pytest_output(output: str, returncode: int) -> Dict[str, Any]:
    """Parse pytest stdout into structured results.

    Args:
        output: Raw stdout/stderr from pytest
        returncode: pytest process return code

    Returns:
        Dict with keys: total, passed, failed, skipped, status
    """
    passed = 0
    failed = 0
    skipped = 0

    # Match summary line: "N passed", "N failed", "N skipped"
    passed_match = re.search(r'(\d+)\s+passed', output)
    failed_match = re.search(r'(\d+)\s+failed', output)
    skipped_match = re.search(r'(\d+)\s+skipped', output)

    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))
    if skipped_match:
        skipped = int(skipped_match.group(1))

    total = passed + failed + skipped
    status = "PASS" if failed == 0 and returncode == 0 else "FAIL"

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "status": status,
    }


def parse_e2e_output(output: str) -> Dict[str, Any]:
    """Parse E2E smoke test output.

    Args:
        output: Raw stdout from the E2E subprocess

    Returns:
        Dict with keys: passed (bool), reason (str), preview (str)
    """
    stripped = output.strip()

    if not stripped:
        return {"passed": False, "reason": "Empty response", "preview": ""}

    lower = stripped.lower()
    if "quality gate failed" in lower:
        return {"passed": False, "reason": "Quality gate failure detected", "preview": stripped[:100]}

    if "error" in lower and len(stripped) < 200:
        # Short error-only outputs indicate failure
        return {"passed": False, "reason": "Error in output", "preview": stripped[:100]}

    return {"passed": True, "reason": "", "preview": stripped[:100]}


# ── Discovery Functions ──────────────────────────────────────────────

def discover_test_files(root: str) -> List[str]:
    """Discover test_*.py files under installed root.

    Searches {HOT,HO1,HO2}/**/tests/test_*.py under root.

    Args:
        root: Path to installed control plane root

    Returns:
        Sorted list of absolute paths to test files
    """
    root_path = Path(root)
    test_files = []
    for tier in ["HOT", "HO1", "HO2"]:
        tier_path = root_path / tier
        if tier_path.exists():
            for test_file in sorted(tier_path.rglob("tests/test_*.py")):
                test_files.append(str(test_file))
    return sorted(test_files)


# ── Validation Functions ─────────────────────────────────────────────

def validate_root(root: str) -> Dict[str, Any]:
    """Validate that root is a valid installed Control Plane.

    Args:
        root: Path to check

    Returns:
        Dict with keys: valid (bool), exit_code (int), message (str)
    """
    root_path = Path(root)

    if not root_path.exists():
        return {
            "valid": False,
            "exit_code": 2,
            "message": f"Root directory does not exist: {root}",
        }

    gate_check = root_path / "HOT" / "scripts" / "gate_check.py"
    if not gate_check.exists():
        return {
            "valid": False,
            "exit_code": 2,
            "message": f"gate_check.py not found at {gate_check}",
        }

    return {"valid": True, "exit_code": 0, "message": "OK"}


def determine_levels(gates_only: bool, e2e: bool) -> Dict[str, bool]:
    """Determine which verification levels to run.

    Args:
        gates_only: If True, only run Level 1
        e2e: If True, include Level 4

    Returns:
        Dict with keys: gates, tests, imports, e2e (all bool)
    """
    if gates_only:
        return {"gates": True, "tests": False, "imports": False, "e2e": False}
    return {"gates": True, "tests": True, "imports": True, "e2e": e2e}


def check_e2e_skip(e2e_requested: bool, api_key_set: bool) -> Optional[Dict[str, str]]:
    """Check if E2E should be skipped.

    Args:
        e2e_requested: Whether --e2e was passed
        api_key_set: Whether ANTHROPIC_API_KEY is in environment

    Returns:
        Dict with status/reason if skipped, None if E2E should run
    """
    if not e2e_requested:
        return {"status": "SKIPPED", "reason": "--e2e not specified"}
    if not api_key_set:
        return {"status": "SKIPPED", "reason": "ANTHROPIC_API_KEY not set"}
    return None


# ── Report Building ──────────────────────────────────────────────────

def build_report(
    root: str,
    gate_results: List[Dict[str, Any]],
    test_results: Dict[str, Any],
    import_results: Dict[str, Any],
    e2e_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Build structured report dict suitable for JSON output.

    Args:
        root: Install root path
        gate_results: List of per-gate results
        test_results: Pytest summary dict
        import_results: Import smoke summary dict
        e2e_result: E2E result dict

    Returns:
        Full report dict with result, levels, root, timestamp
    """
    gates_passed = sum(1 for g in gate_results if g["passed"])
    gates_failed = len(gate_results) - gates_passed
    gates_status = "PASS" if gates_failed == 0 and len(gate_results) > 0 else "FAIL"

    levels = {
        "gates": {
            "status": gates_status,
            "passed": gates_passed,
            "failed": gates_failed,
            "details": gate_results,
        },
        "tests": test_results,
        "imports": import_results,
        "e2e": e2e_result,
    }

    # Overall result: PASS only if all non-skipped levels pass
    all_pass = True
    for level_name, level_data in levels.items():
        status = level_data.get("status", "PASS")
        if status == "SKIPPED":
            continue
        if status != "PASS":
            all_pass = False

    return {
        "result": "PASS" if all_pass else "FAIL",
        "levels": levels,
        "root": root,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def compute_exit_code(
    gate_passed: bool,
    tests_passed: bool,
    imports_passed: bool,
    e2e_result: Dict[str, Any],
) -> int:
    """Compute exit code from level results.

    Args:
        gate_passed: Whether all gates passed
        tests_passed: Whether all tests passed
        imports_passed: Whether all imports succeeded
        e2e_result: E2E result dict (may be SKIPPED)

    Returns:
        0 if all passed, 1 if any failed
    """
    if not gate_passed:
        return 1
    if not tests_passed:
        return 1
    if not imports_passed:
        return 1
    e2e_status = e2e_result.get("status", "SKIPPED")
    if e2e_status not in ("PASS", "SKIPPED"):
        return 1
    return 0


# ── Execution Functions ──────────────────────────────────────────────

def build_python_paths(root: str) -> str:
    """Build PYTHONPATH string for subprocess execution.

    Includes all tier kernel directories, scripts, and well-known
    module directories (e.g., HOT/admin) so that tests and imports
    can resolve modules from the installed layout.

    Args:
        root: Install root path

    Returns:
        OS-separated PYTHONPATH string
    """
    paths = [
        os.path.join(root, "HOT", "kernel"),
        os.path.join(root, "HOT"),
        os.path.join(root, "HOT", "admin"),
        os.path.join(root, "HO1", "kernel"),
        os.path.join(root, "HO2", "kernel"),
        os.path.join(root, "HOT", "scripts"),
    ]
    return os.pathsep.join(paths)


def run_gates(root: str, verbose: bool = False) -> List[Dict[str, Any]]:
    """Run Level 1: Gate checks via subprocess.

    Args:
        root: Install root path
        verbose: Whether to show full gate output

    Returns:
        List of per-gate result dicts
    """
    gate_check_path = os.path.join(root, "HOT", "scripts", "gate_check.py")
    try:
        proc = subprocess.run(
            [sys.executable, gate_check_path, "--root", root, "--all"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = proc.stdout + proc.stderr
        if verbose:
            print(output)
        return parse_gate_output(output)
    except subprocess.TimeoutExpired:
        return [{"gate": "TIMEOUT", "passed": False}]
    except Exception as e:
        return [{"gate": "ERROR", "passed": False, "error": str(e)}]


def run_tests(root: str, verbose: bool = False) -> Dict[str, Any]:
    """Run Level 2: Unit tests via subprocess.

    Args:
        root: Install root path
        verbose: Whether to show full pytest output

    Returns:
        Pytest results dict
    """
    test_files = discover_test_files(root)
    if not test_files:
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "status": "PASS", "details": []}

    python_path = build_python_paths(root)
    env = {**os.environ, "PYTHONPATH": python_path, "CONTROL_PLANE_ROOT": root}

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest"] + test_files + ["-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        output = proc.stdout + proc.stderr
        if verbose:
            print(output)
        result = parse_pytest_output(output, proc.returncode)
        result["details"] = test_files
        return result
    except subprocess.TimeoutExpired:
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "status": "FAIL",
                "error": "pytest timed out", "details": test_files}
    except Exception as e:
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "status": "FAIL",
                "error": str(e), "details": test_files}


def run_import_smoke(root: str, verbose: bool = False) -> Dict[str, Any]:
    """Run Level 3: Import smoke checks via subprocess.

    Args:
        root: Install root path
        verbose: Whether to show per-module details

    Returns:
        Import results dict
    """
    python_path = build_python_paths(root)
    env = {**os.environ, "PYTHONPATH": python_path, "CONTROL_PLANE_ROOT": root}

    results = []
    ok_count = 0
    fail_count = 0

    for module in IMPORT_SMOKE_MODULES:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", f"import {module}"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            passed = proc.returncode == 0
            if passed:
                ok_count += 1
            else:
                fail_count += 1
            results.append({
                "module": module,
                "passed": passed,
                "error": proc.stderr.strip() if not passed else "",
            })
            if verbose:
                status = "OK" if passed else "FAIL"
                print(f"  {module:<24s} {status}")
        except Exception as e:
            fail_count += 1
            results.append({"module": module, "passed": False, "error": str(e)})

    total = len(IMPORT_SMOKE_MODULES)
    status = "PASS" if fail_count == 0 else "FAIL"

    return {
        "total": total,
        "ok": ok_count,
        "failed": fail_count,
        "status": status,
        "details": results,
    }


def run_e2e(root: str, timeout: int = DEFAULT_E2E_TIMEOUT, verbose: bool = False) -> Dict[str, Any]:
    """Run Level 4: E2E smoke test via subprocess.

    Args:
        root: Install root path
        timeout: Timeout in seconds
        verbose: Whether to show full output

    Returns:
        E2E result dict
    """
    main_py = os.path.join(root, "HOT", "admin", "main.py")
    if not os.path.exists(main_py):
        return {"status": "FAIL", "reason": f"main.py not found: {main_py}"}

    try:
        proc = subprocess.run(
            [sys.executable, main_py, "--root", root, "--dev"],
            input="hello\n",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = proc.stdout
        if verbose:
            print(output)
        result = parse_e2e_output(output)
        return {
            "status": "PASS" if result["passed"] else "FAIL",
            "reason": result.get("reason", ""),
            "preview": result.get("preview", ""),
        }
    except subprocess.TimeoutExpired:
        return {"status": "FAIL", "reason": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"status": "FAIL", "reason": str(e)}


# ── Output Formatting ────────────────────────────────────────────────

def format_human_report(report: Dict[str, Any], levels_run: Dict[str, bool]) -> str:
    """Format report for human-readable output.

    Args:
        report: Full report dict from build_report()
        levels_run: Which levels were run

    Returns:
        Formatted string
    """
    lines = []
    lines.append("")
    lines.append("\u2550\u2550\u2550 VERIFY: Control Plane v2 \u2550" * 2 + "\u2550" * 8)
    lines.append("")

    # Level 1: Gates
    if levels_run["gates"]:
        lines.append("\u2500\u2500 Level 1: Gates " + "\u2500" * 42)
        gate_data = report["levels"]["gates"]
        for detail in gate_data.get("details", []):
            status = "PASS" if detail["passed"] else "FAIL"
            lines.append(f"{detail['gate']:<16s} {status}")
        total_gates = gate_data["passed"] + gate_data["failed"]
        lines.append(f"Gates: {gate_data['passed']}/{total_gates} PASS")
        lines.append("")

    # Level 2: Tests
    if levels_run["tests"]:
        lines.append("\u2500\u2500 Level 2: Unit Tests " + "\u2500" * 37)
        test_data = report["levels"]["tests"]
        lines.append(f"Tests: {test_data['passed']} passed, {test_data['failed']} failed, {test_data['skipped']} skipped")
        lines.append("")

    # Level 3: Imports
    if levels_run["imports"]:
        lines.append("\u2500\u2500 Level 3: Import Smoke " + "\u2500" * 35)
        import_data = report["levels"]["imports"]
        for detail in import_data.get("details", []):
            status = "OK" if detail["passed"] else "FAIL"
            lines.append(f"{detail['module']:<24s} {status}")
        lines.append(f"Imports: {import_data['ok']}/{import_data['total']} OK")
        lines.append("")

    # Level 4: E2E
    if levels_run["e2e"]:
        lines.append("\u2500\u2500 Level 4: E2E Smoke " + "\u2500" * 38)
        e2e_data = report["levels"]["e2e"]
        if e2e_data["status"] == "SKIPPED":
            lines.append(f"[SKIPPED \u2014 {e2e_data.get('reason', '')}]")
        elif e2e_data["status"] == "PASS":
            lines.append(f"PASS  {e2e_data.get('preview', '')}")
        else:
            lines.append(f"FAIL  {e2e_data.get('reason', '')}")
        lines.append("")
    else:
        lines.append("\u2500\u2500 Level 4: E2E Smoke " + "\u2500" * 38)
        lines.append("[SKIPPED \u2014 --e2e not specified]")
        lines.append("")

    # Summary
    passed_levels = 0
    total_levels = 0
    skipped_levels = 0
    for level_name in ["gates", "tests", "imports", "e2e"]:
        level_data = report["levels"].get(level_name, {})
        status = level_data.get("status", "SKIPPED")
        if not levels_run.get(level_name, False) or status == "SKIPPED":
            skipped_levels += 1
            continue
        total_levels += 1
        if status == "PASS":
            passed_levels += 1

    lines.append("\u2550" * 60)
    lines.append(f"RESULT: {report['result']} ({passed_levels}/{total_levels} levels passed, {skipped_levels} skipped)")
    lines.append("\u2550" * 60)

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0=pass, 1=fail, 2=error)
    """
    parser = argparse.ArgumentParser(
        description="Control Plane v2 Verification Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", required=True, help="Installed control plane root")
    parser.add_argument("--e2e", action="store_true", help="Run Level 4 E2E smoke test")
    parser.add_argument("--e2e-timeout", type=int, default=DEFAULT_E2E_TIMEOUT, help="E2E timeout in seconds")
    parser.add_argument("--gates-only", action="store_true", help="Run only Level 1")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON report")
    parser.add_argument("--report", type=str, default=None, help="Write report to file (outside root)")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")

    args = parser.parse_args(argv)

    # Validate root
    validation = validate_root(args.root)
    if not validation["valid"]:
        print(f"ERROR: {validation['message']}", file=sys.stderr)
        return validation["exit_code"]

    root = os.path.abspath(args.root)
    levels_run = determine_levels(gates_only=args.gates_only, e2e=args.e2e)

    # Level 1: Gates
    gate_results = []
    if levels_run["gates"]:
        if not args.json_output:
            print("\nRunning Level 1: Gates...")
        gate_results = run_gates(root, verbose=args.verbose)

    # Level 2: Tests
    test_results = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "status": "SKIPPED"}
    if levels_run["tests"]:
        if not args.json_output:
            print("Running Level 2: Unit Tests...")
        test_results = run_tests(root, verbose=args.verbose)

    # Level 3: Imports
    import_results = {"total": 0, "ok": 0, "failed": 0, "status": "SKIPPED", "details": []}
    if levels_run["imports"]:
        if not args.json_output:
            print("Running Level 3: Import Smoke...")
        import_results = run_import_smoke(root, verbose=args.verbose)

    # Level 4: E2E
    e2e_result = {"status": "SKIPPED", "reason": "--e2e not specified"}
    if levels_run["e2e"]:
        skip_check = check_e2e_skip(
            e2e_requested=args.e2e,
            api_key_set=bool(os.environ.get("ANTHROPIC_API_KEY")),
        )
        if skip_check:
            e2e_result = skip_check
        else:
            if not args.json_output:
                print("Running Level 4: E2E Smoke...")
            e2e_result = run_e2e(root, timeout=args.e2e_timeout, verbose=args.verbose)

    # Build report
    report = build_report(
        root=root,
        gate_results=gate_results,
        test_results=test_results,
        import_results=import_results,
        e2e_result=e2e_result,
    )

    # Output
    if args.json_output:
        print(json.dumps(report, indent=2))
    else:
        print(format_human_report(report, levels_run))

    # Write report file if requested
    if args.report:
        report_path = os.path.abspath(args.report)
        # Safety check: report must NOT be inside root
        if report_path.startswith(os.path.abspath(root)):
            print("ERROR: --report path must be outside --root", file=sys.stderr)
            return 2
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

    # Compute exit code
    gate_passed = all(g["passed"] for g in gate_results) if gate_results else True
    tests_passed = test_results.get("status") in ("PASS", "SKIPPED")
    imports_passed = import_results.get("status") in ("PASS", "SKIPPED")

    return compute_exit_code(
        gate_passed=gate_passed,
        tests_passed=tests_passed,
        imports_passed=imports_passed,
        e2e_result=e2e_result,
    )


if __name__ == "__main__":
    sys.exit(main())
