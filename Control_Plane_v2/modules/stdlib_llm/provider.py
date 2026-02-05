"""LLM Provider Interface.

Abstract base class for LLM providers. All providers must implement this interface.

Example:
    class MyProvider(LLMProvider):
        @property
        def provider_id(self) -> str:
            return "my-provider"

        def complete(self, prompt: str, **kwargs) -> ProviderResponse:
            # Implementation
            pass
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class ProviderResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    usage: Dict[str, int]  # {input_tokens, output_tokens}
    request_id: str
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier for evidence logging.

        Returns:
            Provider ID string (e.g., "anthropic", "mock")
        """
        pass

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model: Optional[str] = None,
        schema: Optional[dict] = None,
    ) -> ProviderResponse:
        """Execute a completion request.

        This method is stateless - no conversation memory is maintained.

        Args:
            prompt: The prompt text to complete
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0 = deterministic)
            model: Optional model override (provider default if None)
            schema: Optional JSON schema for structured output

        Returns:
            ProviderResponse with content and metadata

        Raises:
            LLMError: If completion fails
        """
        pass

    def validate_config(self) -> bool:
        """Validate provider configuration.

        Returns:
            True if provider is properly configured
        """
        return True
