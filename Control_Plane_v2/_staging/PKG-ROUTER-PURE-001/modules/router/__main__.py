#!/usr/bin/env python3
"""CLI entrypoint for the Router Module.

Implements the pipe-first contract: reads JSON from stdin, writes JSON to stdout.

Usage:
    echo '{"operation": "route", "query": "What packages are installed?"}' | python3 -m modules.router
    echo '{"operation": "list_handlers"}' | python3 -m modules.router

Operations:
    - route: Route query to handler (uses LLM-based classification)
    - list_handlers: List available handlers
"""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

from modules.router.decision import route_query, get_route_evidence


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


def handle_route(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle route operation."""
    query = request.get("query")

    if not query:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "query is required"),
        )

    # Route query
    route_result = route_query(query)

    # Build evidence
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **get_route_evidence(route_result),
    }

    return make_response(
        "ok",
        result=route_result.to_dict(),
        evidence=evidence,
    )


def handle_list_handlers(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle list_handlers operation."""
    from modules.router.decision import INTENT_HANDLER_MAP

    handlers = dict(INTENT_HANDLER_MAP)

    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return make_response(
        "ok",
        result={"handlers": handlers},
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
    operation = request.get("operation", "route")

    if operation == "route":
        response = handle_route(request)
    elif operation == "list_handlers":
        response = handle_list_handlers(request)
    else:
        response = make_response(
            "error",
            error=make_error(
                "UNKNOWN_OPERATION",
                f"Unknown operation: {operation}",
                details={"valid_operations": ["route", "list_handlers"]},
            ),
        )

    # Add duration to evidence if successful
    if response.get("evidence"):
        duration_ms = int((time.time() - start_time) * 1000)
        response["evidence"]["duration_ms"] = duration_ms

    # Write to stdout
    print(json.dumps(response, ensure_ascii=False))

    # Exit with appropriate code
    sys.exit(0 if response.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
