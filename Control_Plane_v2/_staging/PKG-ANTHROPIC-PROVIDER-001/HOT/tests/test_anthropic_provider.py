"""Tests for Anthropic API provider — Anthropic SDK implementation.

DTT: tests written FIRST, implementation follows.
All tests mock anthropic.Anthropic — no real API calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

# SDK types for building mock responses
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

# Add kernel paths
_staging = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-ANTHROPIC-PROVIDER-001" / "HOT" / "kernel"))

from anthropic_provider import AnthropicProvider, AnthropicResponse  # noqa: E402
from provider import LLMProvider, ProviderError, ProviderResponse  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────


def _mock_sdk_response(
    content="Hello!",
    model="claude-sonnet-4-5-20250929",
    stop_reason="end_turn",
    input_tokens=10,
    output_tokens=5,
    request_id="msg-abc123",
    content_blocks=None,
):
    """Build a real SDK Message object for mock returns."""
    if content_blocks is None:
        content_blocks = [TextBlock(type="text", text=content)]
    return Message(
        id=request_id,
        type="message",
        role="assistant",
        content=content_blocks,
        model=model,
        stop_reason=stop_reason,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _make_provider(provider_id="anthropic", api_key="sk-test-key-123"):
    """Create an AnthropicProvider with a test API key."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": api_key}):
        return AnthropicProvider(provider_id=provider_id)


def _sdk_error_request():
    """Build a httpx.Request for SDK error construction."""
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


# ── Init tests ───────────────────────────────────────────────────────


class TestAnthropicProviderInit:
    """Initialization and protocol conformance."""

    def test_reads_api_key_from_env(self):
        """#1: Reads ANTHROPIC_API_KEY from environment."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-123"}):
            provider = AnthropicProvider()
        assert provider.provider_id == "anthropic"

    def test_missing_key_raises_auth_error(self):
        """#2: Missing ANTHROPIC_API_KEY raises ProviderError(AUTH_ERROR)."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ProviderError) as exc_info:
                AnthropicProvider()
            assert exc_info.value.code == "AUTH_ERROR"

    def test_default_provider_id(self):
        """#3: Default provider_id is 'anthropic'."""
        provider = _make_provider()
        assert provider.provider_id == "anthropic"

    def test_custom_provider_id(self):
        """#4: Custom provider_id is respected."""
        provider = _make_provider(provider_id="my-anthropic")
        assert provider.provider_id == "my-anthropic"

    def test_implements_llm_provider_protocol(self):
        """#5: AnthropicProvider is an instance of LLMProvider protocol."""
        provider = _make_provider()
        assert isinstance(provider, LLMProvider)


# ── SDK client tests ─────────────────────────────────────────────────


class TestSDKClient:
    """SDK client creation."""

    def test_client_created_with_key(self):
        """#6: SDK client created with API key from env."""
        provider = _make_provider(api_key="sk-my-key")
        assert provider._client is not None
        assert provider._client.api_key == "sk-my-key"

    def test_no_client_when_key_missing(self):
        """#7: No client created when API key missing (raises before)."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ProviderError):
                AnthropicProvider()


# ── Request building tests ───────────────────────────────────────────


class TestRequestBuilding:
    """Verify the SDK request parameters."""

    @patch("anthropic.Anthropic")
    def test_model_id_in_request(self, MockClient):
        """#8: model_id passed to send() appears in messages.create() call."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response()
        provider = _make_provider()
        provider._client = mock_client
        provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-5-20250929"

    @patch("anthropic.Anthropic")
    def test_max_tokens_in_request(self, MockClient):
        """#9: max_tokens in messages.create() call."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response()
        provider = _make_provider()
        provider._client = mock_client
        provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi", max_tokens=1024)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 1024

    @patch("anthropic.Anthropic")
    def test_temperature_in_request(self, MockClient):
        """#10: temperature in messages.create() call."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response()
        provider = _make_provider()
        provider._client = mock_client
        provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi", temperature=0.7)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7

    @patch("anthropic.Anthropic")
    def test_timeout_conversion_ms_to_seconds(self, MockClient):
        """#11: timeout_ms converted to seconds for SDK timeout param."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response()
        provider = _make_provider()
        provider._client = mock_client
        provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi", timeout_ms=15000)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["timeout"] == 15.0

    @patch("anthropic.Anthropic")
    def test_default_model_used_when_empty(self, MockClient):
        """#12: Empty model_id uses default claude-sonnet-4-5-20250929."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response()
        provider = _make_provider()
        provider._client = mock_client
        provider.send(model_id="", prompt="Hi")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-5-20250929"

    @patch("anthropic.Anthropic")
    def test_prompt_as_user_message(self, MockClient):
        """#13: prompt is wrapped as a user message."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response()
        provider = _make_provider()
        provider._client = mock_client
        provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hello world")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["messages"] == [{"role": "user", "content": "Hello world"}]


# ── Response mapping tests ───────────────────────────────────────────


class TestResponseMapping:
    """Verify SDK Message response is mapped to AnthropicResponse."""

    @patch("anthropic.Anthropic")
    def test_basic_text_response(self, MockClient):
        """#14: Basic text response mapped correctly."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(content="Hello world")
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")

        assert resp.content == "Hello world"
        assert resp.model == "claude-sonnet-4-5-20250929"

    @patch("anthropic.Anthropic")
    def test_stop_reason_end_turn(self, MockClient):
        """#15: end_turn maps to 'stop'."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(stop_reason="end_turn")
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert resp.finish_reason == "stop"

    @patch("anthropic.Anthropic")
    def test_stop_reason_max_tokens(self, MockClient):
        """#16: max_tokens maps to 'length'."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(stop_reason="max_tokens")
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert resp.finish_reason == "length"

    @patch("anthropic.Anthropic")
    def test_stop_reason_tool_use(self, MockClient):
        """#17: tool_use maps to 'tool_use'."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(stop_reason="tool_use")
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert resp.finish_reason == "tool_use"

    @patch("anthropic.Anthropic")
    def test_request_id_from_response(self, MockClient):
        """#18: request_id from SDK Message.id field."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(request_id="msg-xyz789")
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert resp.request_id == "msg-xyz789"

    @patch("anthropic.Anthropic")
    def test_token_counts(self, MockClient):
        """#19: input_tokens and output_tokens mapped from Usage."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(
            input_tokens=150, output_tokens=75
        )
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert resp.input_tokens == 150
        assert resp.output_tokens == 75

    @patch("anthropic.Anthropic")
    def test_response_is_provider_response_subclass(self, MockClient):
        """#20: AnthropicResponse is a subclass of ProviderResponse."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response()
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert isinstance(resp, ProviderResponse)
        assert isinstance(resp, AnthropicResponse)


