"""Mock LLM Provider for testing.

Provides deterministic responses for testing without external API calls.
Supports canned responses based on prompt patterns.
"""

import re
import uuid
from typing import Optional, Dict, List

from modules.stdlib_llm.provider import LLMProvider, ProviderResponse


# Canned responses for common test patterns.
# Order matters: more specific patterns must come before general ones.
# Router prompts include the template boilerplate (intent list), so patterns
# must match the user query portion specifically. Using "query: <keyword>"
# anchors to the rendered {{query}} line in PRM-ROUTER-001.
CANNED_RESPONSES: Dict[str, str] = {
    "hello": "Hello! I'm a mock LLM assistant.",
    # Router classification patterns (anchored to "Query: <user text>")
    "query: list packages": '{"intent": "list_packages", "confidence": 0.95, "reasoning": "User wants to list installed packages"}',
    "query: show inventory": '{"intent": "list_packages", "confidence": 0.95, "reasoning": "User wants inventory of packages"}',
    "packages are installed": '{"intent": "list_packages", "confidence": 0.95, "reasoning": "User wants to list installed packages"}',
    "query: check health": '{"intent": "health_check", "confidence": 0.95, "reasoning": "User wants health status"}',
    "query: system health": '{"intent": "health_check", "confidence": 0.95, "reasoning": "User wants health status"}',
    "query: system status": '{"intent": "health_check", "confidence": 0.95, "reasoning": "User wants health status"}',
    "query: show ledger": '{"intent": "show_ledger", "confidence": 0.95, "reasoning": "User wants to see the ledger"}',
    "query: show session": '{"intent": "show_session", "confidence": 0.95, "reasoning": "User wants session data"}',
    "query: explain": '{"intent": "explain_artifact", "confidence": 0.95, "reasoning": "User wants an explanation of an artifact"}',
    "query: what is": '{"intent": "explain_artifact", "confidence": 0.95, "reasoning": "User wants an explanation"}',
    "query: describe": '{"intent": "explain_artifact", "confidence": 0.95, "reasoning": "User wants a description"}',
    "query: validate": '{"intent": "validate", "confidence": 0.95, "reasoning": "User wants to validate a document"}',
    "query: summarize": '{"intent": "summarize", "confidence": 0.95, "reasoning": "User wants a summary"}',
    # Generic router classification fallback
    "classify": '{"intent": "general", "confidence": 0.95, "reasoning": "Mock classification"}',
}

# Default response when no pattern matches
DEFAULT_RESPONSE = "Mock response for: {prompt_preview}"


class MockProvider(LLMProvider):
    """Mock LLM provider for testing.

    Provides deterministic responses based on prompt patterns.
    No external API calls are made.
    """

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        """Initialize mock provider.

        Args:
            responses: Optional custom response mapping
        """
        self._responses = responses or CANNED_RESPONSES
        self._call_count = 0
        self._call_history: List[dict] = []

    @property
    def provider_id(self) -> str:
        """Return provider ID."""
        return "mock"

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model: Optional[str] = None,
        schema: Optional[dict] = None,
    ) -> ProviderResponse:
        """Execute mock completion.

        Args:
            prompt: The prompt text
            max_tokens: Maximum tokens (ignored)
            temperature: Temperature (ignored)
            model: Model name (optional)
            schema: JSON schema (ignored)

        Returns:
            ProviderResponse with mock content
        """
        self._call_count += 1

        # Find matching canned response
        content = self._find_response(prompt)

        # Generate mock usage
        input_tokens = len(prompt.split())
        output_tokens = len(content.split())

        # Generate request ID
        request_id = f"mock-{uuid.uuid4().hex[:12]}"

        # Record call
        self._call_history.append({
            "prompt": prompt,
            "content": content,
            "request_id": request_id,
        })

        return ProviderResponse(
            content=content,
            model=model or "mock-model",
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
            request_id=request_id,
            cached=False,
            metadata={"provider_id": self.provider_id},
        )

    def _find_response(self, prompt: str) -> str:
        """Find matching canned response for prompt.

        Args:
            prompt: The prompt text

        Returns:
            Matched response or default
        """
        prompt_lower = prompt.lower()

        for pattern, response in self._responses.items():
            if pattern in prompt_lower:
                return response

        # Default response with prompt preview
        preview = prompt[:50] + "..." if len(prompt) > 50 else prompt
        return DEFAULT_RESPONSE.format(prompt_preview=preview)

    def add_response(self, pattern: str, response: str) -> None:
        """Add a canned response pattern.

        Args:
            pattern: Pattern to match in prompt (case-insensitive)
            response: Response to return
        """
        self._responses[pattern] = response

    def get_call_count(self) -> int:
        """Get number of calls made.

        Returns:
            Call count
        """
        return self._call_count

    def get_call_history(self) -> List[dict]:
        """Get call history.

        Returns:
            List of call records
        """
        return self._call_history.copy()

    def reset(self) -> None:
        """Reset call count and history."""
        self._call_count = 0
        self._call_history = []
