"""LLM Evidence Builders.

Builds evidence records for LLM operations.
Never includes raw secrets, prompts, or responses - only hashes and fingerprints.
"""

from datetime import datetime, timezone
from hashlib import sha256
from typing import Optional, Dict, Any

from modules.stdlib_llm.provider import ProviderResponse


def hash_content(content: str) -> str:
    """Hash content for evidence logging.

    Args:
        content: Content to hash

    Returns:
        SHA256 hash string
    """
    return f"sha256:{sha256(content.encode()).hexdigest()}"


def build_llm_evidence(
    provider_id: str,
    model: str,
    request_id: str,
    usage: Dict[str, int],
    prompt_pack_id: str,
    prompt_hash: str,
    response_hash: str,
    cached: bool = False,
    api_key_fingerprint: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Build evidence record for an LLM call.

    Args:
        provider_id: LLM provider identifier
        model: Model used for completion
        request_id: Provider request ID
        usage: Token usage {input_tokens, output_tokens}
        prompt_pack_id: Governed prompt reference
        prompt_hash: Hash of the actual prompt
        response_hash: Hash of the response
        cached: Whether response was cached
        api_key_fingerprint: Fingerprint of API key (optional)
        duration_ms: Call duration in milliseconds

    Returns:
        Evidence dictionary for logging
    """
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_call": {
            "provider_id": provider_id,
            "model": model,
            "request_id": request_id,
            "usage": usage,
            "prompt_pack_id": prompt_pack_id,
            "prompt_hash": prompt_hash,
            "response_hash": response_hash,
            "cached": cached,
        },
    }

    if api_key_fingerprint:
        evidence["llm_call"]["api_key_fingerprint"] = api_key_fingerprint

    if duration_ms is not None:
        evidence["duration_ms"] = duration_ms

    return evidence


def build_llm_evidence_from_response(
    response: ProviderResponse,
    prompt: str,
    prompt_pack_id: str,
    api_key_fingerprint: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Build evidence from a ProviderResponse.

    Args:
        response: Response from LLM provider
        prompt: The prompt that was sent
        prompt_pack_id: Governed prompt reference
        api_key_fingerprint: Fingerprint of API key
        duration_ms: Call duration

    Returns:
        Evidence dictionary
    """
    return build_llm_evidence(
        provider_id=response.metadata.get("provider_id", "unknown"),
        model=response.model,
        request_id=response.request_id,
        usage=response.usage,
        prompt_pack_id=prompt_pack_id,
        prompt_hash=hash_content(prompt),
        response_hash=hash_content(response.content),
        cached=response.cached,
        api_key_fingerprint=api_key_fingerprint,
        duration_ms=duration_ms,
    )