# ── Tool use tests ───────────────────────────────────────────────────


class TestToolUse:
    """Tool use / content_blocks support."""

    @patch("anthropic.Anthropic")
    def test_content_blocks_present(self, MockClient):
        """#21: content_blocks available on AnthropicResponse."""
        blocks = [
            TextBlock(type="text", text="Let me help."),
            ToolUseBlock(type="tool_use", id="toolu_1", name="search", input={"q": "test"}),
        ]
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(content_blocks=blocks)
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert len(resp.content_blocks) == 2
        assert resp.content_blocks[0]["type"] == "text"
        assert resp.content_blocks[1]["type"] == "tool_use"

    @patch("anthropic.Anthropic")
    def test_content_is_text_only(self, MockClient):
        """#22: content field contains only concatenated text blocks."""
        blocks = [
            TextBlock(type="text", text="Part 1. "),
            ToolUseBlock(type="tool_use", id="toolu_1", name="search", input={}),
            TextBlock(type="text", text="Part 2."),
        ]
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(content_blocks=blocks)
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert resp.content == "Part 1. Part 2."

    @patch("anthropic.Anthropic")
    def test_mixed_blocks_preserved(self, MockClient):
        """#23: Mixed text + tool_use blocks all preserved in content_blocks."""
        blocks = [
            TextBlock(type="text", text="Here's the result:"),
            ToolUseBlock(type="tool_use", id="toolu_1", name="calc", input={"expr": "2+2"}),
        ]
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(content_blocks=blocks)
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert resp.content_blocks[0]["type"] == "text"
        assert resp.content_blocks[1]["name"] == "calc"

    @patch("anthropic.Anthropic")
    def test_content_blocks_is_tuple(self, MockClient):
        """#24: content_blocks is a tuple (immutable)."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response()
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert isinstance(resp.content_blocks, tuple)


# ── Structured output tests ──────────────────────────────────────────


class TestStructuredOutput:
    """Structured output / tool_choice support."""

    @patch("anthropic.Anthropic")
    def test_structured_output_adds_tools(self, MockClient):
        """#25: structured_output adds tools + tool_choice to SDK call."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(
            stop_reason="tool_use",
            content_blocks=[
                ToolUseBlock(
                    type="tool_use", id="toolu_1", name="output_json", input={"answer": 42}
                ),
            ],
        )
        provider = _make_provider()
        provider._client = mock_client
        schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
        provider.send(
            model_id="claude-sonnet-4-5-20250929",
            prompt="What is 6*7?",
            structured_output=schema,
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["tools"][0]["name"] == "output_json"
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "output_json"}

    @patch("anthropic.Anthropic")
    def test_structured_output_extracts_tool_use_content(self, MockClient):
        """#32: tool_use block input extracted as content when text is empty."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(
            stop_reason="tool_use",
            content_blocks=[
                ToolUseBlock(
                    type="tool_use", id="toolu_1", name="output_json",
                    input={"speech_act": "greeting", "ambiguity": "low"},
                ),
            ],
        )
        provider = _make_provider()
        provider._client = mock_client
        schema = {
            "type": "object",
            "required": ["speech_act", "ambiguity"],
            "properties": {"speech_act": {"type": "string"}, "ambiguity": {"type": "string"}},
        }
        resp = provider.send(
            model_id="claude-sonnet-4-5-20250929",
            prompt="Classify this",
            structured_output=schema,
        )
        import json
        parsed = json.loads(resp.content)
        assert parsed["speech_act"] == "greeting"
        assert parsed["ambiguity"] == "low"

    @patch("anthropic.Anthropic")
    def test_structured_output_text_response_still_works(self, MockClient):
        """#33: text response without tool_use still works (existing behavior)."""
        mock_client = MockClient.return_value
        mock_client.messages.create.return_value = _mock_sdk_response(
            content="Hello world",
            stop_reason="end_turn",
        )
        provider = _make_provider()
        provider._client = mock_client
        resp = provider.send(
            model_id="claude-sonnet-4-5-20250929",
            prompt="Say hello",
        )
        assert resp.content == "Hello world"


