#!/usr/bin/env python3
"""CLI entrypoint for the Evidence Emission Standard Library.

Implements the pipe-first contract: reads JSON from stdin, writes JSON to stdout.

Usage:
    echo '{"operation": "build_evidence", ...}' | python3 -m modules.stdlib_evidence
    echo '{"operation": "hash", "data": {...}}' | python3 -m modules.stdlib_evidence

Operations:
    - build_evidence: Build evidence envelope with required fields
    - hash: Compute hash of provided data
    - reference: Build artifact reference
"""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

from modules.stdlib_evidence.hasher import hash_json
from modules.stdlib_evidence.envelope import build_evidence
from modules.stdlib_evidence.reference import build_reference


def make_response(
    status: str,
    result: Any = None,
    error: Dict[str, Any] = None,
    evidence: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Build standard response envelope."""
    response = {"status": status}

    if result is not None:
        response["result"] = result

    if error is not None:
        response["error"] = error

    if evidence is not None:
        response["evidence"] = evidence

    return response


def make_error(code: str, message: str, details: Any = None) -> Dict[str, Any]:
    """Build error object."""
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return error


def handle_build_evidence(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle build_evidence operation."""
    # Extract required fields
    session_id = request.get("session_id")
    turn_number = request.get("turn_number")
    input_data = request.get("input")
    output_data = request.get("output")

    # Validate
    if not session_id:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "session_id is required"),
        )
    if turn_number is None:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "turn_number is required"),
        )
    if input_data is None:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "input is required"),
        )
    if output_data is None:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "output is required"),
        )

    # Compute hashes
    input_hash = hash_json(input_data) if isinstance(input_data, dict) else hash_json({"value": input_data})
    output_hash = hash_json(output_data) if isinstance(output_data, dict) else hash_json({"value": output_data})

    # Extract optional fields
    work_order_id = request.get("work_order_id")
    declared_reads = request.get("declared_reads")
    declared_writes = request.get("declared_writes")
    external_calls = request.get("external_calls")
    duration_ms = request.get("duration_ms")

    # Build evidence
    evidence = build_evidence(
        session_id=session_id,
        turn_number=turn_number,
        input_hash=input_hash,
        output_hash=output_hash,
        work_order_id=work_order_id,
        declared_reads=declared_reads,
        declared_writes=declared_writes,
        external_calls=external_calls,
        duration_ms=duration_ms,
    )

    return make_response(
        "ok",
        result={
            "input_hash": input_hash,
            "output_hash": output_hash,
            "evidence": evidence,
        },
        evidence=evidence,
    )


def handle_hash(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle hash operation."""
    data = request.get("data")
    if data is None:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "data is required"),
        )

    if isinstance(data, dict):
        h = hash_json(data)
    else:
        h = hash_json({"value": data})

    # Build minimal evidence for this operation
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_hash": hash_json(request),
        "output_hash": h,
    }

    return make_response(
        "ok",
        result={"hash": h},
        evidence=evidence,
    )


def handle_reference(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle reference operation."""
    artifact_id = request.get("artifact_id")
    artifact_hash = request.get("hash")

    if not artifact_id:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "artifact_id is required"),
        )
    if not artifact_hash:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "hash is required"),
        )

    ref = build_reference(
        artifact_id=artifact_id,
        hash=artifact_hash,
        artifact_type=request.get("artifact_type"),
        path=request.get("path"),
    )

    # Build minimal evidence for this operation
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_hash": hash_json(request),
        "output_hash": hash_json(ref),
    }

    return make_response(
        "ok",
        result={"reference": ref},
        evidence=evidence,
    )


def main():
    """Main entrypoint."""
    start_time = time.time()

    # Read from stdin
    try:
        input_text = sys.stdin.read()
    except Exception as e:
        response = make_response(
            "error",
            error=make_error("READ_ERROR", f"Failed to read stdin: {e}"),
        )
        print(json.dumps(response))
        sys.exit(1)

    # Parse JSON
    try:
        request = json.loads(input_text)
    except json.JSONDecodeError as e:
        response = make_response(
            "error",
            error=make_error("INVALID_JSON", f"Failed to parse JSON: {e}"),
        )
        print(json.dumps(response))
        sys.exit(1)

    # Route to handler based on operation
    operation = request.get("operation", "build_evidence")

    if operation == "build_evidence":
        response = handle_build_evidence(request)
    elif operation == "hash":
        response = handle_hash(request)
    elif operation == "reference":
        response = handle_reference(request)
    else:
        response = make_response(
            "error",
            error=make_error(
                "UNKNOWN_OPERATION",
                f"Unknown operation: {operation}",
                details={"valid_operations": ["build_evidence", "hash", "reference"]},
            ),
        )

    # Add duration to evidence if successful
    if response.get("status") == "ok" and response.get("evidence"):
        duration_ms = int((time.time() - start_time) * 1000)
        response["evidence"]["duration_ms"] = duration_ms

    # Write to stdout
    print(json.dumps(response, ensure_ascii=False))

    # Exit with appropriate code
    sys.exit(0 if response.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
