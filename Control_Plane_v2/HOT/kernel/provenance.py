#!/usr/bin/env python3
"""
provenance.py - First-class attestation framework for Control Plane v2.

Provides provenance attestations for packages, binding archive content
to build metadata and source information for supply chain security.

Schema Version: 1.0

Attestations are stored as detached .attestation.json files alongside archives.
Optional signing creates .attestation.json.sig files.

Environment:
    CONTROL_PLANE_ATTEST_PACKAGES: If "1", auto-generate attestations on pack
    CONTROL_PLANE_ALLOW_UNATTESTED: If "1", allow installing unattested packages

Ledger Events:
    ATTESTATION_CREATED: Attestation generated
    ATTESTATION_SIGNED: Attestation signed
    ATTESTATION_VERIFIED: Attestation verified successfully
    ATTESTATION_FAILED: Attestation verification failed
    ATTESTATION_MISSING: Package has no attestation
    ATTESTATION_WAIVED: Unattested package installed with waiver
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.packages import sha256_file
from kernel.ledger_client import LedgerClient, LedgerEntry


ATTESTATION_EXTENSION = ".attestation.json"
ATTESTATION_SIG_EXTENSION = ".attestation.json.sig"
ATTESTATION_SCHEMA_VERSION = "1.0"


# --- Exceptions ---

class AttestationError(Exception):
    """Base exception for attestation operations."""
    pass


class AttestationVerificationFailed(AttestationError):
    """Raised when attestation verification fails."""
    pass


class AttestationMissing(AttestationError):
    """Raised when expected attestation is missing."""
    pass


class AttestationDigestMismatch(AttestationError):
    """Raised when attestation digest doesn't match archive."""
    pass


# --- Data Models ---

@dataclass
class BuilderInfo:
    """Information about the build tool."""
    tool: str = "control_plane_package_pack"
    tool_version: str = "2.0.0"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BuilderInfo":
        return cls(**data)


@dataclass
class SourceInfo:
    """Information about the source code."""
    repo: Optional[str] = None
    revision: Optional[str] = None
    branch: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "SourceInfo":
        return cls(
            repo=data.get("repo"),
            revision=data.get("revision"),
            branch=data.get("branch"),
        )


@dataclass
class Attestation:
    """
    Provenance attestation binding archive to build metadata.

    Per FMWK-ATT-001: Attestations provide a cryptographic binding between
    an archive's content hash and its build/source provenance.
    """
    schema_version: str = ATTESTATION_SCHEMA_VERSION
    package_id: str = ""
    package_digest_sha256: str = ""
    built_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    builder: BuilderInfo = field(default_factory=BuilderInfo)
    source: Optional[SourceInfo] = None
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "package_digest_sha256": self.package_digest_sha256,
            "built_at": self.built_at,
            "builder": self.builder.to_dict(),
        }
        if self.source:
            data["source"] = self.source.to_dict()
        if self.metadata:
            data["metadata"] = self.metadata
        return json.dumps(data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Attestation":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls(
            schema_version=data.get("schema_version", ATTESTATION_SCHEMA_VERSION),
            package_id=data.get("package_id", ""),
            package_digest_sha256=data.get("package_digest_sha256", ""),
            built_at=data.get("built_at", ""),
            builder=BuilderInfo.from_dict(data.get("builder", {})),
            source=SourceInfo.from_dict(data["source"]) if data.get("source") else None,
            metadata=data.get("metadata", {}),
        )


# --- Path Helpers ---

def get_attestation_path(archive_path: Path) -> Path:
    """Get the expected attestation path for an archive."""
    return Path(str(archive_path) + ATTESTATION_EXTENSION)


def get_attestation_sig_path(archive_path: Path) -> Path:
    """Get the expected attestation signature path for an archive."""
    return Path(str(archive_path) + ATTESTATION_SIG_EXTENSION)


def has_attestation(archive_path: Path) -> bool:
    """Check if an archive has an attestation file."""
    return get_attestation_path(archive_path).exists()


# --- Core Functions ---

