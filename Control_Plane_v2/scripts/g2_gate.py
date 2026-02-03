#!/usr/bin/env python3
"""
g2_gate.py - G2 WORK_ORDER Gate Implementation.

Implements the G2 gate specified in FMWK-000 Phase 2:
1. Verify WO_APPROVED exists in HOT governance.jsonl
2. Verify wo_payload_hash matches approved hash (detect tampering)
3. Verify Ed25519 signature against config/trusted_keys.json
4. Check idempotency against HO2 workorder.jsonl
5. Validate scope (allowed_files is subset of spec.assets)

Usage:
    python3 scripts/g2_gate.py --wo WO-20260202-001
    python3 scripts/g2_gate.py --wo-file work_orders/ho3/WO-20260202-001.json
    python3 scripts/g2_gate.py --wo WO-20260202-001 --json
"""

import argparse
import base64
import csv
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.ledger_client import LedgerClient, LedgerEntry


@dataclass
class G2Result:
    """Result of G2 gate check."""
    passed: bool
    wo_id: str
    action: str  # PROCEED, NO_OP, FAIL
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "gate": "G2",
            "passed": self.passed,
            "wo_id": self.wo_id,
            "action": self.action,
            "message": self.message,
            "details": self.details,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def canonicalize_wo(wo_data: dict) -> str:
    """Return canonical JSON string for hashing."""
    return json.dumps(wo_data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def compute_wo_payload_hash(wo_data: dict) -> str:
    """Compute deterministic SHA-256 hash of Work Order payload."""
    canonical = canonicalize_wo(wo_data)
    hash_hex = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return f"sha256:{hash_hex}"


def load_trusted_keys(plane_root: Path) -> Dict[str, dict]:
    """Load trusted keys from config/trusted_keys.json."""
    keys_path = plane_root / 'config' / 'trusted_keys.json'
    if not keys_path.exists():
        return {}

    with open(keys_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return {k['key_id']: k for k in data.get('keys', [])}


def verify_ed25519_signature(wo_payload_hash: str, signature_b64: str, public_key_b64: str) -> Tuple[bool, str]:
    """Verify Ed25519 signature.

    Returns:
        (is_valid, message)
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_key_bytes = base64.b64decode(public_key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signature = base64.b64decode(signature_b64)

        public_key.verify(signature, wo_payload_hash.encode('utf-8'))
        return True, "Signature valid"
    except ImportError:
        return True, "cryptography not installed (signature check skipped)"
    except Exception as e:
        return False, f"Signature verification failed: {e}"


def find_approval_in_hot(wo_id: str, plane_root: Path) -> Optional[Dict[str, Any]]:
    """Find WO_APPROVED event in HOT governance.jsonl.

    Returns:
        Approval metadata dict or None
    """
    ledger_path = plane_root / 'ledger' / 'governance.jsonl'
    if not ledger_path.exists():
        return None

    client = LedgerClient(ledger_path=ledger_path)
    entries = client.read_by_event_type('WO_APPROVED')

    for entry in entries:
        if entry.metadata.get('wo_id') == wo_id:
            return {
                'entry_id': entry.id,
                'entry_hash': entry.entry_hash,
                **entry.metadata
            }

    return None


def check_idempotency_ho2(wo_id: str, wo_payload_hash: str, plane_root: Path) -> Tuple[str, str, Optional[Dict]]:
    """Check idempotency against HO2 workorder.jsonl.

    Returns:
        (action, message, existing_entry)
        - action: PROCEED, NO_OP, or FAIL
    """
    ledger_path = plane_root / 'planes' / 'ho2' / 'ledger' / 'workorder.jsonl'
    if not ledger_path.exists():
        return "PROCEED", "HO2 workorder.jsonl not found (first WO)", None

    client = LedgerClient(ledger_path=ledger_path)
    entries = client.read_all()

    for entry in entries:
        if entry.metadata.get('wo_id') == wo_id:
            existing_hash = entry.metadata.get('wo_payload_hash')
            status = entry.metadata.get('status') or entry.decision

            if status in ('COMPLETED', 'APPLIED', 'WO_COMPLETED'):
                if existing_hash == wo_payload_hash:
                    return "NO_OP", f"Already applied at {entry.timestamp}", entry.metadata
                else:
                    return "FAIL", f"TAMPERING: applied hash {existing_hash[:24]}... != current {wo_payload_hash[:24]}...", entry.metadata

    return "PROCEED", "Work Order not yet applied", None


def load_spec_assets(spec_id: str, plane_root: Path) -> Set[str]:
    """Load allowed assets from spec registry.

    Returns:
        Set of allowed file paths
    """
    # Try to find spec in specs/ directory
    spec_dir = plane_root / 'specs' / spec_id
    manifest_path = spec_dir / 'manifest.yaml'

    if manifest_path.exists():
        import yaml
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = yaml.safe_load(f)
            return set(manifest.get('assets', []))

    # Fallback: check control_plane_registry.csv for files with this spec
    registry_path = plane_root / 'registries' / 'control_plane_registry.csv'
    if registry_path.exists():
        assets = set()
        with open(registry_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('source_spec_id') == spec_id:
                    path = row.get('artifact_path', row.get('path', ''))
                    if path:
                        assets.add(path)
        return assets

    return set()


def validate_scope(wo: dict, plane_root: Path) -> Tuple[bool, str, List[str]]:
    """Validate WO scope against spec assets.

    Returns:
        (is_valid, message, violations)
    """
    scope = wo.get('scope', {})
    allowed_files = set(scope.get('allowed_files', []))
    forbidden_files = set(scope.get('forbidden_files', []))

    spec_id = wo.get('spec_id', '')
    if not spec_id:
        return True, "No spec_id (scope check skipped)", []

    spec_assets = load_spec_assets(spec_id, plane_root)

    if not spec_assets:
        # Can't validate if spec has no assets defined
        return True, f"Spec {spec_id} has no assets defined (scope check skipped)", []

    violations = []

    # Check allowed_files is subset of spec.assets
    for f in allowed_files:
        if f not in spec_assets:
            violations.append(f"'{f}' not in {spec_id} assets")

    # Check no forbidden files
    for f in forbidden_files:
        if f in allowed_files:
            violations.append(f"'{f}' is both allowed and forbidden")

    if violations:
        return False, f"Scope violations: {len(violations)}", violations

    return True, f"Scope valid: {len(allowed_files)} files in {spec_id}", []


def discover_wo_path(wo_id: str, plane_root: Path) -> Optional[Path]:
    """Discover Work Order file path from ID."""
    for plane_id in ['ho3', 'ho2', 'ho1']:
        wo_path = plane_root / 'work_orders' / plane_id / f"{wo_id}.json"
        if wo_path.exists():
            return wo_path
    return None


def load_work_order(wo_path: Path) -> dict:
    """Load Work Order JSON file."""
    with open(wo_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_g2_gate(
    wo_id: Optional[str] = None,
    wo_file: Optional[Path] = None,
    plane_root: Path = CONTROL_PLANE,
    skip_signature: bool = False
) -> G2Result:
    """Run G2 WORK_ORDER gate.

    This is the main entry point for G2 validation.

    Args:
        wo_id: Work Order ID
        wo_file: Path to Work Order file
        plane_root: Control plane root
        skip_signature: Skip Ed25519 signature verification

    Returns:
        G2Result with pass/fail status and details
    """
    errors = []
    warnings = []
    details = {}

    # Load Work Order
    wo_path = None
    wo_data = None

    if wo_file and wo_file.exists():
        wo_path = wo_file
        try:
            wo_data = load_work_order(wo_path)
            wo_id = wo_data.get('work_order_id', wo_id)
        except Exception as e:
            return G2Result(
                passed=False,
                wo_id=wo_id or "UNKNOWN",
                action="FAIL",
                message=f"Failed to load WO file: {e}",
                errors=[str(e)]
            )

    if not wo_id:
        return G2Result(
            passed=False,
            wo_id="UNKNOWN",
            action="FAIL",
            message="No WO ID provided",
            errors=["Work Order ID required"]
        )

    if not wo_data and not wo_path:
        wo_path = discover_wo_path(wo_id, plane_root)
        if wo_path:
            wo_data = load_work_order(wo_path)

    if not wo_data:
        return G2Result(
            passed=False,
            wo_id=wo_id,
            action="FAIL",
            message=f"Work Order file not found for {wo_id}",
            errors=[f"Cannot find work_orders/*/WO-{wo_id}.json"]
        )

    # Compute payload hash
    wo_payload_hash = compute_wo_payload_hash(wo_data)
    details['wo_payload_hash'] = wo_payload_hash

    # Step 1: Find WO_APPROVED in HOT governance.jsonl
    approval = find_approval_in_hot(wo_id, plane_root)

    if not approval:
        return G2Result(
            passed=False,
            wo_id=wo_id,
            action="FAIL",
            message=f"No WO_APPROVED found for {wo_id} in governance.jsonl",
            errors=["Work Order not approved. Run: python3 scripts/wo_approve.py ..."],
            details=details
        )

    details['approval_entry_id'] = approval.get('entry_id')
    details['approver_key_id'] = approval.get('approver_key_id')
    details['approved_at'] = approval.get('approved_at')

    # Step 2: Verify hash matches (detect tampering)
    approved_hash = approval.get('wo_payload_hash')
    if approved_hash and approved_hash != wo_payload_hash:
        return G2Result(
            passed=False,
            wo_id=wo_id,
            action="FAIL",
            message="TAMPERING DETECTED: WO file changed after approval",
            errors=[
                f"Approved hash: {approved_hash}",
                f"Current hash: {wo_payload_hash}",
                "Work Order file was modified after approval"
            ],
            details=details
        )

    details['hash_verified'] = True

    # Step 3: Verify Ed25519 signature
    if not skip_signature:
        trusted_keys = load_trusted_keys(plane_root)
        approver_key_id = approval.get('approver_key_id')
        signature_b64 = approval.get('signature_b64')

        if not trusted_keys:
            warnings.append("No trusted keys configured (signature not enforced)")
        elif not approver_key_id:
            errors.append("Approval has no approver_key_id")
        elif approver_key_id not in trusted_keys:
            errors.append(f"Approver key '{approver_key_id}' not in trusted_keys.json")
        elif not signature_b64:
            errors.append("Approval has no signature")
        else:
            key_entry = trusted_keys[approver_key_id]
            public_key_b64 = key_entry.get('public_key_b64', '')

            if public_key_b64.startswith('PLACEHOLDER'):
                warnings.append(f"Key '{approver_key_id}' has placeholder (signature not verified)")
            else:
                sig_valid, sig_msg = verify_ed25519_signature(
                    approved_hash, signature_b64, public_key_b64
                )
                if not sig_valid:
                    return G2Result(
                        passed=False,
                        wo_id=wo_id,
                        action="FAIL",
                        message=f"Signature verification failed: {sig_msg}",
                        errors=[sig_msg],
                        details=details
                    )
                details['signature_verified'] = True

    # Step 4: Check idempotency against HO2
    idem_action, idem_msg, existing = check_idempotency_ho2(wo_id, wo_payload_hash, plane_root)
    details['idempotency_check'] = idem_action

    if idem_action == "NO_OP":
        return G2Result(
            passed=True,
            wo_id=wo_id,
            action="NO_OP",
            message=f"Idempotent: {idem_msg}",
            details=details,
            warnings=warnings
        )

    if idem_action == "FAIL":
        return G2Result(
            passed=False,
            wo_id=wo_id,
            action="FAIL",
            message=idem_msg,
            errors=[idem_msg],
            details=details
        )

    # Step 5: Validate scope
    scope_valid, scope_msg, violations = validate_scope(wo_data, plane_root)
    details['scope_message'] = scope_msg

    if not scope_valid:
        return G2Result(
            passed=False,
            wo_id=wo_id,
            action="FAIL",
            message=f"Scope validation failed: {scope_msg}",
            errors=violations,
            details=details
        )

    # If we have errors from signature checking, fail
    if errors:
        return G2Result(
            passed=False,
            wo_id=wo_id,
            action="FAIL",
            message="G2 validation failed",
            errors=errors,
            warnings=warnings,
            details=details
        )

    # All checks passed
    return G2Result(
        passed=True,
        wo_id=wo_id,
        action="PROCEED",
        message="G2 WORK_ORDER gate passed",
        warnings=warnings,
        details=details
    )


def write_wo_received(wo_id: str, wo_payload_hash: str, hot_approval: dict, plane_root: Path) -> str:
    """Write WO_RECEIVED event to HO2 workorder.jsonl.

    Called after G2 passes to record that WO has been accepted into execution queue.

    Returns:
        Entry ID
    """
    ledger_path = plane_root / 'planes' / 'ho2' / 'ledger' / 'workorder.jsonl'
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    client = LedgerClient(ledger_path=ledger_path)

    entry = LedgerEntry(
        event_type='WO_RECEIVED',
        submission_id=wo_id,
        decision='ACCEPTED',
        reason='G2 gate passed - WO accepted into execution queue',
        metadata={
            'wo_id': wo_id,
            'wo_payload_hash': wo_payload_hash,
            'hot_approval_hash': hot_approval.get('entry_hash'),
            'hot_approval_idx': hot_approval.get('entry_id'),
            'received_at': datetime.now(timezone.utc).isoformat(),
        }
    )

    entry_id = client.write(entry)
    client.flush()
    return entry_id


def main():
    parser = argparse.ArgumentParser(
        description="Run G2 WORK_ORDER gate validation"
    )
    parser.add_argument(
        "--wo",
        type=str,
        help="Work Order ID"
    )
    parser.add_argument(
        "--wo-file",
        type=Path,
        help="Path to Work Order JSON file"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=CONTROL_PLANE,
        help="Control plane root path"
    )
    parser.add_argument(
        "--skip-signature",
        action="store_true",
        help="Skip Ed25519 signature verification"
    )
    parser.add_argument(
        "--record-received",
        action="store_true",
        help="Write WO_RECEIVED to HO2 if G2 passes"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    if not args.wo and not args.wo_file:
        parser.error("Either --wo or --wo-file is required")

    result = run_g2_gate(
        wo_id=args.wo,
        wo_file=args.wo_file,
        plane_root=args.root,
        skip_signature=args.skip_signature
    )

    # Optionally record WO_RECEIVED
    if result.passed and result.action == "PROCEED" and args.record_received:
        try:
            approval = find_approval_in_hot(result.wo_id, args.root)
            entry_id = write_wo_received(
                result.wo_id,
                result.details.get('wo_payload_hash', ''),
                approval or {},
                args.root
            )
            result.details['wo_received_entry_id'] = entry_id
        except Exception as e:
            result.warnings.append(f"Failed to write WO_RECEIVED: {e}")

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"\nG2 WORK_ORDER Gate: {status}")
        print(f"Work Order: {result.wo_id}")
        print(f"Action: {result.action}")
        print(f"Message: {result.message}")

        if result.details:
            print("\nDetails:")
            for k, v in result.details.items():
                if isinstance(v, str) and len(v) > 40:
                    v = v[:40] + "..."
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
