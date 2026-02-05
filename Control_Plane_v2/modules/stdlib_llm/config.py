"""LLM Configuration.

Loads provider configuration from environment or external secrets.
Never exposes raw secrets - only fingerprints for logging.

Environment Variables:
    ANTHROPIC_API_KEY: API key for Anthropic Claude
    LLM_DEFAULT_PROVIDER: Default provider ID (default: "anthropic")
    LLM_DEFAULT_MODEL: Default model (provider-specific)
"""

import os
from dataclasses import dataclass
from typing import Optional

from modules.stdlib_auth.fingerprint import fingerprint_secret


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""

    provider_id: str
    api_key: Optional[str] = None
    api_key_fingerprint: str = ""
    model: Optional[str] = None
    base_url: Optional[str] = None

    def __post_init__(self):
        """Compute fingerprint on init."""
        if self.api_key:
            self.api_key_fingerprint = fingerprint_secret(self.api_key)


def get_anthropic_config() -> ProviderConfig:
    """Get Anthropic provider configuration.

    Reads ANTHROPIC_API_KEY from environment.

    Returns:
        ProviderConfig for Anthropic

    Raises:
        ValueError: If API key not configured
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    return ProviderConfig(
        provider_id="anthropic",
        api_key=api_key,
        model=model,
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
    )


def get_mock_config() -> ProviderConfig:
    """Get mock provider configuration for testing.

    Returns:
        ProviderConfig for mock provider
    """
    return ProviderConfig(
        provider_id="mock",
        api_key=None,
        model="mock-model",
    )


def get_default_provider_id() -> str:
    """Get the default provider ID.

    Returns:
        Provider ID from LLM_DEFAULT_PROVIDER or "anthropic"
    """
    return os.getenv("LLM_DEFAULT_PROVIDER", "anthropic")
