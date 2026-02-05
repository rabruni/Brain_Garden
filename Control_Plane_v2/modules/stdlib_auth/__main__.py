#!/usr/bin/env python3
"""CLI entrypoint for the Authentication Standard Library.

Implements the pipe-first contract: reads JSON from stdin, writes JSON to stdout.

Usage:
    echo '{"operation": "validate_token", "token": "user:sig"}' | python3 -m modules.stdlib_auth
    echo '{"operation": "fingerprint", "secret": "my-key"}' | python3 -m modules.stdlib_auth

Operations:
    - validate_token: Validate token and return identity
    - fingerprint: Create safe fingerprint of a secret
    - require_role: Check if identity has role (needs prior validation)
"""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

from modules.stdlib_auth.validator import validate_token, require_role, AuthError, Identity
from modules.stdlib_auth.fingerprint import fingerprint_secret


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


def handle_validate_token(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle validate_token operation."""
    token = request.get("token")

    if not token:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "token is required"),
        )

    try:
        identity = validate_token(token)

        evidence = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "auth": {
                "user": identity.user,
                "token_fingerprint": identity.fingerprint,
            },
        }

        return make_response(
            "ok",
            result={
                "user": identity.user,
                "roles": identity.roles,
                "fingerprint": identity.fingerprint,
            },
            evidence=evidence,
        )

    except AuthError as e:
        return make_response(
            "error",
            error=make_error(e.code, e.message, e.details),
        )


def handle_fingerprint(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle fingerprint operation."""
    secret = request.get("secret")

    if secret is None:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "secret is required"),
        )

    fp = fingerprint_secret(secret)

    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return make_response(
        "ok",
        result={"fingerprint": fp},
        evidence=evidence,
    )


def handle_require_role(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle require_role operation."""
    identity_data = request.get("identity")
    role = request.get("role")

    if not identity_data:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "identity is required"),
        )

    if not role:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "role is required"),
        )

    identity = Identity(
        user=identity_data.get("user", ""),
        roles=identity_data.get("roles", []),
        fingerprint=identity_data.get("fingerprint", ""),
    )

    try:
        require_role(identity, role)

        evidence = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "auth": {
                "user": identity.user,
                "role_checked": role,
                "result": "granted",
            },
        }

        return make_response(
            "ok",
            result={"granted": True, "role": role},
            evidence=evidence,
        )

    except AuthError as e:
        return make_response(
            "error",
            error=make_error(e.code, e.message, e.details),
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
    operation = request.get("operation", "validate_token")

    if operation == "validate_token":
        response = handle_validate_token(request)
    elif operation == "fingerprint":
        response = handle_fingerprint(request)
    elif operation == "require_role":
        response = handle_require_role(request)
    else:
        response = make_response(
            "error",
            error=make_error(
                "UNKNOWN_OPERATION",
                f"Unknown operation: {operation}",
                details={"valid_operations": ["validate_token", "fingerprint", "require_role"]},
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
