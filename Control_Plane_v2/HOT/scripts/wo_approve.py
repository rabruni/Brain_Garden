#!/usr/bin/env python3
"""
wo_approve.py - Human CLI for Ed25519 Work Order approval.

This script is the ONLY authorized way to approve Work Orders.
Agents MUST NOT self-approve. Human review via this CLI is required.

The script:
1. Loads the Work Order file
2. Computes wo_payload_hash from canonicalized JSON
3. Signs the hash with Ed25519 private key
4. Appends WO_APPROVED event to HOT governance.jsonl

Usage:
    # Generate keypair first (one-time setup)
    python3 scripts/wo_keygen.py --output ~/.control_plane_v2/

    # Approve a Work Order
    python3 scripts/wo_approve.py \\
        --wo work_orders/ho3/WO-20260202-001.json \\
        --key-file ~/.control_plane_v2/private_key.pem \\
        --key-id admin-001 \\
        --reason "Approved per ticket #123"
"""

import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import CONTROL_PLANE
from kernel.ledger_client import LedgerClient, LedgerEntry


def canonicalize_wo(wo_data: dict) -> str:
    """Return canonical JSON string for hashing."""
    return json.dumps(wo_data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def compute_wo_payload_hash(wo_data: dict) -> str:
    """Compute deterministic SHA-256 hash of Work Order payload.

    Returns hash with 'sha256:' prefix per FMWK-000 spec.
    """
    canonical = canonicalize_wo(wo_data)
    hash_hex = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return f"sha256:{hash_hex}"


def load_private_key(key_path: Path) -> bytes:
    """Load Ed25519 private key from PEM file.

    Supports both raw 32-byte keys and PEM format.
    """
    content = key_path.read_bytes()

    # Check if it's PEM format
    if b'-----BEGIN' in content:
        from cryptography.hazmat.primitives import serialization
        private_key = serialization.load_pem_private_key(content, password=None)
        return private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption()
        )
    else:
        # Assume raw base64 or raw bytes
        try:
            return base64.b64decode(content.strip())
        except Exception:
            return content


def sign_wo_hash(wo_payload_hash: str, private_key_bytes: bytes) -> str:
    """Sign wo_payload_hash with Ed25519 private key.

    Args:
        wo_payload_hash: The hash string to sign (e.g., "sha256:abc123...")
        private_key_bytes: 32-byte Ed25519 private key

    Returns:
        Base64-encoded signature
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature = private_key.sign(wo_payload_hash.encode('utf-8'))
    return base64.b64encode(signature).decode('ascii')


def get_public_key_b64(private_key_bytes: bytes) -> str:
    """Get base64-encoded public key from private key."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw
    )
    return base64.b64encode(public_bytes).decode('ascii')