# ── Error tests ──────────────────────────────────────────────────────


class TestErrors:
    """Error handling and mapping from SDK exceptions to ProviderError."""

    @patch("anthropic.Anthropic")
    def test_timeout_error(self, MockClient):
        """#26: APITimeoutError -> ProviderError(TIMEOUT, retryable=True)."""
        import anthropic

        mock_client = MockClient.return_value
        mock_client.messages.create.side_effect = anthropic.APITimeoutError(
            request=_sdk_error_request()
        )
        provider = _make_provider()
        provider._client = mock_client
        with pytest.raises(ProviderError) as exc_info:
            provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.retryable is True

    @patch("anthropic.Anthropic")
    def test_connection_error(self, MockClient):
        """#27: APIConnectionError -> ProviderError(TIMEOUT, retryable=True)."""
        import anthropic

        mock_client = MockClient.return_value
        mock_client.messages.create.side_effect = anthropic.APIConnectionError(
            request=_sdk_error_request(), message="connection failed"
        )
        provider = _make_provider()
        provider._client = mock_client
        with pytest.raises(ProviderError) as exc_info:
            provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.retryable is True

    @patch("anthropic.Anthropic")
    def test_429_rate_limited(self, MockClient):
        """#28: RateLimitError -> ProviderError(RATE_LIMITED, retryable=True)."""
        import anthropic

        req = _sdk_error_request()
        mock_client = MockClient.return_value
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            "rate limited", response=httpx.Response(429, request=req), body=None
        )
        provider = _make_provider()
        provider._client = mock_client
        with pytest.raises(ProviderError) as exc_info:
            provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert exc_info.value.code == "RATE_LIMITED"
        assert exc_info.value.retryable is True

    @patch("anthropic.Anthropic")
    def test_401_auth_error(self, MockClient):
        """#29: AuthenticationError -> ProviderError(AUTH_ERROR, retryable=False)."""
        import anthropic

        req = _sdk_error_request()
        mock_client = MockClient.return_value
        mock_client.messages.create.side_effect = anthropic.AuthenticationError(
            "invalid api key", response=httpx.Response(401, request=req), body=None
        )
        provider = _make_provider()
        provider._client = mock_client
        with pytest.raises(ProviderError) as exc_info:
            provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert exc_info.value.code == "AUTH_ERROR"
        assert exc_info.value.retryable is False

    @patch("anthropic.Anthropic")
    def test_400_invalid_request(self, MockClient):
        """#30: BadRequestError -> ProviderError(INVALID_REQUEST, retryable=False)."""
        import anthropic

        req = _sdk_error_request()
        mock_client = MockClient.return_value
        mock_client.messages.create.side_effect = anthropic.BadRequestError(
            "invalid model", response=httpx.Response(400, request=req), body=None
        )
        provider = _make_provider()
        provider._client = mock_client
        with pytest.raises(ProviderError) as exc_info:
            provider.send(model_id="bad-model", prompt="Hi")
        assert exc_info.value.code == "INVALID_REQUEST"
        assert exc_info.value.retryable is False

    @patch("anthropic.Anthropic")
    def test_500_server_error(self, MockClient):
        """#31: InternalServerError -> ProviderError(SERVER_ERROR, retryable=True)."""
        import anthropic

        req = _sdk_error_request()
        mock_client = MockClient.return_value
        mock_client.messages.create.side_effect = anthropic.InternalServerError(
            "internal error", response=httpx.Response(500, request=req), body=None
        )
        provider = _make_provider()
        provider._client = mock_client
        with pytest.raises(ProviderError) as exc_info:
            provider.send(model_id="claude-sonnet-4-5-20250929", prompt="Hi")
        assert exc_info.value.code == "SERVER_ERROR"
        assert exc_info.value.retryable is True
