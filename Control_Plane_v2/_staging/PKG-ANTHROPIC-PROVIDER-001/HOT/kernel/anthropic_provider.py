"""Anthropic Messages API provider — official SDK (anthropic>=0.40.0).

Implements LLMProvider Protocol from provider.py. No retries — the router's
CircuitBreaker handles that. Layer 3 application package — stdlib-only
constraint applies to kernel (Layers 0-2) only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

import anthropic

from provider import ProviderError, ProviderResponse

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

STOP_REASON_MAP = {
    "end_turn": "stop",
    "max_tokens": "length",
    "tool_use": "tool_use",
}


@dataclass(frozen=True)
class AnthropicResponse(ProviderResponse):
    """ProviderResponse with raw content_blocks for tool use support."""

    content_blocks: tuple = ()


class AnthropicProvider:
    """Anthropic Messages API provider using the official SDK."""

    def __init__(self, provider_id: str = "anthropic"):
        self.provider_id = provider_id
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ProviderError(
                message="ANTHROPIC_API_KEY environment variable not set",
                code="AUTH_ERROR",
                retryable=False,
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def send(
        self,
        model_id: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout_ms: int = 30000,
        structured_output: Optional[dict[str, Any]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AnthropicResponse:
        """Send a prompt to the Anthropic Messages API."""
        kwargs: dict[str, Any] = {
            "model": model_id or DEFAULT_MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": timeout_ms / 1000.0,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = {"type": "auto"}
        elif structured_output is not None:
            kwargs["tools"] = [{
                "name": "output_json",
                "description": "Return structured output matching the schema.",
                "input_schema": structured_output,
            }]
            kwargs["tool_choice"] = {"type": "tool", "name": "output_json"}

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.APITimeoutError as e:
            raise ProviderError(
                message=str(e), code="TIMEOUT", retryable=True
            ) from e
        except anthropic.APIConnectionError as e:
            raise ProviderError(
                message=str(e), code="TIMEOUT", retryable=True
            ) from e
        except anthropic.AuthenticationError as e:
            raise ProviderError(
                message=str(e), code="AUTH_ERROR", retryable=False
            ) from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderError(
                message=str(e), code="AUTH_ERROR", retryable=False
            ) from e
        except anthropic.BadRequestError as e:
            raise ProviderError(
                message=str(e), code="INVALID_REQUEST", retryable=False
            ) from e
        except anthropic.RateLimitError as e:
            raise ProviderError(
                message=str(e), code="RATE_LIMITED", retryable=True
            ) from e
        except anthropic.InternalServerError as e:
            raise ProviderError(
                message=str(e), code="SERVER_ERROR", retryable=True
            ) from e
        except anthropic.APIStatusError as e:
            raise ProviderError(
                message=str(e), code="SERVER_ERROR", retryable=True
            ) from e

        blocks = response.content
        text_parts = [b.text for b in blocks if b.type == "text"]
        tool_use_parts = [b for b in blocks if b.type == "tool_use"]
        content_dicts = tuple(b.model_dump() for b in blocks)
        finish = STOP_REASON_MAP.get(response.stop_reason or "", "stop")

        content = "".join(text_parts)
        if not content and tool_use_parts:
            content = json.dumps(tool_use_parts[0].input)

        return AnthropicResponse(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            request_id=response.id,
            provider_id=self.provider_id,
            finish_reason=finish,
            content_blocks=content_dicts,
        )
