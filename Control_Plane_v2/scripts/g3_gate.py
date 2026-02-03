#!/usr/bin/env python3
"""
g3_gate.py - G3 CONSTRAINTS Gate Implementation.

Implements the G3 gate specified in FMWK-000 Phase 3:
1. Detect new dependencies (requires dependency_add WO type)
2. Detect new files not in spec assets (warning in Phase 3)
3. Validate WO constraints field

Per user decision Q1=B: Detect dependencies via requirements.txt/pyproject.toml diff only.
Per user decision Q5=A: API change detection ignored in Phase 3.

Usage:
    python3 scripts/g3_gate.py --wo-file work_orders/ho3/WO-TEST-001.json
    python3 scripts/g3_gate.py --wo-file work_orders/ho3/WO-TEST-001.json --workspace /tmp/workspace
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE


@dataclass
class G3Result:
    """Result of G3 gate check."""
    passed: bool
    message: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "gate": "G3",
            "passed": self.passed,
            "message": self.message,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


# Dependency manifest files to monitor
DEPENDENCY_FILES = [
    'requirements.txt',
    'requirements-dev.txt',
    'requirements-test.txt',
    'pyproject.toml',
    'setup.py',
    'setup.cfg',
    'Pipfile',
    'poetry.lock',
]


def is_dependency_file(file_path: str) -> bool:
    """Check if file is a dependency manifest."""
    filename = Path(file_path).name
    return filename in DEPENDENCY_FILES or file_path.endswith('requirements.txt')


def check_dependency_changes(wo: dict, workspace_root: Optional[Path] = None) -> Tuple[bool, List[str], List[str]]:
    """Check for unauthorized dependency file changes.

    Per Q1=B: Detect via requirements.txt/pyproject.toml presence in scope.

    Args:
        wo: Work Order dict
        workspace_root: Optional workspace path (for future diff analysis)

    Returns:
        (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    scope = wo.get('scope', {})
    allowed_files = scope.get('allowed_files', [])
    wo_type = wo.get('type', '')

    # Find dependency files in scope
    dep_files_in_scope = [f for f in allowed_files if is_dependency_file(f)]

    if dep_files_in_scope:
        if wo_type != 'dependency_add':
            errors.append(
                f"Dependency files modified without dependency_add WO type: {dep_files_in_scope}"
            )
            errors.append(
                f"Current WO type is '{wo_type}'. Change to 'dependency_add' to modify dependencies."
            )
        else:
            # Valid: dependency_add WO modifying dependency files
            pass

    return len(errors) == 0, errors, warnings


def check_new_files(wo: dict, workspace_root: Optional[Path] = None, plane_root: Path = CONTROL_PLANE) -> Tuple[bool, List[str], List[str]]:
    """Check for new files not in spec assets.

    Per Q4=B: spec_delta deferred to Phase 4. In Phase 3, warn but don't block.

    Args:
        wo: Work Order dict
        workspace_root: Optional workspace path
        plane_root: Control plane root

    Returns:
        (is_valid, errors, warnings)
    """
    warnings = []

    # In Phase 3, we only warn about potential new files
    # Full enforcement requires spec_delta WO type (Phase 4)

    scope = wo.get('scope', {})
    allowed_files = scope.get('allowed_files', [])
    wo_type = wo.get('type', '')

    # Check if any allowed_files don't exist yet (potential new files)
    if workspace_root:
        for f in allowed_files:
            file_path = workspace_root / f
            if not file_path.exists():
                if wo_type != 'spec_delta':
                    warnings.append(
                        f"New file '{f}' in scope but WO type is '{wo_type}' (not spec_delta). "
                        "This will be blocked in Phase 4."
                    )

    # Phase 3: warnings only, don't fail
    return True, [], warnings


def check_constraints_field(wo: dict) -> Tuple[bool, List[str], List[str]]:
    """Validate WO constraints field if present.

    Constraints can specify additional rules like:
    - no_new_deps_unless: condition
    - no_api_change_unless: condition
    - no_file_create_unless: condition

    Args:
        wo: Work Order dict

    Returns:
        (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    constraints = wo.get('constraints', {})

    if not constraints:
        return True, [], []

    # Log constraints for audit
    for key, value in constraints.items():
        warnings.append(f"Constraint declared: {key} = {value}")

    # In Phase 3, we log constraints but don't enforce complex rules
    # Full enforcement would require analyzing actual changes

    return True, errors, warnings


def run_g3_gate(
    wo: dict,
    workspace_root: Optional[Path] = None,
    plane_root: Path = CONTROL_PLANE
) -> G3Result:
    """Run G3 CONSTRAINTS gate.

    This gate validates that Work Order changes don't violate constraints:
    1. No dependency changes without dependency_add type
    2. New files require spec_delta type (warning in Phase 3)
    3. Constraints field is respected

    Args:
        wo: Work Order dict
        workspace_root: Path to isolated workspace (optional)
        plane_root: Control plane root

    Returns:
        G3Result with pass/fail status
    """
    all_errors = []
    all_warnings = []
    details = {}

    wo_id = wo.get('work_order_id', 'UNKNOWN')
    wo_type = wo.get('type', '')

    details['wo_id'] = wo_id
    details['wo_type'] = wo_type

    # Check 1: Dependency changes
    deps_valid, deps_errors, deps_warnings = check_dependency_changes(wo, workspace_root)
    all_errors.extend(deps_errors)
    all_warnings.extend(deps_warnings)
    details['dependency_check'] = 'PASS' if deps_valid else 'FAIL'

    # Check 2: New files (warning only in Phase 3)
    files_valid, files_errors, files_warnings = check_new_files(wo, workspace_root, plane_root)
    all_errors.extend(files_errors)
    all_warnings.extend(files_warnings)
    details['new_files_check'] = 'PASS' if files_valid else 'WARN'

    # Check 3: Constraints field
    constraints_valid, constraints_errors, constraints_warnings = check_constraints_field(wo)
    all_errors.extend(constraints_errors)
    all_warnings.extend(constraints_warnings)
    details['constraints_check'] = 'PASS' if constraints_valid else 'FAIL'

    # Overall result
    passed = len(all_errors) == 0

    if passed:
        message = "G3 CONSTRAINTS gate passed"
        if all_warnings:
            message += f" ({len(all_warnings)} warnings)"
    else:
        message = f"G3 CONSTRAINTS gate failed: {len(all_errors)} violations"

    return G3Result(
        passed=passed,
        message=message,
        errors=all_errors,
        warnings=all_warnings,
        details=details
    )


def load_work_order(wo_path: Path) -> dict:
    """Load Work Order JSON file."""
    with open(wo_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Run G3 CONSTRAINTS gate validation"
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
        help="Path to isolated workspace (optional)"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=CONTROL_PLANE,
        help="Control plane root path"
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

    wo = load_work_order(args.wo_file)

    result = run_g3_gate(
        wo=wo,
        workspace_root=args.workspace,
        plane_root=args.root
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"\nG3 CONSTRAINTS Gate: {status}")
        print(f"Message: {result.message}")

        if result.details:
            print("\nChecks:")
            for k, v in result.details.items():
                if k not in ('wo_id', 'wo_type'):
                    print(f"  {k}: {v}")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  - {w}")

        if result.errors:
            print("\nErrors:")
            for e in result.errors:
                print(f"  - {e}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
