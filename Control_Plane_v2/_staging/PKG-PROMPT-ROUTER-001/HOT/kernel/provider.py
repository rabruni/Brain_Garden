"""LLM Provider interface and mock implementation for prompt routing.

Defines the protocol that all LLM providers must implement, plus a
configurable MockProvider for testing without real LLM calls.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    request_id: str
    provider_id: str
    cached: bool = False
    finish_reason: str = "stop"


@dataclass
class ProviderError(Exception):
    """Error from an LLM provider."""

    message: str
    code: str  # TIMEOUT, RATE_LIMITED, SERVER_ERROR, AUTH_ERROR, INVALID_REQUEST
    retryable: bool = False
    details: Optional[dict[str, Any]] = None

    def __str__(self) -> str:
        return f"ProviderError({self.code}): {self.message}"


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol that all LLM providers must implement."""

    provider_id: str

    def send(
        self,
        model_id: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout_ms: int = 30000,
        structured_output: Optional[dict[str, Any]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> ProviderResponse:
        """Send a prompt to the LLM and return the response."""
        ...


class MockProvider:
    """Configurable mock LLM provider for testing."""

    def __init__(
        self,
        provider_id: str = "mock",
        default_response: str = "Mock response",
        default_model: str = "mock-model-1",
        default_input_tokens: int = 100,
        default_output_tokens: int = 50,
        fail_after: Optional[int] = None,
        fail_with: Optional[ProviderError] = None,
        responses: Optional[list[ProviderResponse]] = None,
        latency_ms: float = 0.0,
    ):
        self.provider_id = provider_id
        self._default_response = default_response
        self._default_model = default_model
        self._default_input_tokens = default_input_tokens
        self._default_output_tokens = default_output_tokens
        self._fail_after = fail_after
        self._fail_with = fail_with
        self._responses = responses or []
        self._latency_ms = latency_ms
        self.call_count: int = 0
        self.calls: list[dict[str, Any]] = []

    def send(
        self,
        model_id: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout_ms: int = 30000,
        structured_output: Optional[dict[str, Any]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> ProviderResponse:
        """Send a mock prompt — returns configured response or raises configured error."""
        self.calls.append(
            {
                "model_id": model_id,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "timeout_ms": timeout_ms,
                "structured_output": structured_output,
                "tools": tools,
            }
        )
        self.call_count += 1

        # Simulate latency
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000.0)

        # Check if we should fail
        if self._fail_after is not None and self.call_count > self._fail_after:
            raise self._fail_with or ProviderError(
                message="Mock failure",
                code="SERVER_ERROR",
                retryable=True,
            )

        # Return from response queue or default
        if self._responses and self.call_count <= len(self._responses):
            return self._responses[self.call_count - 1]

        return ProviderResponse(
            content=self._default_response,
            model=model_id or self._default_model,
            input_tokens=self._default_input_tokens,
            output_tokens=self._default_output_tokens,
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            provider_id=self.provider_id,
        )

    def reset(self) -> None:
        """Reset call tracking."""
        self.call_count = 0
        self.calls = []
