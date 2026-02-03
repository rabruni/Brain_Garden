#!/usr/bin/env python3
"""
g5_gate.py - G5 SIGNATURE Gate Implementation.

Implements the G5 gate specified in FMWK-000 Phase 3:
1. Compute changeset digest (Merkle root of changed files)
2. Create attestation with wo_id, spec_id, changeset_digest, timestamp
3. Sign attestation with build key (or waive if key not configured)

Per user decision Q3=C: Role-based keys (signer role separate from wo_approver).
Per user decision: Create build-001 signing key separate from approval keys.

Usage:
    python3 scripts/g5_gate.py --wo-file work_orders/ho3/WO-TEST-001.json --workspace /tmp/workspace
"""

import argparse
import base64
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE


@dataclass
class Attestation:
    """Attestation for a changeset."""
    attestation_id: str
    wo_id: str
    spec_id: str
    changeset_digest: str
    timestamp: str
    signer_key_id: Optional[str] = None
    signature_b64: Optional[str] = None
    signature_waived: bool = False
    waiver_reason: Optional[str] = None

    def to_dict(self) -> dict:
        result = {
            'attestation_id': self.attestation_id,
            'wo_id': self.wo_id,
            'spec_id': self.spec_id,
            'changeset_digest': self.changeset_digest,
            'timestamp': self.timestamp,
        }
        if self.signer_key_id:
            result['signer_key_id'] = self.signer_key_id
        if self.signature_b64:
            result['signature_b64'] = self.signature_b64
        if self.signature_waived:
            result['signature_waived'] = True
            result['waiver_reason'] = self.waiver_reason
        return result


@dataclass
class G5Result:
    """Result of G5 gate check."""
    passed: bool
    message: str
    attestation: Optional[Attestation] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "gate": "G5",
            "passed": self.passed,
            "message": self.message,
            "attestation": self.attestation.to_dict() if self.attestation else None,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def compute_changeset_digest(changed_files: List[str], workspace_root: Path) -> Tuple[str, List[str]]:
    """Compute Merkle root of changed files.

    Args:
        changed_files: List of relative file paths that changed
        workspace_root: Root directory to resolve paths

    Returns:
        (digest, file_hashes) - The digest and list of individual file hashes
    """
    file_hashes = []

    for rel_path in sorted(changed_files):
        full_path = workspace_root / rel_path
        if full_path.exists():
            file_hash = compute_file_hash(full_path)
            file_hashes.append(f"{rel_path}:{file_hash}")

    if not file_hashes:
        # Empty changeset
        return "sha256:" + hashlib.sha256(b"EMPTY_CHANGESET").hexdigest(), []

    # Combine all hashes into a Merkle-like digest
    combined = '\n'.join(file_hashes)
    digest = "sha256:" + hashlib.sha256(combined.encode('utf-8')).hexdigest()

    return digest, file_hashes


