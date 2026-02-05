"""Artifact reference builder for ledger entries.

Creates standardized references to artifacts that can be included in
ledger entries and evidence envelopes.

Example:
    from modules.stdlib_evidence.reference import build_reference

    ref = build_reference(
        artifact_id="PKG-KERNEL-001",
        hash="sha256:abc123..."
    )
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def build_reference(
    artifact_id: str,
    hash: str,
    artifact_type: Optional[str] = None,
    path: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build artifact reference for ledger entries.

    Args:
        artifact_id: Identifier of the artifact (e.g., "PKG-KERNEL-001",
            "FMWK-100", "lib/merkle.py")
        hash: Hash of the artifact (e.g., "sha256:...")
        artifact_type: Optional type of artifact ("package", "framework",
            "spec", "file")
        path: Optional path to artifact
        **kwargs: Additional metadata to include

    Returns:
        Reference dictionary with artifact_id, hash, timestamp, and
        any optional fields

    Example:
        >>> ref = build_reference("PKG-001", "sha256:abc")
        >>> ref["artifact_id"]
        'PKG-001'
    """
    reference: Dict[str, Any] = {
        "artifact_id": artifact_id,
        "hash": hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if artifact_type:
        reference["artifact_type"] = artifact_type

    if path:
        reference["path"] = path

    # Include any additional kwargs
    for key, value in kwargs.items():
        if key not in reference:
            reference[key] = value

    return reference
