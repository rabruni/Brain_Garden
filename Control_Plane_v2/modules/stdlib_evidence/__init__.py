"""Evidence Emission Standard Library.

Provides foundational utilities for generating cryptographic evidence,
computing hashes, and building evidence envelopes that link agent execution
to the Control Plane's audit trail.

This is a Tier 0 (T0) trust baseline library.

Example usage:
    from modules.stdlib_evidence import hash_json, build_evidence

    input_data = {"query": "explain FMWK-000"}
    output_data = {"result": "..."}

    evidence = build_evidence(
        session_id="SES-abc123",
        turn_number=1,
        input_hash=hash_json(input_data),
        output_hash=hash_json(output_data)
    )
"""

from modules.stdlib_evidence.hasher import hash_json, hash_file, hash_string
from modules.stdlib_evidence.envelope import build_evidence
from modules.stdlib_evidence.reference import build_reference

__all__ = [
    "hash_json",
    "hash_file",
    "hash_string",
    "build_evidence",
    "build_reference",
]

__version__ = "0.1.0"
