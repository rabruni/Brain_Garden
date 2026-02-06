#!/usr/bin/env python3
"""CLI entrypoint for Universal Shell module.

Implements pipe-first contract per FMWK-100 §7.

Usage:
    echo '{"operation": "pkg_list"}' | python3 -m modules.shell
    echo '{"operation": "gate_status"}' | python3 -m modules.shell
    echo '{"operation": "pkg_info", "package_id": "PKG-TEST-001"}' | python3 -m modules.shell

Core Operations:
    - pkg_list: List installed packages
    - pkg_info: Get package details (requires package_id)
    - ledger_query: Query ledger entries (optional: type, limit)
    - gate_status: Get gate status
    - compliance: Get compliance summary
    - trace: Trace artifact (requires artifact_id)
    - signal_status: Get current signals
    - execute_command: Execute shell command (requires command)

Package Compliance Operations (Agent Guidance):
    - manifest_requirements: Get manifest.json field requirements
    - packaging_workflow: Get step-by-step packaging workflow
    - troubleshoot: Get troubleshooting guide (optional: error_type)
    - example_manifest: Get example manifest (optional: package_type)
    - list_frameworks: List registered frameworks
    - list_specs: List registered specs (optional: framework_id)
    - spec_info: Get spec manifest (requires spec_id)
    - governed_roots: List governed roots
    - explain_path: Explain path classification (requires path)
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
CP_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(CP_ROOT))

from modules.shell.operations import (
    handle_pkg_list,
    handle_pkg_info,
    handle_ledger_query,
    handle_gate_status,
    handle_compliance,
    handle_trace,
    handle_signal_status,
    handle_execute_command,
    # Package compliance operations (agent guidance)
    handle_manifest_requirements,
    handle_packaging_workflow,
    handle_troubleshoot,
    handle_example_manifest,
    handle_list_frameworks,
    handle_list_specs,
    handle_spec_info,
    handle_governed_roots,
    handle_explain_path,
)


# Operation dispatch table
OPERATIONS = {
    # Core operations
    "pkg_list": handle_pkg_list,
    "pkg_info": handle_pkg_info,
    "ledger_query": handle_ledger_query,
    "gate_status": handle_gate_status,
    "compliance": handle_compliance,
    "trace": handle_trace,
    "signal_status": handle_signal_status,
    "execute_command": handle_execute_command,
    # Package compliance operations (agent guidance)
    "manifest_requirements": handle_manifest_requirements,
    "packaging_workflow": handle_packaging_workflow,
    "troubleshoot": handle_troubleshoot,
    "example_manifest": handle_example_manifest,
    "list_frameworks": handle_list_frameworks,
    "list_specs": handle_list_specs,
    "spec_info": handle_spec_info,
    "governed_roots": handle_governed_roots,
    "explain_path": handle_explain_path,
}


def make_response(
    status: str,
    result: Any = None,
    error: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build standard response envelope per FMWK-100 §7.

    Args:
        status: "ok" or "error"
        result: Operation-specific result (for ok responses)
        error: Error object with code, message, details (for error responses)
        evidence: Evidence object with hashes, timestamps, declared reads/writes

    Returns:
        Response envelope dict
    """
    response = {"status": status}

    if result is not None:
        response["result"] = result

    if error is not None:
        response["error"] = error

    if evidence is not None:
        response["evidence"] = evidence

    return response


def make_error(code: str, message: str, details: Any = None) -> Dict[str, Any]:
    """Build error object.

    Args:
        code: Error code (e.g., "INVALID_JSON", "UNKNOWN_OPERATION")
        message: Human-readable error message
        details: Additional error context

    Returns:
        Error object dict
    """
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return error


def main():
    """Main entrypoint for pipe-first shell interface."""
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

    # Handle empty input
    if not input_text.strip():
        response = make_response(
            "error",
            error=make_error("EMPTY_INPUT", "No input provided"),
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

    # Validate request is a dict
    if not isinstance(request, dict):
        response = make_response(
            "error",
            error=make_error("INVALID_REQUEST", "Request must be a JSON object"),
        )
        print(json.dumps(response))
        sys.exit(1)

    # Route to handler based on operation
    operation = request.get("operation", "pkg_list")
    handler = OPERATIONS.get(operation)

    if not handler:
        response = make_response(
            "error",
            error=make_error(
                "UNKNOWN_OPERATION",
                f"Unknown operation: {operation}",
                details={"valid_operations": list(OPERATIONS.keys())},
            ),
        )
        print(json.dumps(response))
        sys.exit(1)

    # Execute handler
    try:
        response = handler(request)
    except Exception as e:
        response = make_response(
            "error",
            error=make_error(
                "HANDLER_ERROR",
                f"Operation failed: {e}",
                details={"operation": operation},
            ),
        )

    # Add duration to evidence if successful
    if response.get("status") == "ok":
        duration_ms = int((time.time() - start_time) * 1000)
        if "evidence" not in response:
            response["evidence"] = {}
        response["evidence"]["duration_ms"] = duration_ms

    # Write to stdout
    print(json.dumps(response, ensure_ascii=False))

    # Exit with appropriate code
    sys.exit(0 if response.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
