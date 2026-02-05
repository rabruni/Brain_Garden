"""LLM Provider Registry.

Manages available LLM providers and their instantiation.

Example:
    from modules.stdlib_llm.providers import get_provider, list_providers

    provider = get_provider("anthropic")
    response = provider.complete("Hello")

    print(list_providers())  # ["anthropic", "mock"]
"""

from typing import Dict, Type, List

from modules.stdlib_llm.provider import LLMProvider


# Provider registry - maps provider_id to provider class
_PROVIDERS: Dict[str, Type[LLMProvider]] = {}


def register_provider(provider_id: str, provider_class: Type[LLMProvider]) -> None:
    """Register a provider class.

    Args:
        provider_id: Unique provider identifier
        provider_class: LLMProvider subclass
    """
    _PROVIDERS[provider_id] = provider_class


def get_provider(provider_id: str) -> LLMProvider:
    """Get a provider instance by ID.

    Args:
        provider_id: Provider identifier

    Returns:
        Instantiated LLMProvider

    Raises:
        ValueError: If provider_id is unknown
    """
    if provider_id not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider_id}. "
            f"Available: {list(_PROVIDERS.keys())}"
        )

    return _PROVIDERS[provider_id]()


def list_providers() -> List[str]:
    """List available provider IDs.

    Returns:
        List of registered provider IDs
    """
    return list(_PROVIDERS.keys())


# Auto-register built-in providers
def _register_builtins():
    """Register built-in providers."""
    from modules.stdlib_llm.providers.mock import MockProvider
    register_provider("mock", MockProvider)

    # Only register anthropic if SDK is available
    try:
        from modules.stdlib_llm.providers.anthropic import AnthropicProvider
        register_provider("anthropic", AnthropicProvider)
    except ImportError:
        pass  # anthropic SDK not installed


_register_builtins()
