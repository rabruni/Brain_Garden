"""LLM Client.

High-level interface for LLM completions.
Enforces governed prompts and builds evidence.
All LLM calls are logged to the L-LLM ledger with prompt tracking.

Example:
    from modules.stdlib_llm.client import complete, load_prompt

    prompt = load_prompt("PRM-ADMIN-EXPLAIN-001")
    response = complete(
        prompt=prompt.format(artifact="FMWK-000"),
        prompt_pack_id="PRM-ADMIN-EXPLAIN-001",
    )
    print(response.content)
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List

from modules.stdlib_llm.provider import LLMProvider, ProviderResponse
from modules.stdlib_llm.providers import get_provider as _get_provider, list_providers
from modules.stdlib_llm.config import get_default_provider_id
from modules.stdlib_llm.evidence import build_llm_evidence_from_response, hash_content

# Import ledger client for logging LLM calls
from lib.ledger_client import LedgerClient, LedgerEntry


def _get_llm_ledger_path() -> Path:
    """Get path to the L-LLM ledger.

    Returns:
        Path to ledger/llm.jsonl
    """
    # Determine control plane root
    current = Path(__file__).resolve()
    while current.name != "Control_Plane_v2" and current.parent != current:
        current = current.parent

    if current.name == "Control_Plane_v2":
        root = current
    else:
        root = Path.cwd()

    return root / "ledger" / "llm.jsonl"


def _log_llm_call(
    prompt_pack_id: str,
    evidence: Dict[str, Any],
    provider_id: str,
    prompt_text: str,
    response_text: str,
) -> None:
    """Log LLM call to dedicated ledger.

    Writes an LLM_CALL entry to the L-LLM ledger with prompt tracking.
    This ensures every LLM call has a complete audit trail with FULL
    TRANSPARENCY - actual content is stored, not just hashes.

    Args:
        prompt_pack_id: Governed prompt identifier used
        evidence: Evidence dict with hashes and usage
        provider_id: Provider that handled the call
        prompt_text: Actual prompt text sent to LLM
        response_text: Actual response text from LLM
    """
    ledger_path = _get_llm_ledger_path()
    client = LedgerClient(ledger_path=ledger_path)

    llm_call = evidence.get("llm_call", {})

    entry = LedgerEntry(
        event_type="LLM_CALL",
        submission_id=llm_call.get("request_id", "unknown"),
        decision="COMPLETED",
        reason=f"LLM completion via {provider_id}",
        prompts_used=[prompt_pack_id],
        metadata={
            # Actual content for transparency
            "prompt_text": prompt_text,
            "response_text": response_text,
            # Hashes for integrity verification
            "prompt_hash": llm_call.get("prompt_hash", ""),
            "response_hash": llm_call.get("response_hash", ""),
            # Call metadata
            "model": llm_call.get("model", ""),
            "usage": llm_call.get("usage", {}),
            "cached": llm_call.get("cached", False),
            "duration_ms": evidence.get("duration_ms"),
            "provider_id": provider_id,
            "prompt_pack_id": prompt_pack_id,
        },
    )
    client.write(entry)


class LLMError(Exception):
    """LLM operation error."""

    def __init__(self, message: str, code: str = "LLM_ERROR", details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


@dataclass
class LLMResponse:
    """Response from LLM completion with evidence."""

    content: str
    model: str
    usage: Dict[str, int]
    request_id: str
    cached: bool
    evidence: Dict[str, Any]
    prompt_pack_id: str
    provider_id: str

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "model": self.model,
            "usage": self.usage,
            "request_id": self.request_id,
            "cached": self.cached,
            "prompt_pack_id": self.prompt_pack_id,
            "provider_id": self.provider_id,
        }


def _get_prompt_path(prompt_pack_id: str) -> Path:
    """Get path to governed prompt file.

    Args:
        prompt_pack_id: Prompt pack identifier (e.g., PRM-ADMIN-001)

    Returns:
        Path to prompt file
    """
    # Determine control plane root
    current = Path(__file__).resolve()
    while current.name != "Control_Plane_v2" and current.parent != current:
        current = current.parent

    if current.name == "Control_Plane_v2":
        root = current
    else:
        root = Path.cwd()

    return root / "governed_prompts" / f"{prompt_pack_id}.md"


def load_prompt(prompt_pack_id: str) -> str:
    """Load a governed prompt by ID.

    Args:
        prompt_pack_id: Prompt pack identifier (e.g., PRM-ADMIN-001)

    Returns:
        Prompt template content

    Raises:
        LLMError: If prompt not found or not governed
    """
    if not prompt_pack_id:
        raise LLMError(
            "prompt_pack_id is required",
            code="PROMPT_ID_REQUIRED",
        )

    # Validate format
    if not prompt_pack_id.startswith("PRM-"):
        raise LLMError(
            f"Invalid prompt ID format: {prompt_pack_id}",
            code="INVALID_PROMPT_ID",
            details={"expected_format": "PRM-<DOMAIN>-<SEQ>"},
        )

    # Get prompt path
    prompt_path = _get_prompt_path(prompt_pack_id)

    if not prompt_path.exists():
        raise LLMError(
            f"Governed prompt not found: {prompt_pack_id}",
            code="PROMPT_NOT_FOUND",
            details={"path": str(prompt_path)},
        )

    return prompt_path.read_text()


def get_provider(provider_id: Optional[str] = None) -> LLMProvider:
    """Get an LLM provider by ID.

    Args:
        provider_id: Provider identifier (uses default if None)

    Returns:
        LLMProvider instance

    Raises:
        LLMError: If provider not found
    """
    pid = provider_id or get_default_provider_id()

    try:
        return _get_provider(pid)
    except ValueError as e:
        raise LLMError(
            str(e),
            code="PROVIDER_NOT_FOUND",
            details={
                "provider_id": pid,
                "available": list_providers(),
            },
        )


def complete(
    prompt: str,
    *,
    prompt_pack_id: str,
    schema: Optional[dict] = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    provider_id: Optional[str] = None,
) -> LLMResponse:
    """Execute a stateless LLM completion.

    This is the primary interface for LLM operations. All completions
    require a governed prompt reference (prompt_pack_id).

    Args:
        prompt: The rendered prompt text to complete
        prompt_pack_id: REQUIRED - governed prompt reference (e.g., PRM-ADMIN-001)
        schema: Optional JSON schema for structured output
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature (0.0 = deterministic)
        provider_id: Provider to use (uses default if None)

    Returns:
        LLMResponse with content and evidence

    Raises:
        LLMError: If completion fails or prompt not governed
    """
    # Validate prompt_pack_id is provided (HARD FAIL if missing)
    if not prompt_pack_id:
        raise LLMError(
            "prompt_pack_id is REQUIRED for all LLM completions",
            code="PROMPT_PACK_ID_REQUIRED",
            details={
                "reason": "Ungoverned prompts are not allowed",
                "fix": "Provide prompt_pack_id referencing a governed prompt",
            },
        )

    # Get provider
    pid = provider_id or get_default_provider_id()
    provider = get_provider(pid)

    # Track timing
    start_time = time.time()

    try:
        # Execute completion
        response = provider.complete(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            schema=schema,
        )

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Get API key fingerprint if available
        api_key_fingerprint = None
        if hasattr(provider, "get_api_key_fingerprint"):
            api_key_fingerprint = provider.get_api_key_fingerprint()

        # Build evidence (never includes raw prompt or response)
        evidence = build_llm_evidence_from_response(
            response=response,
            prompt=prompt,
            prompt_pack_id=prompt_pack_id,
            api_key_fingerprint=api_key_fingerprint,
            duration_ms=duration_ms,
        )

        # Log to L-LLM ledger for audit trail (full transparency)
        _log_llm_call(
            prompt_pack_id=prompt_pack_id,
            evidence=evidence,
            provider_id=pid,
            prompt_text=prompt,
            response_text=response.content,
        )

        return LLMResponse(
            content=response.content,
            model=response.model,
            usage=response.usage,
            request_id=response.request_id,
            cached=response.cached,
            evidence=evidence,
            prompt_pack_id=prompt_pack_id,
            provider_id=pid,
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)

        # Check if it's already an LLMError
        if isinstance(e, LLMError):
            raise

        # Wrap other exceptions
        raise LLMError(
            f"LLM completion failed: {e}",
            code="COMPLETION_FAILED",
            details={
                "provider_id": pid,
                "prompt_hash": hash_content(prompt),
                "duration_ms": duration_ms,
            },
        )
