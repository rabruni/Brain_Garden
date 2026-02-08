"""Anthropic Claude Provider.

Provides LLM completions via the Anthropic API.
Requires the 'anthropic' SDK to be installed.
"""

import os
from typing import Optional

from modules.stdlib_llm.provider import LLMProvider, ProviderResponse
from modules.stdlib_llm.config import get_anthropic_config


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider.

    Uses the Anthropic Python SDK for API calls.

    Environment Variables:
        ANTHROPIC_API_KEY: Required API key
        ANTHROPIC_MODEL: Model to use (default: claude-sonnet-4-20250514)
        ANTHROPIC_BASE_URL: Optional custom base URL
    """

    def __init__(self):
        """Initialize Anthropic provider."""
        self._config = get_anthropic_config()
        self._client = None

    @property
    def provider_id(self) -> str:
        """Return provider ID."""
        return "anthropic"

    def _get_client(self):
        """Get or create Anthropic client.

        Returns:
            Anthropic client instance

        Raises:
            ImportError: If anthropic SDK not installed
            ValueError: If API key not configured
        """
        if self._client is not None:
            return self._client

        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic SDK not installed. "
                "Install with: pip install anthropic"
            )

        if not self._config.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not configured. "
                "Set environment variable or use external secrets."
            )

        kwargs = {
            "api_key": self._config.api_key,
            "max_retries": 5,
            "timeout": anthropic.Timeout(
                connect=5.0, read=120.0, write=120.0, pool=120.0
            ),
        }
        if self._config.base_url:
            kwargs["base_url"] = self._config.base_url

        self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model: Optional[str] = None,
        schema: Optional[dict] = None,
    ) -> ProviderResponse:
        """Execute completion via Anthropic API.

        Args:
            prompt: The prompt text
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            model: Model override (uses config default if None)
            schema: Optional JSON schema (triggers tool use)

        Returns:
            ProviderResponse with content and metadata

        Raises:
            anthropic.APIError: If API call fails
        """
        client = self._get_client()
        use_model = model or self._config.model or "claude-sonnet-4-20250514"

        # Build message request
        kwargs = {
            "model": use_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        # Add JSON mode if schema provided
        if schema:
            kwargs["response_format"] = {"type": "json_object"}

        # Make API call
        response = client.messages.create(**kwargs)

        # Extract content
        content = ""
        if response.content:
            content = response.content[0].text

        return ProviderResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            request_id=response.id,
            cached=getattr(response, "cached", False),
            metadata={
                "provider_id": self.provider_id,
                "stop_reason": response.stop_reason,
            },
        )

    def validate_config(self) -> bool:
        """Validate Anthropic configuration.

        Returns:
            True if API key is configured
        """
        return bool(self._config.api_key)

    def get_api_key_fingerprint(self) -> str:
        """Get fingerprint of API key for logging.

        Returns:
            API key fingerprint or empty string
        """
        return self._config.api_key_fingerprint
