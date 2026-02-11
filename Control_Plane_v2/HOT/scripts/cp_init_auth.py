#!/usr/bin/env python3
"""
cp_init_auth.py - Initialize Control Plane external auth secrets.

Creates secrets file OUTSIDE plane root (fail-closed boundary preserved).
Logs initialization event to ledger (without exposing secret).

The external secrets approach preserves the invariant:
"NOTHING unaccounted-for inside governed roots"

Usage:
    python3 scripts/cp_init_auth.py [--path ~/.control_plane_v2/secrets.env]
    python3 scripts/cp_init_auth.py --force  # Rotate existing secrets
"""
from __future__ import annotations

import argparse
import hmac
import secrets
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.paths import CONTROL_PLANE
from kernel.ledger_client import LedgerClient, LedgerEntry


DEFAULT_SECRETS_PATH = Path.home() / ".control_plane_v2" / "secrets.env"


def generate_token(secret: str, user: str) -> str:
    """Generate HMAC token for user."""
    sig = hmac.new(secret.encode(), user.encode(), sha256).hexdigest()
    return f"{user}:{sig}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize Control Plane auth secrets")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_SECRETS_PATH,
        help=f"Secrets file path (default: {DEFAULT_SECRETS_PATH})"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing secrets file (rotates secrets)"
    )
    args = parser.parse_args()

    secrets_path = args.path.expanduser().resolve()

    # Validate: must be OUTSIDE plane root
    try:
        secrets_path.relative_to(CONTROL_PLANE)
        print(f"ERROR: Secrets path must be OUTSIDE plane root: {CONTROL_PLANE}")
        print(f"       Given path: {secrets_path}")
        return 1
    except ValueError:
        pass  # Good - path is outside plane root

    # Check existing
    is_rotation = secrets_path.exists()
    if is_rotation and not args.force:
        print(f"ERROR: Secrets file already exists: {secrets_path}")
        print("       Use --force to overwrite (rotates secrets)")
        return 1

    # Generate secrets
    secret = secrets.token_hex(32)
    admin_token = generate_token(secret, "admin")
    maintainer_token = generate_token(secret, "maintainer")

    # Create directory
    secrets_path.parent.mkdir(parents=True, exist_ok=True)

    # Write secrets file (export format for direct sourcing)
    secrets_path.write_text(f"""# Control Plane Auth Secrets
# Generated: {datetime.now(timezone.utc).isoformat()}
# Location: OUTSIDE plane root (by design)
# DO NOT COMMIT TO VERSION CONTROL
# Usage: source {secrets_path}

export CONTROL_PLANE_SHARED_SECRET={secret}

# Pre-generated tokens (user:hmac_signature)
export CONTROL_PLANE_TOKEN_ADMIN={admin_token}
export CONTROL_PLANE_TOKEN_MAINTAINER={maintainer_token}

# Convenience alias
export CONTROL_PLANE_TOKEN=$CONTROL_PLANE_TOKEN_ADMIN
""")

    # Set restrictive permissions (owner read/write only)
    secrets_path.chmod(0o600)

    # Log to ledger (WITHOUT exposing secret)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    decision = "ROTATED" if is_rotation else "CREATED"

    try:
        ledger = LedgerClient()
        ledger.write(LedgerEntry(
            event_type="auth_secrets_initialized",
            submission_id=f"AUTH-INIT-{timestamp}",
            decision=decision,
            reason=f"External auth secrets file {'rotated' if is_rotation else 'created'}",
            metadata={
                "secrets_path": str(secrets_path),
                "users": ["admin", "maintainer"],
                "algorithm": "hmac-sha256",
                "actor": "cp_init_auth",
                "is_rotation": is_rotation,
                # NOTE: Secret NOT logged (security)
            }
        ))
        ledger.flush()
    except Exception as e:
        print(f"WARNING: Could not log to ledger: {e}")

    action = "Rotated" if is_rotation else "Created"
    print(f"{action}: {secrets_path}")
    print(f"Permissions: 600 (owner read/write only)")
    print()
    print("Usage (Option A - point to file):")
    print(f"  export CONTROL_PLANE_SECRETS_FILE={secrets_path}")
    print("  python3 scripts/cp_version_checkpoint.py --label 'test'")
    print()
    print("Usage (Option B - source directly):")
    print(f"  source {secrets_path}")
    print("  python3 scripts/cp_version_checkpoint.py --token $CONTROL_PLANE_TOKEN --label 'test'")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
