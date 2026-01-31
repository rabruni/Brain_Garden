#!/usr/bin/env python3
"""
signing.py - Detached signature support for Control Plane v2.

Provides optional artifact signing and verification for package integrity.
Signatures are stored as detached .sig files alongside archives.

Supports:
- Ed25519 (via PyNaCl if available)
- HMAC-SHA256 fallback (no external deps)

Environment:
    CONTROL_PLANE_SIGNING_KEY: Path to signing key or HMAC secret
    CONTROL_PLANE_VERIFY_KEY: Path to verification key or HMAC secret

Ledger Events:
    PACKAGE_SIGNED: Signature created
    SIGNATURE_VERIFIED: Signature verified successfully
    SIGNATURE_FAILED: Signature verification failed
    SIGNATURE_MISSING: Package has no signature (warning)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.ledger_client import LedgerClient, LedgerEntry
from lib.packages import sha256_file


SIG_EXTENSION = ".sig"
SIG_VERSION = "1.0"


@dataclass
class SignatureMetadata:
    """Metadata stored in signature file."""
    version: str
    algorithm: str
    archive_hash: str
    signer: str
    timestamp: str
    signature: str

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "algorithm": self.algorithm,
            "archive_hash": self.archive_hash,
            "signer": self.signer,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }, indent=2)

    @classmethod
    def from_json(cls, data: str) -> "SignatureMetadata":
        d = json.loads(data)
        return cls(**d)


class SignatureError(Exception):
    """Raised when signature operations fail."""
    pass


class SignatureVerificationFailed(SignatureError):
    """Raised when signature verification fails."""
    pass


class SignatureMissing(SignatureError):
    """Raised when expected signature is missing."""
    pass


def _get_signing_key() -> Optional[bytes]:
    """Get signing key from environment."""
    key_ref = os.getenv("CONTROL_PLANE_SIGNING_KEY", "")
    if not key_ref:
        return None
    key_path = Path(key_ref)
    if key_path.exists():
        return key_path.read_bytes().strip()
    return key_ref.encode()


def _get_verify_key() -> Optional[bytes]:
    """Get verification key from environment."""
    key_ref = os.getenv("CONTROL_PLANE_VERIFY_KEY", "")
    if not key_ref:
        return _get_signing_key()
    key_path = Path(key_ref)
    if key_path.exists():
        return key_path.read_bytes().strip()
    return key_ref.encode()


def _try_nacl_available() -> bool:
    """Check if PyNaCl is available for Ed25519."""
    try:
        import nacl.signing
        return True
    except ImportError:
        return False


def _sign_ed25519(data: bytes, key: bytes) -> bytes:
    """Sign data with Ed25519."""
    import nacl.signing
    signing_key = nacl.signing.SigningKey(key[:32])
    signed = signing_key.sign(data)
    return signed.signature


def _verify_ed25519(data: bytes, signature: bytes, key: bytes) -> bool:
    """Verify Ed25519 signature."""
    import nacl.signing
    try:
        verify_key = nacl.signing.VerifyKey(key[:32])
        verify_key.verify(data, signature)
        return True
    except nacl.exceptions.BadSignature:
        return False


def _sign_hmac(data: bytes, key: bytes) -> bytes:
    """Sign data with HMAC-SHA256."""
    return hmac.new(key, data, hashlib.sha256).digest()


def _verify_hmac(data: bytes, signature: bytes, key: bytes) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = hmac.new(key, data, hashlib.sha256).digest()
    return hmac.compare_digest(expected, signature)


def sign_detached(
    archive_path: Path,
    key_ref: Optional[str] = None,
    signer: str = "",
) -> Path:
    """
    Create a detached signature for an archive.

    Args:
        archive_path: Path to archive file
        key_ref: Signing key (path or value). Defaults to env var.
        signer: Identity of signer (for metadata)

    Returns:
        Path to signature file (<archive>.sig)

    Raises:
        SignatureError: If signing fails
    """
    archive_path = Path(archive_path).resolve()
    if not archive_path.exists():
        raise SignatureError(f"Archive not found: {archive_path}")

    if key_ref:
        key_path = Path(key_ref)
        if key_path.exists():
            key = key_path.read_bytes().strip()
        else:
            key = key_ref.encode()
    else:
        key = _get_signing_key()

    if not key:
        raise SignatureError("No signing key available. Set CONTROL_PLANE_SIGNING_KEY")

    archive_hash = sha256_file(archive_path)
    data = archive_hash.encode()

    if _try_nacl_available() and len(key) >= 32:
        algorithm = "ed25519"
        signature = _sign_ed25519(data, key)
    else:
        algorithm = "hmac-sha256"
        signature = _sign_hmac(data, key)

    meta = SignatureMetadata(
        version=SIG_VERSION,
        algorithm=algorithm,
        archive_hash=archive_hash,
        signer=signer or os.getenv("USER", "unknown"),
        timestamp=datetime.now(timezone.utc).isoformat(),
        signature=base64.b64encode(signature).decode(),
    )

    sig_path = archive_path.with_suffix(archive_path.suffix + SIG_EXTENSION)
    sig_path.write_text(meta.to_json(), encoding="utf-8")

    _log_signing_event("PACKAGE_SIGNED", archive_path, meta)
    return sig_path


def verify_detached(
    archive_path: Path,
    sig_path: Optional[Path] = None,
    key_ref: Optional[str] = None,
) -> Tuple[bool, SignatureMetadata]:
    """
    Verify a detached signature.

    Args:
        archive_path: Path to archive file
        sig_path: Path to signature file. Defaults to <archive>.sig
        key_ref: Verification key. Defaults to env var.

    Returns:
        Tuple of (valid: bool, metadata: SignatureMetadata)

    Raises:
        SignatureMissing: If signature file not found
        SignatureVerificationFailed: If verification fails
    """
    archive_path = Path(archive_path).resolve()
    if not archive_path.exists():
        raise SignatureError(f"Archive not found: {archive_path}")

    if sig_path is None:
        sig_path = archive_path.with_suffix(archive_path.suffix + SIG_EXTENSION)

    if not sig_path.exists():
        _log_signing_event("SIGNATURE_MISSING", archive_path, None)
        raise SignatureMissing(f"Signature file not found: {sig_path}")

    try:
        meta = SignatureMetadata.from_json(sig_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise SignatureError(f"Invalid signature file: {e}")

    if key_ref:
        key_path = Path(key_ref)
        if key_path.exists():
            key = key_path.read_bytes().strip()
        else:
            key = key_ref.encode()
    else:
        key = _get_verify_key()

    if not key:
        raise SignatureError("No verification key available. Set CONTROL_PLANE_VERIFY_KEY")

    actual_hash = sha256_file(archive_path)
    if actual_hash != meta.archive_hash:
        _log_signing_event("SIGNATURE_FAILED", archive_path, meta, reason="Archive hash mismatch")
        raise SignatureVerificationFailed(
            f"Archive hash mismatch: expected {meta.archive_hash[:16]}..., got {actual_hash[:16]}..."
        )

    data = meta.archive_hash.encode()
    signature = base64.b64decode(meta.signature)

    if meta.algorithm == "ed25519":
        if not _try_nacl_available():
            raise SignatureError("Ed25519 signature requires PyNaCl")
        valid = _verify_ed25519(data, signature, key)
    elif meta.algorithm == "hmac-sha256":
        valid = _verify_hmac(data, signature, key)
    else:
        raise SignatureError(f"Unknown algorithm: {meta.algorithm}")

    if not valid:
        _log_signing_event("SIGNATURE_FAILED", archive_path, meta, reason="Signature invalid")
        raise SignatureVerificationFailed("Signature verification failed")

    _log_signing_event("SIGNATURE_VERIFIED", archive_path, meta)
    return True, meta


def has_signature(archive_path: Path) -> bool:
    """Check if an archive has a signature file."""
    sig_path = Path(archive_path).with_suffix(Path(archive_path).suffix + SIG_EXTENSION)
    return sig_path.exists()


def get_signature_path(archive_path: Path) -> Path:
    """Get the expected signature path for an archive."""
    return Path(archive_path).with_suffix(Path(archive_path).suffix + SIG_EXTENSION)


def _log_signing_event(
    event_type: str,
    archive_path: Path,
    meta: Optional[SignatureMetadata],
    reason: str = "",
) -> None:
    """Log a signing event to the ledger."""
    try:
        ledger = LedgerClient()
        entry = LedgerEntry(
            event_type=f"signing_{event_type.lower()}",
            submission_id=str(archive_path.name),
            decision=event_type,
            reason=reason or f"{event_type}: {archive_path.name}",
            metadata={
                "archive": str(archive_path),
                "algorithm": meta.algorithm if meta else "",
                "signer": meta.signer if meta else "",
                "timestamp": meta.timestamp if meta else "",
                "archive_hash": meta.archive_hash if meta else "",
            },
        )
        ledger.write(entry)
    except Exception:
        pass