def create_attestation(
    archive_path: Path,
    package_id: str,
    source_repo: Optional[str] = None,
    source_revision: Optional[str] = None,
    source_branch: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Path:
    """
    Create a provenance attestation for an archive.

    Args:
        archive_path: Path to archive file
        package_id: Package identifier
        source_repo: Optional source repository URL
        source_revision: Optional source commit SHA
        source_branch: Optional source branch name
        metadata: Optional additional metadata

    Returns:
        Path to attestation file (<archive>.attestation.json)

    Raises:
        AttestationError: If attestation creation fails
    """
    archive_path = Path(archive_path).resolve()
    if not archive_path.exists():
        raise AttestationError(f"Archive not found: {archive_path}")

    # Compute archive digest
    archive_digest = sha256_file(archive_path)

    # Build source info if provided
    source = None
    if source_repo or source_revision or source_branch:
        source = SourceInfo(
            repo=source_repo,
            revision=source_revision,
            branch=source_branch,
        )

    # Create attestation
    attestation = Attestation(
        package_id=package_id,
        package_digest_sha256=archive_digest,
        builder=BuilderInfo(),
        source=source,
        metadata=metadata or {},
    )

    # Write attestation file
    attestation_path = get_attestation_path(archive_path)
    attestation_path.write_text(attestation.to_json(), encoding="utf-8")

    # Log to ledger
    _log_attestation_event(
        "ATTESTATION_CREATED",
        archive_path,
        attestation,
    )

    return attestation_path


def sign_attestation(
    attestation_path: Path,
    key_ref: Optional[str] = None,
    signer: str = "",
) -> Path:
    """
    Sign an attestation file.

    Args:
        attestation_path: Path to attestation file
        key_ref: Signing key (path or value). Defaults to env var.
        signer: Identity of signer

    Returns:
        Path to signature file (<attestation>.sig)

    Raises:
        AttestationError: If signing fails
    """
    from kernel.signing import sign_detached, SignatureError

    attestation_path = Path(attestation_path).resolve()
    if not attestation_path.exists():
        raise AttestationError(f"Attestation not found: {attestation_path}")

    try:
        sig_path = sign_detached(attestation_path, key_ref=key_ref, signer=signer)

        # Rename to attestation signature naming
        attestation_sig_path = Path(str(attestation_path) + ".sig")
        if sig_path != attestation_sig_path:
            sig_path.rename(attestation_sig_path)
            sig_path = attestation_sig_path

        # Log to ledger
        _log_attestation_event(
            "ATTESTATION_SIGNED",
            attestation_path,
            None,
            signer=signer,
        )

        return sig_path

    except SignatureError as e:
        raise AttestationError(f"Failed to sign attestation: {e}")


def verify_attestation(
    archive_path: Path,
    attestation_path: Optional[Path] = None,
) -> Tuple[bool, Attestation]:
    """
    Verify a provenance attestation.

    Args:
        archive_path: Path to archive file
        attestation_path: Path to attestation file. Defaults to <archive>.attestation.json

    Returns:
        Tuple of (valid: bool, attestation: Attestation)

    Raises:
        AttestationMissing: If attestation file not found
        AttestationDigestMismatch: If archive digest doesn't match
        AttestationVerificationFailed: If verification fails
    """
    archive_path = Path(archive_path).resolve()
    if not archive_path.exists():
        raise AttestationError(f"Archive not found: {archive_path}")

    if attestation_path is None:
        attestation_path = get_attestation_path(archive_path)

    if not attestation_path.exists():
        _log_attestation_event("ATTESTATION_MISSING", archive_path, None)
        raise AttestationMissing(f"Attestation file not found: {attestation_path}")

    # Load attestation
    try:
        attestation = Attestation.from_json(
            attestation_path.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        _log_attestation_event(
            "ATTESTATION_FAILED",
            archive_path,
            None,
            reason=f"Invalid attestation JSON: {e}",
        )
        raise AttestationVerificationFailed(f"Invalid attestation file: {e}")

    # Verify archive digest matches attestation
    actual_digest = sha256_file(archive_path)
    if actual_digest != attestation.package_digest_sha256:
        _log_attestation_event(
            "ATTESTATION_FAILED",
            archive_path,
            attestation,
            reason="Archive digest mismatch",
        )
        raise AttestationDigestMismatch(
            f"Archive digest mismatch: "
            f"attestation={attestation.package_digest_sha256[:16]}..., "
            f"actual={actual_digest[:16]}..."
        )

    # Verify schema version
    if attestation.schema_version != ATTESTATION_SCHEMA_VERSION:
        _log_attestation_event(
            "ATTESTATION_FAILED",
            archive_path,
            attestation,
            reason=f"Unknown schema version: {attestation.schema_version}",
        )
        raise AttestationVerificationFailed(
            f"Unknown attestation schema version: {attestation.schema_version}"
        )

    # Log success
    _log_attestation_event("ATTESTATION_VERIFIED", archive_path, attestation)

    return True, attestation


def verify_attestation_signature(
    attestation_path: Path,
    key_ref: Optional[str] = None,
) -> bool:
    """
    Verify the signature on an attestation file.

    Args:
        attestation_path: Path to attestation file
        key_ref: Verification key. Defaults to env var.

    Returns:
        True if signature is valid

    Raises:
        AttestationError: If signature verification fails
    """
    from kernel.signing import verify_detached, SignatureError, SignatureVerificationFailed

    attestation_path = Path(attestation_path).resolve()
    sig_path = Path(str(attestation_path) + ".sig")

    if not sig_path.exists():
        raise AttestationError(f"Attestation signature not found: {sig_path}")

    try:
        valid, _ = verify_detached(attestation_path, sig_path=sig_path, key_ref=key_ref)
        return valid
    except SignatureVerificationFailed as e:
        raise AttestationError(f"Attestation signature verification failed: {e}")
    except SignatureError as e:
        raise AttestationError(f"Attestation signature error: {e}")


def log_attestation_waiver(
    archive_path: Path,
    package_id: str,
    reason: str = "",
    actor: str = "",
) -> None:
    """
    Log an attestation waiver to the ledger.

    Called when CONTROL_PLANE_ALLOW_UNATTESTED=1 allows an unattested package.
    """
    _log_attestation_event(
        "ATTESTATION_WAIVED",
        archive_path,
        None,
        reason=reason or "Unattested package installed with CONTROL_PLANE_ALLOW_UNATTESTED=1",
        package_id=package_id,
        actor=actor,
    )


def compute_attestation_digest(attestation_path: Path) -> str:
    """Compute SHA256 digest of an attestation file."""
    return sha256_file(attestation_path)


# --- Ledger Logging ---

def _log_attestation_event(
    event_type: str,
    archive_path: Path,
    attestation: Optional[Attestation],
    reason: str = "",
    package_id: str = "",
    signer: str = "",
    actor: str = "",
) -> None:
    """Log an attestation event to the ledger."""
    try:
        ledger = LedgerClient()

        metadata = {
            "archive": str(archive_path),
        }

        if attestation:
            metadata.update({
                "schema_version": attestation.schema_version,
                "package_id": attestation.package_id,
                "package_digest": attestation.package_digest_sha256[:16] + "...",
                "built_at": attestation.built_at,
                "builder_tool": attestation.builder.tool,
            })
            if attestation.source:
                metadata["source_repo"] = attestation.source.repo or ""
                metadata["source_revision"] = attestation.source.revision or ""
        elif package_id:
            metadata["package_id"] = package_id

        if signer:
            metadata["signer"] = signer
        if actor:
            metadata["actor"] = actor

        entry = LedgerEntry(
            event_type=f"provenance_{event_type.lower()}",
            submission_id=package_id or (attestation.package_id if attestation else str(archive_path.name)),
            decision=event_type,
            reason=reason or f"{event_type}: {archive_path.name}",
            metadata=metadata,
        )
        ledger.write(entry)
    except Exception:
        # Don't fail on ledger errors
        pass