def load_work_order(wo_path: Path) -> dict:
    """Load Work Order JSON file."""
    with open(wo_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def check_already_approved(wo_id: str, plane_root: Path) -> Tuple[bool, Optional[str]]:
    """Check if WO is already approved in governance.jsonl.

    Returns:
        (is_approved, existing_hash) - existing_hash is None if not approved
    """
    ledger_path = plane_root / 'ledger' / 'governance.jsonl'
    if not ledger_path.exists():
        return False, None

    client = LedgerClient(ledger_path=ledger_path)
    entries = client.read_by_event_type('WO_APPROVED')

    for entry in entries:
        if entry.metadata.get('wo_id') == wo_id:
            return True, entry.metadata.get('wo_payload_hash')

    return False, None


def write_wo_approved(
    wo_id: str,
    wo_payload: dict,
    wo_payload_hash: str,
    signature_b64: str,
    approver_key_id: str,
    approval_reason: str,
    plane_root: Path
) -> str:
    """Write WO_APPROVED event to HOT governance.jsonl.

    Returns:
        Entry ID of the WO_APPROVED event
    """
    ledger_path = plane_root / 'ledger' / 'governance.jsonl'
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    client = LedgerClient(ledger_path=ledger_path)

    entry = LedgerEntry(
        event_type='WO_APPROVED',
        submission_id=wo_id,
        decision='APPROVED',
        reason=approval_reason,
        metadata={
            'wo_id': wo_id,
            'wo_payload': wo_payload,
            'wo_payload_hash': wo_payload_hash,
            'signature_b64': signature_b64,
            'approver_key_id': approver_key_id,
            'approved_at': datetime.now(timezone.utc).isoformat(),
        }
    )

    entry_id = client.write(entry)
    client.flush()

    return entry_id


def approve_work_order(
    wo_path: Path,
    key_path: Path,
    key_id: str,
    reason: str,
    plane_root: Path,
    force: bool = False
) -> Tuple[bool, str]:
    """Approve a Work Order with Ed25519 signature.

    Args:
        wo_path: Path to Work Order JSON file
        key_path: Path to Ed25519 private key file
        key_id: Key ID to record in approval
        reason: Human-readable approval reason
        plane_root: Path to control plane root
        force: If True, allow re-approval with different hash

    Returns:
        (success, message)
    """
    # Load Work Order
    wo_data = load_work_order(wo_path)
    wo_id = wo_data.get('work_order_id', '')

    if not wo_id:
        return False, "Work Order missing work_order_id field"

    # Compute hash
    wo_payload_hash = compute_wo_payload_hash(wo_data)

    # Check if already approved
    already_approved, existing_hash = check_already_approved(wo_id, plane_root)
    if already_approved:
        if existing_hash == wo_payload_hash:
            return False, f"Work Order {wo_id} already approved with same hash"
        elif not force:
            return False, f"Work Order {wo_id} already approved with different hash. Use --force to re-approve."

    # Load private key and sign
    try:
        private_key_bytes = load_private_key(key_path)
        signature_b64 = sign_wo_hash(wo_payload_hash, private_key_bytes)
    except ImportError:
        return False, "cryptography library not installed. Run: pip install cryptography"
    except Exception as e:
        return False, f"Signing failed: {e}"

    # Write approval to ledger
    try:
        entry_id = write_wo_approved(
            wo_id=wo_id,
            wo_payload=wo_data,
            wo_payload_hash=wo_payload_hash,
            signature_b64=signature_b64,
            approver_key_id=key_id,
            approval_reason=reason,
            plane_root=plane_root
        )
    except Exception as e:
        return False, f"Failed to write ledger: {e}"

    return True, f"Work Order {wo_id} approved. Entry ID: {entry_id}, Hash: {wo_payload_hash}"


def main():
    parser = argparse.ArgumentParser(
        description="Approve Work Order with Ed25519 signature (human approval only)"
    )
    parser.add_argument(
        "--wo", "-w",
        type=Path,
        required=True,
        help="Path to Work Order JSON file"
    )
    parser.add_argument(
        "--key-file", "-k",
        type=Path,
        required=True,
        help="Path to Ed25519 private key file"
    )
    parser.add_argument(
        "--key-id",
        type=str,
        required=True,
        help="Key ID to record in approval (must match trusted_keys.json)"
    )
    parser.add_argument(
        "--reason", "-r",
        type=str,
        required=True,
        help="Human-readable approval reason (e.g., 'Approved per ticket #123')"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=CONTROL_PLANE,
        help="Control plane root path"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force re-approval even if already approved"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    # Validate paths
    if not args.wo.exists():
        print(f"Error: Work Order file not found: {args.wo}", file=sys.stderr)
        return 1

    if not args.key_file.exists():
        print(f"Error: Private key file not found: {args.key_file}", file=sys.stderr)
        return 1

    # Execute approval
    success, message = approve_work_order(
        wo_path=args.wo,
        key_path=args.key_file,
        key_id=args.key_id,
        reason=args.reason,
        plane_root=args.root,
        force=args.force
    )

    if args.json:
        output = {"success": success, "message": message}
        print(json.dumps(output, indent=2))
    else:
        if success:
            print(f"SUCCESS: {message}")
        else:
            print(f"ERROR: {message}", file=sys.stderr)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
