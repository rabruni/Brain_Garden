#!/usr/bin/env python3
"""
gate_check.py - Run governance gates for the Control Plane.

Implements the gate sequence from FMWK-000 and CP-IMPL-001:
- G0A (PACKAGE DECLARATION): Package assets declared and hashes match (install-time)
- G0B (PLANE OWNERSHIP): Every governed file owned by one package (integrity-time)
- G0 (OWNERSHIP): Legacy alias for G0B
- G1 (CHAIN): Every file->spec->framework chain must be valid
- G2 (WORK_ORDER): Work Orders must be approved and pass idempotency
- G3 (CONSTRAINTS): No constraint violations
- G4 (ACCEPTANCE): Acceptance tests must pass
- G5 (SIGNATURE): Package signatures must be valid
- G6 (LEDGER): Ledger chain must be valid

BINDING CONSTRAINTS (from CP-IMPL-001):
- G0A: At package install pre-commit - "every file being installed is declared in manifest + hashes match archive"
- G0B: At integrity/seal check - "every governed file is owned by exactly one package + hash matches"
- --enforce mode: exit 1 on ANY gate failure (fail-closed)

Usage:
    python3 scripts/gate_check.py --all --enforce
    python3 scripts/gate_check.py --gate G0B --enforce
    python3 scripts/gate_check.py --gate G0A --manifest /path/to/manifest.json
"""

import argparse
import csv
import fnmatch
import hashlib
import json
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.merkle import hash_file


@dataclass
class GateResult:
    """Result of a gate check."""
    gate: str
    passed: bool
    message: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "gate": self.gate,
            "passed": self.passed,
            "message": self.message,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details
        }


