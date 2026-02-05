"""Evidence envelope builder with required linkage fields.

Constructs evidence envelopes that tie agent execution to the Control Plane's
audit trail. Every evidence envelope includes session_id and turn_number
as required by FMWK-100 Section 7.7.

Example:
    from modules.stdlib_evidence.envelope import build_evidence

    evidence = build_evidence(
        session_id="SES-abc123",
        turn_number=1,
        input_hash="sha256:...",
        output_hash="sha256:...",
        work_order_id="WO-xyz789"
    )
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def build_evidence(
    session_id: str,
    turn_number: int,
    input_hash: str,
    output_hash: str,
    work_order_id: Optional[str] = None,
    declared_reads: Optional[List[Dict[str, Any]]] = None,
    declared_writes: Optional[List[Dict[str, Any]]] = None,
    external_calls: Optional[List[Dict[str, Any]]] = None,
    duration_ms: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build evidence envelope with required linkage fields.

    Args:
        session_id: Required session identifier (e.g., "SES-abc123")
        turn_number: Required turn number within session (1-indexed)
        input_hash: Hash of the input (e.g., "sha256:...")
        output_hash: Hash of the output (e.g., "sha256:...")
        work_order_id: Optional work order reference (e.g., "WO-xyz789")
        declared_reads: Optional list of read file records, each with
            {"path": str, "hash": str}
        declared_writes: Optional list of write file records, each with
            {"path": str, "hash": str, "size": int}
        external_calls: Optional list of external call records, each with
            {"request_id": str, "provider": str, "model": str, "cached": bool}
        duration_ms: Optional execution duration in milliseconds
        **kwargs: Additional metadata to include

    Returns:
        Evidence envelope dictionary with all required and optional fields

    Raises:
        ValueError: If session_id or turn_number is missing/invalid

    Example:
        >>> evidence = build_evidence(
        ...     session_id="SES-123",
        ...     turn_number=1,
        ...     input_hash="sha256:abc",
        ...     output_hash="sha256:def"
        ... )
        >>> evidence["session_id"]
        'SES-123'
    """
    # Validate required fields
    if not session_id:
        raise ValueError("session_id is required")
    if not isinstance(turn_number, int) or turn_number < 1:
        raise ValueError("turn_number must be a positive integer")
    if not input_hash:
        raise ValueError("input_hash is required")
    if not output_hash:
        raise ValueError("output_hash is required")

    # Build evidence envelope
    evidence: Dict[str, Any] = {
        "session_id": session_id,
        "turn_number": turn_number,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Add optional fields if provided
    if work_order_id:
        evidence["work_order_id"] = work_order_id

    if declared_reads is not None:
        evidence["declared_reads"] = declared_reads

    if declared_writes is not None:
        evidence["declared_writes"] = declared_writes

    if external_calls is not None:
        evidence["external_calls"] = external_calls

    if duration_ms is not None:
        evidence["duration_ms"] = duration_ms

    # Include any additional kwargs
    for key, value in kwargs.items():
        if key not in evidence:
            evidence[key] = value

    return evidence
