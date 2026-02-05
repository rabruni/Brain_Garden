#!/usr/bin/env python3
"""CLI entrypoint for the LLM Standard Library.

Implements the pipe-first contract: reads JSON from stdin, writes JSON to stdout.

Usage:
    echo '{"operation": "complete", "prompt": "Hello", "prompt_pack_id": "PRM-TEST-001"}' | python3 -m modules.stdlib_llm
    echo '{"operation": "load_prompt", "prompt_pack_id": "PRM-ADMIN-001"}' | python3 -m modules.stdlib_llm
    echo '{"operation": "list_providers"}' | python3 -m modules.stdlib_llm

Operations:
    - complete: Execute LLM completion (requires prompt_pack_id)
    - load_prompt: Load a governed prompt by ID
    - list_providers: List available providers
"""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

from modules.stdlib_llm.client import complete, load_prompt, get_provider, LLMError
from modules.stdlib_llm.providers import list_providers
from modules.stdlib_llm.evidence import hash_content


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


def handle_complete(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle complete operation."""
    prompt = request.get("prompt")
    prompt_pack_id = request.get("prompt_pack_id")

    if not prompt:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "prompt is required"),
        )

    if not prompt_pack_id:
        return make_response(
            "error",
            error=make_error(
                "PROMPT_PACK_ID_REQUIRED",
                "prompt_pack_id is REQUIRED for all LLM completions",
                details={"reason": "Ungoverned prompts are not allowed"},
            ),
        )

    try:
        response = complete(
            prompt=prompt,
            prompt_pack_id=prompt_pack_id,
            schema=request.get("schema"),
            max_tokens=request.get("max_tokens", 1024),
            temperature=request.get("temperature", 0.0),
            provider_id=request.get("provider_id"),
        )

        return make_response(
            "ok",
            result={
                "content": response.content,
                "model": response.model,
                "usage": response.usage,
                "request_id": response.request_id,
                "cached": response.cached,
                "prompt_pack_id": response.prompt_pack_id,
                "provider_id": response.provider_id,
            },
            evidence=response.evidence,
        )

    except LLMError as e:
        return make_response(
            "error",
            error=make_error(e.code, e.message, e.details),
        )


def handle_load_prompt(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle load_prompt operation."""
    prompt_pack_id = request.get("prompt_pack_id")

    if not prompt_pack_id:
        return make_response(
            "error",
            error=make_error("MISSING_FIELD", "prompt_pack_id is required"),
        )

    try:
        content = load_prompt(prompt_pack_id)

        evidence = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_pack_id": prompt_pack_id,
            "prompt_hash": hash_content(content),
        }

        return make_response(
            "ok",
            result={
                "prompt_pack_id": prompt_pack_id,
                "content": content,
                "hash": hash_content(content),
            },
            evidence=evidence,
        )

    except LLMError as e:
        return make_response(
            "error",
            error=make_error(e.code, e.message, e.details),
        )


def handle_list_providers(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle list_providers operation."""
    providers = list_providers()

    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return make_response(
        "ok",
        result={"providers": providers},
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
    operation = request.get("operation", "complete")

    if operation == "complete":
        response = handle_complete(request)
    elif operation == "load_prompt":
        response = handle_load_prompt(request)
    elif operation == "list_providers":
        response = handle_list_providers(request)
    else:
        response = make_response(
            "error",
            error=make_error(
                "UNKNOWN_OPERATION",
                f"Unknown operation: {operation}",
                details={"valid_operations": ["complete", "load_prompt", "list_providers"]},
            ),
        )

    # Add duration to evidence if successful
    if response.get("status") == "ok" and response.get("evidence"):
        duration_ms = int((time.time() - start_time) * 1000)
        if "duration_ms" not in response["evidence"]:
            response["evidence"]["duration_ms"] = duration_ms

    # Write to stdout
    print(json.dumps(response, ensure_ascii=False))

    # Exit with appropriate code
    sys.exit(0 if response.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