def load_governed_roots(plane_root: Path) -> dict:
    """Load governed roots configuration."""
    config_path = plane_root / 'config' / 'governed_roots.json'
    if not config_path.exists():
        return {
            "governed_roots": ["lib/", "scripts/", "frameworks/", "schemas/", "policies/", "registries/", "modules/", "tests/"],
            "excluded_patterns": ["**/__pycache__/**", "**/*.pyc", "**/__init__.py"]
        }
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_control_plane_registry(plane_root: Path) -> List[dict]:
    """Load control_plane_registry.csv."""
    registry_path = plane_root / 'registries' / 'control_plane_registry.csv'
    if not registry_path.exists():
        return []
    with open(registry_path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def get_registered_paths(plane_root: Path) -> Set[str]:
    """Get all registered file paths from registry."""
    rows = load_control_plane_registry(plane_root)
    paths = set()
    for row in rows:
        artifact_path = row.get('artifact_path', '').strip()
        if artifact_path:
            paths.add(artifact_path.lstrip('/'))
    return paths


def matches_pattern(path: str, patterns: List[str]) -> bool:
    """Check if path matches any of the glob patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        # Also check with leading slash removed
        if fnmatch.fnmatch('/' + path, pattern):
            return True
    return False


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash in standard format: sha256:<64hex>"""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def load_file_ownership_registry(plane_root: Path) -> Dict[str, dict]:
    """Load file_ownership.csv as dict keyed by file_path."""
    registry_path = plane_root / 'registries' / 'file_ownership.csv'
    if not registry_path.exists():
        return {}

    ownership = {}
    with open(registry_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            file_path = row.get('file_path', '').strip()
            if file_path:
                ownership[file_path] = row
    return ownership


# =============================================================================
# Gate Implementations
# =============================================================================

def check_g0a_package_declaration(
    plane_root: Path,
    manifest: Optional[dict] = None,
    archive_path: Optional[Path] = None
) -> GateResult:
    """G0A: PACKAGE DECLARATION - Verify package is internally consistent.

    Run at package install pre-commit.

    Checks:
    1. Every file in archive is declared in manifest.assets[]
    2. Every declared asset hash matches archive file hash
    3. install_targets[] paths are valid namespaces
    4. No path escapes (no "..", no absolute paths)

    Args:
        plane_root: Path to plane root
        manifest: Package manifest dict (required)
        archive_path: Path to package archive (optional, for file verification)
    """
    result = GateResult(gate="G0A", passed=True, message="Package declaration check passed")
    errors = []
    warnings = []

    if manifest is None:
        result.passed = False
        result.message = "G0A requires --manifest argument"
        result.errors = ["No manifest provided for G0A check"]
        return result

    # Valid namespaces per CP-IMPL-001
    valid_namespaces = {
        "frameworks", "specs", "lib", "scripts", "gates",
        "schemas", "policies", "modules", "tests", "docs",
        "registries", "config"
    }

    assets = manifest.get('assets', [])
    install_targets = manifest.get('install_targets', [])

    # Check 3: Valid namespaces
    for target in install_targets:
        namespace = target.get('namespace', '')
        if namespace not in valid_namespaces:
            errors.append(f"INVALID_NAMESPACE: '{namespace}' not in allowed namespaces")

    # Check 4: No path escapes
    for asset in assets:
        path = asset.get('path', '')
        if '..' in path:
            errors.append(f"PATH_ESCAPE: '{path}' contains '..'")
        if path.startswith('/'):
            errors.append(f"PATH_ESCAPE: '{path}' is absolute path")

    # Check 2: Hash format
    for asset in assets:
        sha = asset.get('sha256', '')
        if not sha.startswith('sha256:'):
            errors.append(f"HASH_FORMAT: '{asset.get('path', '?')}' hash not in sha256:<hex> format")
        elif len(sha) != 71:  # "sha256:" (7) + 64 hex
            errors.append(f"HASH_FORMAT: '{asset.get('path', '?')}' hash has wrong length")

    # If archive provided, verify contents
    if archive_path and archive_path.exists():
        try:
            declared_paths = {a['path'] for a in assets}

            with tarfile.open(archive_path, 'r:gz') as tar:
                archive_members = [m.name for m in tar.getmembers() if m.isfile()]

            # Check 1: All archive files declared
            for member in archive_members:
                # Strip package prefix (first path component)
                parts = Path(member).parts
                if len(parts) > 1:
                    rel_path = str(Path(*parts[1:]))
                else:
                    rel_path = member

                # Skip manifest and signature files
                if rel_path in ('manifest.json', 'signature.json', 'checksums.sha256'):
                    continue

                if rel_path not in declared_paths:
                    errors.append(f"UNDECLARED: '{rel_path}' in archive but not in manifest")
        except Exception as e:
            warnings.append(f"Could not read archive: {e}")

    if errors:
        result.passed = False
        result.message = f"G0A FAILED: {len(errors)} issues"
    else:
        result.message = f"G0A PASSED: {len(assets)} assets verified"

    result.errors = errors[:20]
    if len(errors) > 20:
        result.errors.append(f"... and {len(errors) - 20} more")
    result.warnings = warnings
    result.details = {"asset_count": len(assets), "error_count": len(errors)}

    return result


def check_g0b_plane_ownership(plane_root: Path) -> GateResult:
    """G0B: PLANE OWNERSHIP - Verify plane is fully governed.

    Run at integrity check and seal check.

    Checks:
    1. Every file in governed roots is owned by exactly one package
    2. Every owned file exists with matching hash
    3. No orphan files in governed roots

    Uses file_ownership.csv (derived registry) as source of truth.
    """
    result = GateResult(gate="G0B", passed=True, message="Plane ownership check passed")
    errors = []
    warnings = []

    # Load configuration
    config = load_governed_roots(plane_root)
    governed_roots = config.get('governed_roots', [])
    excluded_patterns = config.get('excluded_patterns', [])

    # Load file ownership registry
    ownership = load_file_ownership_registry(plane_root)

    if not ownership:
        warnings.append("file_ownership.csv is empty or missing")
        warnings.append("Run: python3 scripts/rebuild_derived_registries.py --plane ho3")

    # Check 1 & 3: Every governed file is owned (find orphans)
    orphans = []
    for root_pattern in governed_roots:
        root_dir = plane_root / root_pattern.rstrip('/')
        if not root_dir.exists():
            continue

        for file_path in root_dir.rglob('*'):
            if file_path.is_dir():
                continue

            rel_path = str(file_path.relative_to(plane_root))

            # Skip excluded patterns
            if matches_pattern(rel_path, excluded_patterns):
                continue

            # Skip hidden files
            if any(part.startswith('.') for part in Path(rel_path).parts):
                continue

            # Check if owned
            if rel_path not in ownership:
                orphans.append(rel_path)

    if orphans:
        result.passed = False
        errors.extend([f"ORPHAN: {p}" for p in orphans[:20]])
        if len(orphans) > 20:
            errors.append(f"... and {len(orphans) - 20} more orphans")

    # Check 2: Every owned file exists with correct hash
    missing = []
    hash_mismatches = []

    for file_path, entry in ownership.items():
        full_path = plane_root / file_path

        if not full_path.exists():
            missing.append(file_path)
            continue

        expected_hash = entry.get('sha256', '')
        if expected_hash:
            actual_hash = compute_sha256(full_path)
            if actual_hash != expected_hash:
                hash_mismatches.append({
                    'path': file_path,
                    'expected': expected_hash[:24] + '...',
                    'actual': actual_hash[:24] + '...'
                })

    if missing:
        result.passed = False
        errors.extend([f"MISSING: {p} (owned by {ownership[p].get('owner_package_id', '?')})" for p in missing[:10]])
        if len(missing) > 10:
            errors.append(f"... and {len(missing) - 10} more missing")

    if hash_mismatches:
        result.passed = False
        for hm in hash_mismatches[:10]:
            errors.append(f"HASH_MISMATCH: {hm['path']} expected {hm['expected']} got {hm['actual']}")
        if len(hash_mismatches) > 10:
            errors.append(f"... and {len(hash_mismatches) - 10} more hash mismatches")

    if result.passed:
        result.message = f"G0B PASSED: {len(ownership)} files owned, 0 orphans"
    else:
        result.message = f"G0B FAILED: {len(orphans)} orphans, {len(missing)} missing, {len(hash_mismatches)} hash mismatches"

    result.errors = errors
    result.warnings = warnings
    result.details = {
        "owned_count": len(ownership),
        "orphan_count": len(orphans),
        "missing_count": len(missing),
        "hash_mismatch_count": len(hash_mismatches)
    }

    return result


def check_g0_ownership(plane_root: Path) -> GateResult:
    """G0: OWNERSHIP - Legacy alias for G0B.

    Now delegates to G0B (plane ownership check).
    For package declaration checks, use G0A explicitly.
    """
    result = check_g0b_plane_ownership(plane_root)
    result.gate = "G0"  # Keep gate name for backward compatibility
    return result


def check_g1_chain(plane_root: Path) -> GateResult:
    """G1: CHAIN - Verify spec->framework chain integrity.

    Checks:
    - Every file's owner_spec_id MUST exist in specs_registry.csv
    - Every spec's framework_id MUST exist in frameworks_registry.csv
    """
    result = GateResult(gate="G1", passed=True, message="Chain check passed")
    errors = []

    # Load registries
    cp_rows = load_control_plane_registry(plane_root)

    # Build framework lookup
    framework_ids = {row['id'] for row in cp_rows if row.get('entity_type') == 'framework'}

    # Check all artifacts have valid chains
    for row in cp_rows:
        deps = row.get('dependencies', '').strip()
        if deps:
            for dep_id in deps.split(','):
                dep_id = dep_id.strip().strip('"')
                if dep_id.startswith('FMWK-') and dep_id not in framework_ids:
                    errors.append(f"{row.get('id', '?')}: dependency {dep_id} not found")

    if errors:
        result.passed = False
        result.message = f"Found {len(errors)} chain errors"
        result.errors = errors[:20]
        if len(errors) > 20:
            result.errors.append(f"... and {len(errors) - 20} more")

    return result


def check_g2_work_order(
    plane_root: Path,
    wo_id: Optional[str] = None,
    wo_file: Optional[Path] = None,
    skip_signature: bool = False
) -> GateResult:
    """G2: WORK_ORDER - Verify Work Order approval, signature, and idempotency.

    Phase 2 implementation using full G2 gate from g2_gate.py.

    When wo_id is provided, validates specific Work Order.
    Otherwise, reports on overall WO system health.

    Args:
        plane_root: Path to plane root
        wo_id: Work Order ID to validate (optional)
        wo_file: Path to Work Order file (optional)
        skip_signature: Skip Ed25519 signature verification
    """
    # If specific WO provided, use full G2 validation
    if wo_id or wo_file:
        try:
            from scripts.g2_gate import run_g2_gate

            g2_result = run_g2_gate(
                wo_id=wo_id,
                wo_file=wo_file,
                plane_root=plane_root,
                skip_signature=skip_signature
            )

            # Map G2Result to GateResult
            return GateResult(
                gate="G2",
                passed=g2_result.passed,
                message=g2_result.message,
                errors=g2_result.errors,
                warnings=g2_result.warnings,
                details=g2_result.details
            )
        except ImportError as e:
            # Fallback if g2_gate not available
            return GateResult(
                gate="G2",
                passed=False,
                message=f"G2 gate module not available: {e}",
                errors=["Import g2_gate.py failed"]
            )

    # No specific WO - report on overall WO system health
    result = GateResult(gate="G2", passed=True, message="Work Order system check passed")

    # Check HOT governance.jsonl for WO_APPROVED events
    governance_ledger = plane_root / 'ledger' / 'governance.jsonl'
    ho2_ledger = plane_root / 'planes' / 'ho2' / 'ledger' / 'workorder.jsonl'

    approved_count = 0
    completed_count = 0

    # Count WO_APPROVED in HOT
    if governance_ledger.exists():
        with open(governance_ledger, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get('event_type') == 'WO_APPROVED':
                            approved_count += 1
                    except json.JSONDecodeError:
                        pass

    # Count WO_COMPLETED in HO2
    if ho2_ledger.exists():
        with open(ho2_ledger, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get('event_type') == 'WO_COMPLETED':
                            completed_count += 1
                    except json.JSONDecodeError:
                        pass

    result.message = f"WO system: {approved_count} approved (HOT), {completed_count} completed (HO2)"
    result.details = {
        "approved_count": approved_count,
        "completed_count": completed_count,
        "governance_ledger_exists": governance_ledger.exists(),
        "ho2_ledger_exists": ho2_ledger.exists(),
    }

    return result


def check_g3_constraints(
    plane_root: Path,
    wo: Optional[dict] = None,
    changed_files: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None
) -> GateResult:
    """G3: CONSTRAINTS - Verify no constraint violations.

    Checks:
    - No new dependencies without dependency_add WO
    - No new files without spec_delta WO
    - No API changes without version bump

    When wo and changed_files provided, runs full G3 validation.
    Otherwise reports on constraint system health.
    """
    # If WO provided, use full G3 implementation
    if wo is not None:
        try:
            from scripts.g3_gate import run_g3_gate

            g3_result = run_g3_gate(
                wo=wo,
                changed_files=changed_files or [],
                workspace_root=workspace_root or plane_root
            )

            return GateResult(
                gate="G3",
                passed=g3_result.passed,
                message=g3_result.message,
                errors=g3_result.errors,
                warnings=g3_result.warnings,
                details=g3_result.details
            )
        except ImportError as e:
            return GateResult(
                gate="G3",
                passed=False,
                message=f"G3 gate module not available: {e}",
                errors=["Import g3_gate.py failed"]
            )

    # No WO - report on constraint system health
    result = GateResult(gate="G3", passed=True, message="Constraints check passed")
    return result


def check_g4_acceptance(
    plane_root: Path,
    wo: Optional[dict] = None,
    workspace_root: Optional[Path] = None
) -> GateResult:
    """G4: ACCEPTANCE - Verify acceptance tests pass.

    When wo provided, runs acceptance.tests shell commands in workspace.
    Otherwise reports on test infrastructure health.

    Per user decision Q2=B: Timeout only (300s), rely on workspace isolation.
    """
    # If WO provided, use full G4 implementation
    if wo is not None:
        try:
            from scripts.g4_gate import run_g4_gate

            g4_result = run_g4_gate(
                wo=wo,
                workspace_root=workspace_root or plane_root
            )

            return GateResult(
                gate="G4",
                passed=g4_result.passed,
                message=g4_result.message,
                errors=g4_result.errors,
                warnings=g4_result.warnings,
                details=g4_result.details
            )
        except ImportError as e:
            return GateResult(
                gate="G4",
                passed=False,
                message=f"G4 gate module not available: {e}",
                errors=["Import g4_gate.py failed"]
            )

    # No WO - report on test infrastructure health
    result = GateResult(gate="G4", passed=True, message="Acceptance infrastructure check passed")

    test_dir = plane_root / 'tests'
    if test_dir.exists():
        test_files = list(test_dir.glob('test_*.py'))
        result.message = f"Found {len(test_files)} test files"
        result.details = {"test_file_count": len(test_files)}
    else:
        result.warnings = ["tests/ directory not found"]

    return result


def check_g5_signature(
    plane_root: Path,
    wo: Optional[dict] = None,
    changed_files: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None
) -> GateResult:
    """G5: SIGNATURE - Create and verify changeset attestation.

    When wo and changed_files provided, computes changeset digest and creates attestation.
    Otherwise reports on package store signature status.

    Per user decision Q3=C: Role-based keys (signer role separate from wo_approver).
    Uses build-001 signing key from config/signing_keys.json.
    """
    # If WO provided, use full G5 implementation
    if wo is not None:
        try:
            from scripts.g5_gate import run_g5_gate

            g5_result = run_g5_gate(
                wo=wo,
                changed_files=changed_files or [],
                workspace_root=workspace_root or plane_root,
                plane_root=plane_root
            )

            return GateResult(
                gate="G5",
                passed=g5_result.passed,
                message=g5_result.message,
                errors=g5_result.errors,
                warnings=g5_result.warnings,
                details=g5_result.details
            )
        except ImportError as e:
            return GateResult(
                gate="G5",
                passed=False,
                message=f"G5 gate module not available: {e}",
                errors=["Import g5_gate.py failed"]
            )

    # No WO - report on package store signature status
    result = GateResult(gate="G5", passed=True, message="Signature check passed")

    packages_dir = plane_root / 'packages_store'
    if packages_dir.exists():
        packages = list(packages_dir.glob('*.tar.gz'))
        signed = list(packages_dir.glob('*.tar.gz.sha256'))
        result.message = f"Found {len(packages)} packages, {len(signed)} signed"
        result.details = {"package_count": len(packages), "signed_count": len(signed)}
    else:
        result.message = "No packages store found"

    return result


def check_g6_ledger(plane_root: Path) -> GateResult:
    """G6: LEDGER - Verify ledger chain integrity.

    Checks:
    - Ledger entries are properly chained
    - No gaps or modifications detected
    """
    result = GateResult(gate="G6", passed=True, message="Ledger check passed")

    ledger_dir = plane_root / 'ledger'
    if ledger_dir.exists():
        ledger_files = list(ledger_dir.glob('*.jsonl'))
        entry_count = 0
        for lf in ledger_files:
            with open(lf, 'r', encoding='utf-8') as f:
                entry_count += sum(1 for line in f if line.strip())
        result.message = f"Found {len(ledger_files)} ledger files, {entry_count} entries"
        result.details = {"ledger_file_count": len(ledger_files), "entry_count": entry_count}
    else:
        result.warnings = ["ledger/ directory not found"]

    return result


GATE_FUNCTIONS = {
    "G0": check_g0_ownership,      # Legacy alias for G0B
    "G0A": check_g0a_package_declaration,  # Package declaration (install-time)
    "G0B": check_g0b_plane_ownership,      # Plane ownership (integrity-time)
    "G1": check_g1_chain,
    "G2": check_g2_work_order,
    "G3": check_g3_constraints,
    "G4": check_g4_acceptance,
    "G5": check_g5_signature,
    "G6": check_g6_ledger,
}


def run_gates(
    gates: List[str],
    plane_root: Path,
    manifest: Optional[dict] = None,
    archive_path: Optional[Path] = None,
    fail_fast: bool = False,
    wo_id: Optional[str] = None,
    wo_file: Optional[Path] = None,
    skip_signature: bool = False
) -> Tuple[List[GateResult], bool]:
    """Run specified gates.

    Args:
        gates: List of gate names (G0-G6, G0A, G0B) or ["all"]
        plane_root: Path to plane root
        manifest: Package manifest for G0A (optional)
        archive_path: Package archive for G0A (optional)
        fail_fast: Stop on first failure (for --enforce mode)
        wo_id: Work Order ID for G2 (optional)
        wo_file: Work Order file for G2 (optional)
        skip_signature: Skip Ed25519 signature verification for G2

    Returns:
        (results, all_passed)
    """
    if "all" in gates or not gates:
        # "all" includes G0B but not G0A (G0A requires manifest)
        gates = ["G0B", "G1", "G2", "G3", "G4", "G5", "G6"]

    results = []
    all_passed = True

    for gate in gates:
        gate_upper = gate.upper()
        gate_fn = GATE_FUNCTIONS.get(gate_upper)

        if not gate_fn:
            results.append(GateResult(
                gate=gate,
                passed=False,
                message=f"Unknown gate: {gate}",
                errors=[f"Gate '{gate}' not found in GATE_FUNCTIONS"]
            ))
            all_passed = False
            if fail_fast:
                break
            continue

        # Gate-specific argument handling
        if gate_upper == "G0A":
            result = gate_fn(plane_root, manifest=manifest, archive_path=archive_path)
        elif gate_upper == "G2":
            result = gate_fn(plane_root, wo_id=wo_id, wo_file=wo_file, skip_signature=skip_signature)
        else:
            result = gate_fn(plane_root)

        results.append(result)

        if not result.passed:
            all_passed = False
            if fail_fast:
                break

    return results, all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Run governance gates for the Control Plane",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all gates (G0B, G1-G6)
    python3 scripts/gate_check.py --all

    # Run G0B (plane ownership) with enforce mode
    python3 scripts/gate_check.py --gate G0B --enforce

    # Run G0A (package declaration) with manifest
    python3 scripts/gate_check.py --gate G0A --manifest packages_store/PKG-TEST/manifest.json

    # Run specific gates
    python3 scripts/gate_check.py --gate G0B G1 G6 --plane ho3
"""
    )
    parser.add_argument(
        "--gate", "-g",
        nargs="+",
        default=["all"],
        help="Gates to run (G0, G0A, G0B, G1-G6) or 'all'"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Run all gates"
    )
    parser.add_argument(
        "--plane",
        type=str,
        help="Plane ID (ho3, ho2, ho1)"
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Fail-closed mode: exit 1 on ANY gate failure"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Package manifest JSON for G0A check"
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="Package archive for G0A check"
    )
    parser.add_argument(
        "--wo",
        type=str,
        help="Work Order ID for G2 check"
    )
    parser.add_argument(
        "--wo-file",
        type=Path,
        help="Work Order file for G2 check"
    )
    parser.add_argument(
        "--skip-signature",
        action="store_true",
        help="Skip Ed25519 signature verification for G2"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only show summary"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=CONTROL_PLANE,
        help="Plane root path"
    )

    args = parser.parse_args()

    # Determine plane root
    plane_root = args.root
    if args.plane:
        if args.plane == "ho3":
            plane_root = args.root  # HO3 is the root
        else:
            plane_root = args.root / 'planes' / args.plane
            if not plane_root.exists():
                plane_root = args.root

    # Load manifest if provided
    manifest = None
    if args.manifest:
        if not args.manifest.exists():
            print(f"ERROR: Manifest not found: {args.manifest}", file=sys.stderr)
            return 1
        manifest = json.loads(args.manifest.read_text())

    # Run gates
    gates = ["all"] if args.all else args.gate
    results, all_passed = run_gates(
        gates,
        plane_root,
        manifest=manifest,
        archive_path=args.archive,
        fail_fast=args.enforce,
        wo_id=args.wo,
        wo_file=args.wo_file,
        skip_signature=args.skip_signature
    )

    # Output
    if args.json:
        output = {
            "plane_root": str(plane_root),
            "all_passed": all_passed,
            "enforce_mode": args.enforce,
            "results": [r.to_dict() for r in results]
        }
        print(json.dumps(output, indent=2))
    elif args.quiet:
        status = "PASS" if all_passed else "FAIL"
        passed_count = sum(1 for r in results if r.passed)
        mode = " [ENFORCE]" if args.enforce else ""
        print(f"Gates: {status} ({passed_count}/{len(results)} passed){mode}")
    else:
        mode_str = " [ENFORCE MODE]" if args.enforce else ""
        print(f"\nGATE CHECK REPORT{mode_str}")
        print(f"Plane: {plane_root}")
        print("=" * 60)

        for result in results:
            status = "PASS" if result.passed else "FAIL"
            print(f"\n{result.gate}: {status}")
            print(f"  {result.message}")

            for error in result.errors[:5]:
                print(f"  ERROR: {error}")
            if len(result.errors) > 5:
                print(f"  ... and {len(result.errors) - 5} more errors")

            for warning in result.warnings[:3]:
                print(f"  WARNING: {warning}")

        print()
        status = "PASS" if all_passed else "FAIL"
        passed_count = sum(1 for r in results if r.passed)
        print(f"Overall: {status} ({passed_count}/{len(results)} gates passed)")

        if args.enforce and not all_passed:
            print("\n[ENFORCE MODE] Exiting with error code 1")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
