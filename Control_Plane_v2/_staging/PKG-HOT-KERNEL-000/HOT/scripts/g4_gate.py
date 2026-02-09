#!/usr/bin/env python3
"""
g4_gate.py - G4 ACCEPTANCE Gate Implementation.

Implements the G4 gate specified in FMWK-000 Phase 3:
1. Execute acceptance.tests shell commands in isolated workspace
2. All tests must exit with code 0
3. Timeout enforcement (300s per test per Q2=B decision)

Per user decision Q2=B: Timeout only, rely on workspace isolation for security.

Usage:
    python3 scripts/g4_gate.py --wo-file work_orders/ho3/WO-TEST-001.json --workspace /tmp/workspace
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import CONTROL_PLANE


# Per Q2=B: 300 second (5 minute) timeout per test
DEFAULT_TIMEOUT_SECONDS = 300


@dataclass
class TestResult:
    """Result of a single test execution."""
    command: str
    returncode: int
    passed: bool
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


@dataclass
class G4Result:
    """Result of G4 gate check."""
    passed: bool
    message: str
    test_results: List[TestResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "gate": "G4",
            "passed": self.passed,
            "message": self.message,
            "test_results": [
                {
                    "command": r.command,
                    "returncode": r.returncode,
                    "passed": r.passed,
                    "stdout_tail": r.stdout[-200:] if r.stdout else "",
                    "stderr_tail": r.stderr[-200:] if r.stderr else "",
                    "duration_ms": r.duration_ms,
                    "timed_out": r.timed_out,
                }
                for r in self.test_results
            ],
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


def run_single_test(
    command: str,
    workspace_root: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
) -> TestResult:
    """Run a single test command.

    Args:
        command: Shell command to execute
        workspace_root: Working directory for test execution
        timeout_seconds: Maximum execution time

    Returns:
        TestResult with execution details
    """
    start_time = datetime.now(timezone.utc)

    # Build environment with workspace in PYTHONPATH
    env = os.environ.copy()
    pythonpath = env.get('PYTHONPATH', '')
    if pythonpath:
        env['PYTHONPATH'] = f"{workspace_root}:{pythonpath}"
    else:
        env['PYTHONPATH'] = str(workspace_root)

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env
        )

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return TestResult(
            command=command,
            returncode=result.returncode,
            passed=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
            timed_out=False
        )

    except subprocess.TimeoutExpired as e:
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return TestResult(
            command=command,
            returncode=-1,
            passed=False,
            stdout=e.stdout.decode() if e.stdout else "",
            stderr=e.stderr.decode() if e.stderr else f"TIMEOUT: Exceeded {timeout_seconds}s",
            duration_ms=duration_ms,
            timed_out=True
        )

    except Exception as e:
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return TestResult(
            command=command,
            returncode=-2,
            passed=False,
            stdout="",
            stderr=f"EXCEPTION: {str(e)}",
            duration_ms=duration_ms,
            timed_out=False
        )


def run_acceptance_tests(
    wo: dict,
    workspace_root: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
) -> G4Result:
    """Run all acceptance tests from Work Order.

    Args:
        wo: Work Order dict
        workspace_root: Path to isolated workspace
        timeout_seconds: Timeout per test

    Returns:
        G4Result with all test results
    """
    acceptance = wo.get('acceptance', {})
    tests = acceptance.get('tests', [])
    checks = acceptance.get('checks', [])

    wo_id = wo.get('work_order_id', 'UNKNOWN')
    all_commands = tests + checks  # Run both tests and checks

    if not all_commands:
        return G4Result(
            passed=True,
            message="G4 PASSED: No acceptance tests defined",
            details={
                'wo_id': wo_id,
                'test_count': 0,
                'check_count': 0,
            }
        )

    test_results = []
    errors = []

    for cmd in all_commands:
        result = run_single_test(cmd, workspace_root, timeout_seconds)
        test_results.append(result)

        if not result.passed:
            if result.timed_out:
                errors.append(f"TIMEOUT: '{cmd}' exceeded {timeout_seconds}s")
            else:
                errors.append(f"FAILED: '{cmd}' exited with code {result.returncode}")

            # Fail fast - stop on first failure
            break

    passed_count = sum(1 for r in test_results if r.passed)
    total_count = len(test_results)
    total_duration_ms = sum(r.duration_ms for r in test_results)

    if errors:
        return G4Result(
            passed=False,
            message=f"G4 FAILED: {passed_count}/{total_count} tests passed",
            test_results=test_results,
            errors=errors,
            details={
                'wo_id': wo_id,
                'test_count': len(tests),
                'check_count': len(checks),
                'passed_count': passed_count,
                'total_count': total_count,
                'total_duration_ms': total_duration_ms,
            }
        )

    return G4Result(
        passed=True,
        message=f"G4 PASSED: All {total_count} tests passed ({total_duration_ms}ms)",
        test_results=test_results,
        details={
            'wo_id': wo_id,
            'test_count': len(tests),
            'check_count': len(checks),
            'passed_count': passed_count,
            'total_count': total_count,
            'total_duration_ms': total_duration_ms,
        }
    )


def run_g4_gate(
    wo: dict,
    workspace_root: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
) -> G4Result:
    """Run G4 ACCEPTANCE gate.

    This is the main entry point for G4 validation.

    Args:
        wo: Work Order dict
        workspace_root: Path to isolated workspace
        timeout_seconds: Timeout per test (default 300s per Q2=B)

    Returns:
        G4Result with pass/fail status
    """
    # Validate workspace exists
    if not workspace_root.exists():
        return G4Result(
            passed=False,
            message="G4 FAILED: Workspace does not exist",
            errors=[f"Workspace not found: {workspace_root}"]
        )

    return run_acceptance_tests(wo, workspace_root, timeout_seconds)


def load_work_order(wo_path: Path) -> dict:
    """Load Work Order JSON file."""
    with open(wo_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Run G4 ACCEPTANCE gate - execute acceptance tests"
    )
    parser.add_argument(
        "--wo-file",
        type=Path,
        required=True,
        help="Path to Work Order JSON file"
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Path to isolated workspace"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Timeout per test in seconds (default: {DEFAULT_TIMEOUT_SECONDS})"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    if not args.wo_file.exists():
        print(f"ERROR: Work Order file not found: {args.wo_file}", file=sys.stderr)
        return 1

    if not args.workspace.exists():
        print(f"ERROR: Workspace not found: {args.workspace}", file=sys.stderr)
        return 1

    wo = load_work_order(args.wo_file)

    result = run_g4_gate(
        wo=wo,
        workspace_root=args.workspace,
        timeout_seconds=args.timeout
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"\nG4 ACCEPTANCE Gate: {status}")
        print(f"Message: {result.message}")

        if result.test_results:
            print("\nTest Results:")
            for r in result.test_results:
                status_icon = "✓" if r.passed else "✗"
                timeout_note = " (TIMEOUT)" if r.timed_out else ""
                print(f"  {status_icon} [{r.duration_ms}ms] {r.command}{timeout_note}")
                if not r.passed and r.stderr:
                    # Show last 100 chars of stderr for failed tests
                    stderr_tail = r.stderr[-100:].strip()
                    if stderr_tail:
                        print(f"      stderr: ...{stderr_tail}")

        if result.errors:
            print("\nErrors:")
            for e in result.errors:
                print(f"  - {e}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
