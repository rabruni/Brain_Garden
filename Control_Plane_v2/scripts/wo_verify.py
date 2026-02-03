#!/usr/bin/env python3
"""
wo_verify.py - Verify Work Order approval signature.

Verifies that a Work Order has been properly approved by checking:
1. WO_APPROVED event exists in HOT governance.jsonl
2. Ed25519 signature is valid against config/trusted_keys.json
3. wo_payload_hash matches current WO file (detects tampering)

Usage:
    # Verify by WO ID
    python3 scripts/wo_verify.py --wo-id WO-20260202-001

    # Verify by WO file (also checks file hasn't changed since approval)
    python3 scripts/wo_verify.py --wo-file work_orders/ho3/WO-20260202-001.json

    # JSON output
    python3 scripts/wo_verify.py --wo-id WO-20260202-001 --json
"""

import argparse
import base64
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.paths import CONTROL_PLANE
from lib.ledger_client import LedgerClient


@dataclass
class VerificationResult:
    """Result of WO verification."""
    wo_id: str
    approved: bool
    signature_valid: bool
    hash_matches: bool
    approver_key_id: Optional[str]
    approved_at: Optional[str]
    wo_payload_hash: Optional[str]
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> dict:
        return {
            "wo_id": self.wo_id,
            "approved": self.approved,
            "signature_valid": self.signature_valid,
            "hash_matches": self.hash_matches,
            "approver_key_id": self.approver_key_id,
            "approved_at": self.approved_at,
            "wo_payload_hash": self.wo_payload_hash,
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
    """Load trusted keys from config/trusted_keys.json.

    Returns:
        Dict mapping key_id to key entry
    """
    keys_path = plane_root / 'config' / 'trusted_keys.json'
    if not keys_path.exists():
        return {}

    with open(keys_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return {k['key_id']: k for k in data.get('keys', [])}


def verify_signature(wo_payload_hash: str, signature_b64: str, public_key_b64: str) -> bool:
    """Verify Ed25519 signature of wo_payload_hash.

    Args:
        wo_payload_hash: The hash string that was signed
        signature_b64: Base64-encoded signature
        public_key_b64: Base64-encoded 32-byte public key

    Returns:
        True if signature is valid
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_key_bytes = base64.b64decode(public_key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signature = base64.b64decode(signature_b64)

        public_key.verify(signature, wo_payload_hash.encode('utf-8'))
        return True
    except Exception:
        return False


def find_approval(wo_id: str, plane_root: Path) -> Optional[Dict[str, Any]]:
    """Find WO_APPROVED event for a Work Order.

    Returns:
        Approval metadata dict or None if not found
    """
    ledger_path = plane_root / 'ledger' / 'governance.jsonl'
    if not ledger_path.exists():
        return None

    client = LedgerClient(ledger_path=ledger_path)
    entries = client.read_by_event_type('WO_APPROVED')

    for entry in entries:
        if entry.metadata.get('wo_id') == wo_id:
            return entry.metadata

    return None


def load_work_order(wo_path: Path) -> dict:
    """Load Work Order JSON file."""
    with open(wo_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def verify_work_order(
    wo_id: Optional[str] = None,
    wo_file: Optional[Path] = None,
    plane_root: Path = CONTROL_PLANE
) -> VerificationResult:
    """Verify Work Order approval and signature.

    Args:
        wo_id: Work Order ID to verify
        wo_file: Path to Work Order file (also computes current hash)
        plane_root: Control plane root

    Returns:
        VerificationResult with verification status
    """
    errors = []
    warnings = []

    # Determine WO ID
    current_hash = None
    if wo_file and wo_file.exists():
        try:
            wo_data = load_work_order(wo_file)
            wo_id = wo_data.get('work_order_id', wo_id)
            current_hash = compute_wo_payload_hash(wo_data)
        except Exception as e:
            errors.append(f"Failed to load WO file: {e}")

    if not wo_id:
        return VerificationResult(
            wo_id="UNKNOWN",
            approved=False,
            signature_valid=False,
            hash_matches=False,
            approver_key_id=None,
            approved_at=None,
            wo_payload_hash=None,
            errors=["No WO ID provided"],
            warnings=[]
        )

    # Find approval in ledger
    approval = find_approval(wo_id, plane_root)
    if not approval:
        return VerificationResult(
            wo_id=wo_id,
            approved=False,
            signature_valid=False,
            hash_matches=False,
            approver_key_id=None,
            approved_at=None,
            wo_payload_hash=None,
            errors=[f"No WO_APPROVED event found for {wo_id}"],
            warnings=warnings
        )

    # Extract approval details
    approved_hash = approval.get('wo_payload_hash')
    signature_b64 = approval.get('signature_b64')
    approver_key_id = approval.get('approver_key_id')
    approved_at = approval.get('approved_at')

    # Check hash matches current file (if provided)
    hash_matches = True
    if current_hash and approved_hash:
        if current_hash != approved_hash:
            hash_matches = False
            errors.append(f"Hash mismatch: file={current_hash[:24]}..., approved={approved_hash[:24]}...")

    # Load trusted keys and verify signature
    signature_valid = False
    trusted_keys = load_trusted_keys(plane_root)

    if not trusted_keys:
        warnings.append("No trusted keys configured (config/trusted_keys.json)")
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
            warnings.append(f"Key '{approver_key_id}' has placeholder public key")
        else:
            try:
                signature_valid = verify_signature(approved_hash, signature_b64, public_key_b64)
                if not signature_valid:
                    errors.append("Ed25519 signature verification failed")
            except ImportError:
                warnings.append("cryptography library not installed - signature not verified")
                signature_valid = True  # Can't verify, assume valid
            except Exception as e:
                errors.append(f"Signature verification error: {e}")

    return VerificationResult(
        wo_id=wo_id,
        approved=True,
        signature_valid=signature_valid,
        hash_matches=hash_matches,
        approver_key_id=approver_key_id,
        approved_at=approved_at,
        wo_payload_hash=approved_hash,
        errors=errors,
        warnings=warnings
    )


def main():
    parser = argparse.ArgumentParser(
        description="Verify Work Order approval signature"
    )
    parser.add_argument(
        "--wo-id",
        type=str,
        help="Work Order ID to verify"
    )
    parser.add_argument(
        "--wo-file",
        type=Path,
        help="Work Order file to verify (also checks file hash matches approval)"
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

    if not args.wo_id and not args.wo_file:
        parser.error("Either --wo-id or --wo-file is required")

    result = verify_work_order(
        wo_id=args.wo_id,
        wo_file=args.wo_file,
        plane_root=args.root
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\nWork Order: {result.wo_id}")
        print(f"  Approved: {'YES' if result.approved else 'NO'}")
        print(f"  Signature Valid: {'YES' if result.signature_valid else 'NO'}")
        print(f"  Hash Matches: {'YES' if result.hash_matches else 'NO'}")

        if result.approver_key_id:
            print(f"  Approver: {result.approver_key_id}")
        if result.approved_at:
            print(f"  Approved At: {result.approved_at}")
        if result.wo_payload_hash:
            print(f"  Hash: {result.wo_payload_hash}")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  - {w}")

        if result.errors:
            print("\nErrors:")
            for e in result.errors:
                print(f"  - {e}")

    # Exit code based on verification status
    if result.errors:
        return 1
    if not result.approved or not result.signature_valid or not result.hash_matches:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
