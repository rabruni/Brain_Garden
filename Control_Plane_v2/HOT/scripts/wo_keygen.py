#!/usr/bin/env python3
"""
wo_keygen.py - Generate Ed25519 keypair for Work Order approval.

This script generates a new Ed25519 keypair for use with wo_approve.py.
The private key should be stored securely and never committed to version control.

Usage:
    # Generate keypair to default location
    python3 scripts/wo_keygen.py --output ~/.control_plane_v2/

    # Generate with custom key ID
    python3 scripts/wo_keygen.py --output ~/.control_plane_v2/ --key-id admin-001

    # Show public key for adding to trusted_keys.json
    python3 scripts/wo_keygen.py --output /tmp --show-public
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate_keypair() -> tuple:
    """Generate Ed25519 keypair.

    Returns:
        (private_key_bytes, public_key_bytes) - both 32 bytes
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption()
    )

    public_bytes = public_key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw
    )

    return private_bytes, public_bytes


def save_private_key_pem(private_bytes: bytes, path: Path) -> None:
    """Save private key in PEM format."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    pem_data = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()
    )

    # Create parent directory with secure permissions
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write with restricted permissions (owner read/write only)
    with open(path, 'wb') as f:
        f.write(pem_data)
    os.chmod(path, 0o600)


def format_trusted_key_entry(key_id: str, public_key_b64: str, description: str = "") -> dict:
    """Format entry for trusted_keys.json."""
    return {
        "key_id": key_id,
        "algorithm": "Ed25519",
        "public_key_b64": public_key_b64,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": None,
        "roles": ["wo_approver"],
        "description": description
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate Ed25519 keypair for Work Order approval"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path.home() / ".control_plane_v2",
        help="Output directory for keypair files (default: ~/.control_plane_v2/)"
    )
    parser.add_argument(
        "--key-id",
        type=str,
        default="admin-001",
        help="Key ID to use in trusted_keys.json entry"
    )
    parser.add_argument(
        "--description",
        type=str,
        default="",
        help="Description for the key"
    )
    parser.add_argument(
        "--show-public",
        action="store_true",
        help="Print public key entry for trusted_keys.json"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing key files"
    )

    args = parser.parse_args()

    # Check cryptography library
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        print("Error: cryptography library not installed.", file=sys.stderr)
        print("Run: pip install cryptography", file=sys.stderr)
        return 1

    # Define output paths
    private_key_path = args.output / "private_key.pem"
    public_key_path = args.output / "public_key.txt"

    # Check for existing files
    if not args.force:
        if private_key_path.exists():
            print(f"Error: Private key already exists at {private_key_path}", file=sys.stderr)
            print("Use --force to overwrite", file=sys.stderr)
            return 1

    # Generate keypair
    try:
        private_bytes, public_bytes = generate_keypair()
    except Exception as e:
        print(f"Error generating keypair: {e}", file=sys.stderr)
        return 1

    # Save private key
    try:
        save_private_key_pem(private_bytes, private_key_path)
        print(f"Private key saved to: {private_key_path}")
        print(f"  (permissions: 0600 - owner read/write only)")
    except Exception as e:
        print(f"Error saving private key: {e}", file=sys.stderr)
        return 1

    # Save public key in base64
    public_key_b64 = base64.b64encode(public_bytes).decode('ascii')
    public_key_path.write_text(public_key_b64 + '\n')
    print(f"Public key saved to: {public_key_path}")

    # Create trusted_keys.json entry
    trusted_entry = format_trusted_key_entry(
        key_id=args.key_id,
        public_key_b64=public_key_b64,
        description=args.description or f"Generated by wo_keygen.py on {datetime.now().isoformat()}"
    )

    if args.show_public or True:  # Always show the entry
        print()
        print("Add this entry to config/trusted_keys.json:")
        print("-" * 60)
        print(json.dumps(trusted_entry, indent=2))
        print("-" * 60)

    print()
    print("Next steps:")
    print(f"  1. Add the public key entry to Control_Plane_v2/config/trusted_keys.json")
    print(f"  2. Keep {private_key_path} secure - never commit to git")
    print(f"  3. Use: python3 scripts/wo_approve.py --key-file {private_key_path} --key-id {args.key_id} ...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