def load_signing_keys(plane_root: Path) -> Dict[str, dict]:
    """Load signing keys from config/signing_keys.json or trusted_keys.json."""
    # First try dedicated signing_keys.json
    signing_keys_path = plane_root / 'config' / 'signing_keys.json'
    if signing_keys_path.exists():
        with open(signing_keys_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        keys = {k['key_id']: k for k in data.get('keys', []) if 'signer' in k.get('roles', [])}
        if keys:
            return keys

    # Fallback to trusted_keys.json
    trusted_keys_path = plane_root / 'config' / 'trusted_keys.json'
    if trusted_keys_path.exists():
        with open(trusted_keys_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {k['key_id']: k for k in data.get('keys', []) if 'signer' in k.get('roles', [])}

    return {}


def load_private_key(key_id: str, plane_root: Path) -> Optional[Any]:
    """Load Ed25519 private key for signing.

    Looks for key in:
    1. ~/.control_plane_v2/{key_id}.pem
    2. ~/.control_plane_v2/private_key.pem (if key_id is default)

    Returns:
        Ed25519PrivateKey or None
    """
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
    except ImportError:
        return None

    home = Path.home()
    key_paths = [
        home / '.control_plane_v2' / f'{key_id}.pem',
        home / '.control_plane_v2' / 'build_key.pem',
        home / '.control_plane_v2' / 'private_key.pem',
    ]

    for key_path in key_paths:
        if key_path.exists():
            try:
                with open(key_path, 'rb') as f:
                    private_key = load_pem_private_key(f.read(), password=None)
                return private_key
            except Exception:
                continue

    return None


def sign_attestation(attestation_data: dict, private_key: Any) -> str:
    """Sign attestation data with Ed25519 private key.

    Args:
        attestation_data: Dict to sign (will be canonicalized)
        private_key: Ed25519PrivateKey

    Returns:
        Base64-encoded signature
    """
    canonical = json.dumps(attestation_data, sort_keys=True, separators=(',', ':'))
    signature = private_key.sign(canonical.encode('utf-8'))
    return base64.b64encode(signature).decode('utf-8')


def create_attestation(
    wo_id: str,
    spec_id: str,
    changeset_digest: str,
    signing_key: Optional[dict],
    private_key: Optional[Any],
    plane_root: Path
) -> Attestation:
    """Create attestation for changeset.

    Args:
        wo_id: Work Order ID
        spec_id: Spec ID
        changeset_digest: Computed digest of changed files
        signing_key: Key entry from signing_keys.json (or None)
        private_key: Loaded private key (or None)
        plane_root: Control plane root

    Returns:
        Attestation object
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    attestation_id = f"ATT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    attestation = Attestation(
        attestation_id=attestation_id,
        wo_id=wo_id,
        spec_id=spec_id,
        changeset_digest=changeset_digest,
        timestamp=timestamp,
    )

    if signing_key and private_key:
        # Sign the attestation
        attestation.signer_key_id = signing_key['key_id']

        attestation_data = {
            'attestation_id': attestation_id,
            'wo_id': wo_id,
            'spec_id': spec_id,
            'changeset_digest': changeset_digest,
            'timestamp': timestamp,
        }

        try:
            attestation.signature_b64 = sign_attestation(attestation_data, private_key)
        except Exception as e:
            attestation.signature_waived = True
            attestation.waiver_reason = f"Signing failed: {e}"
    elif signing_key:
        # Key configured but private key not available
        attestation.signer_key_id = signing_key['key_id']
        attestation.signature_waived = True
        attestation.waiver_reason = "Private key not found"
    else:
        # No signing key configured
        attestation.signature_waived = True
        attestation.waiver_reason = "No signing key configured"

    return attestation


def run_g5_gate(
    wo: dict,
    changed_files: List[str],
    workspace_root: Path,
    plane_root: Path = CONTROL_PLANE
) -> G5Result:
    """Run G5 SIGNATURE gate.

    This gate creates a signed attestation for the changeset.

    Args:
        wo: Work Order dict
        changed_files: List of changed file paths (relative to workspace)
        workspace_root: Path to isolated workspace
        plane_root: Control plane root

    Returns:
        G5Result with attestation
    """
    warnings = []
    details = {}

    wo_id = wo.get('work_order_id', 'UNKNOWN')
    spec_id = wo.get('spec_id', '')

    details['wo_id'] = wo_id
    details['spec_id'] = spec_id
    details['changed_file_count'] = len(changed_files)

    # Compute changeset digest
    changeset_digest, file_hashes = compute_changeset_digest(changed_files, workspace_root)
    details['changeset_digest'] = changeset_digest
    details['file_hashes'] = file_hashes[:10]  # First 10 for details
    if len(file_hashes) > 10:
        details['file_hashes_truncated'] = True

    # Load signing key
    signing_keys = load_signing_keys(plane_root)
    signing_key = signing_keys.get('build-001')

    if not signing_key:
        warnings.append("No build-001 signing key configured in signing_keys.json")
        # Check if any signer key exists
        if signing_keys:
            first_key = list(signing_keys.values())[0]
            signing_key = first_key
            warnings.append(f"Using alternate signing key: {first_key['key_id']}")

    # Try to load private key
    private_key = None
    if signing_key:
        key_id = signing_key['key_id']
        public_key_b64 = signing_key.get('public_key_b64', '')

        if public_key_b64.startswith('PLACEHOLDER'):
            warnings.append(f"Key '{key_id}' has placeholder public key (signature waived)")
        else:
            private_key = load_private_key(key_id, plane_root)
            if not private_key:
                warnings.append(f"Private key for '{key_id}' not found (signature waived)")

    # Create attestation
    attestation = create_attestation(
        wo_id=wo_id,
        spec_id=spec_id,
        changeset_digest=changeset_digest,
        signing_key=signing_key,
        private_key=private_key,
        plane_root=plane_root
    )

    details['signature_waived'] = attestation.signature_waived
    if attestation.waiver_reason:
        details['waiver_reason'] = attestation.waiver_reason

    # G5 passes even with waiver (Phase 3 allows waiver)
    if attestation.signature_waived:
        message = f"G5 PASSED (WAIVED): Attestation created without signature"
    else:
        message = f"G5 PASSED: Attestation signed by {attestation.signer_key_id}"

    return G5Result(
        passed=True,
        message=message,
        attestation=attestation,
        warnings=warnings,
        details=details
    )


def load_work_order(wo_path: Path) -> dict:
    """Load Work Order JSON file."""
    with open(wo_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_changed_files_from_scope(wo: dict) -> List[str]:
    """Extract changed files from WO scope (for standalone execution)."""
    scope = wo.get('scope', {})
    return scope.get('allowed_files', [])


def main():
    parser = argparse.ArgumentParser(
        description="Run G5 SIGNATURE gate - create changeset attestation"
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
        help="Path to isolated workspace (defaults to plane root)"
    )
    parser.add_argument(
        "--changed-files",
        nargs="+",
        help="List of changed files (defaults to WO scope.allowed_files)"
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

    workspace = args.workspace or args.root
    changed_files = args.changed_files or get_changed_files_from_scope(wo)

    result = run_g5_gate(
        wo=wo,
        changed_files=changed_files,
        workspace_root=workspace,
        plane_root=args.root
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        waiver = " (WAIVED)" if result.attestation and result.attestation.signature_waived else ""
        print(f"\nG5 SIGNATURE Gate: {status}{waiver}")
        print(f"Message: {result.message}")

        if result.attestation:
            print("\nAttestation:")
            print(f"  ID: {result.attestation.attestation_id}")
            print(f"  WO: {result.attestation.wo_id}")
            print(f"  Spec: {result.attestation.spec_id}")
            print(f"  Digest: {result.attestation.changeset_digest[:40]}...")
            if result.attestation.signer_key_id:
                print(f"  Signer: {result.attestation.signer_key_id}")
            if result.attestation.signature_waived:
                print(f"  Waiver: {result.attestation.waiver_reason}")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  - {w}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
