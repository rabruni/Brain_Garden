"""Tests for stdlib_llm module."""

import pytest

from modules.stdlib_llm import (
    complete,
    load_prompt,
    get_provider,
    LLMResponse,
    LLMProvider,
    ProviderResponse,
)
from modules.stdlib_llm.client import LLMError
from modules.stdlib_llm.providers.mock import MockProvider
from modules.stdlib_llm.evidence import hash_content, build_llm_evidence


class TestHashContent:
    """Tests for hash_content function."""

    def test_hash_creates_sha256(self):
        """hash_content returns sha256 prefix."""
        h = hash_content("test content")
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_hash_deterministic(self):
        """Same input produces same hash."""
        h1 = hash_content("my content")
        h2 = hash_content("my content")
        assert h1 == h2

    def test_hash_different_content(self):
        """Different content produces different hashes."""
        h1 = hash_content("content-1")
        h2 = hash_content("content-2")
        assert h1 != h2


class TestBuildLLMEvidence:
    """Tests for build_llm_evidence function."""

    def test_evidence_structure(self):
        """Evidence has required fields."""
        evidence = build_llm_evidence(
            provider_id="mock",
            model="mock-model",
            request_id="req-123",
            usage={"input_tokens": 10, "output_tokens": 5},
            prompt_pack_id="PRM-TEST-001",
            prompt_hash="sha256:abc",
            response_hash="sha256:def",
        )

        assert "timestamp" in evidence
        assert "llm_call" in evidence
        assert evidence["llm_call"]["provider_id"] == "mock"
        assert evidence["llm_call"]["model"] == "mock-model"
        assert evidence["llm_call"]["prompt_pack_id"] == "PRM-TEST-001"

    def test_evidence_optional_fields(self):
        """Evidence includes optional fields when provided."""
        evidence = build_llm_evidence(
            provider_id="mock",
            model="mock-model",
            request_id="req-123",
            usage={"input_tokens": 10, "output_tokens": 5},
            prompt_pack_id="PRM-TEST-001",
            prompt_hash="sha256:abc",
            response_hash="sha256:def",
            api_key_fingerprint="fp:sha256:abc123",
            duration_ms=100,
        )

        assert evidence["llm_call"]["api_key_fingerprint"] == "fp:sha256:abc123"
        assert evidence["duration_ms"] == 100


class TestMockProvider:
    """Tests for MockProvider."""

    def test_provider_id(self):
        """Mock provider has correct ID."""
        provider = MockProvider()
        assert provider.provider_id == "mock"

    def test_complete_returns_response(self):
        """complete returns ProviderResponse."""
        provider = MockProvider()
        response = provider.complete("Hello")

        assert isinstance(response, ProviderResponse)
        assert response.content
        assert response.model == "mock-model"
        assert "input_tokens" in response.usage
        assert "output_tokens" in response.usage
        assert response.request_id.startswith("mock-")

    def test_complete_canned_response(self):
        """complete matches canned responses."""
        provider = MockProvider()
        response = provider.complete("Please explain this")

        assert "explanation" in response.content.lower()

    def test_add_response(self):
        """Custom responses can be added."""
        provider = MockProvider()
        provider.add_response("custom", "Custom response!")
        response = provider.complete("This is a custom test")

        assert response.content == "Custom response!"

    def test_call_count(self):
        """Call count is tracked."""
        provider = MockProvider()
        assert provider.get_call_count() == 0

        provider.complete("Test 1")
        assert provider.get_call_count() == 1

        provider.complete("Test 2")
        assert provider.get_call_count() == 2

    def test_call_history(self):
        """Call history is tracked."""
        provider = MockProvider()
        provider.complete("Test prompt")

        history = provider.get_call_history()
        assert len(history) == 1
        assert history[0]["prompt"] == "Test prompt"

    def test_reset(self):
        """Reset clears count and history."""
        provider = MockProvider()
        provider.complete("Test")
        provider.reset()

        assert provider.get_call_count() == 0
        assert provider.get_call_history() == []


class TestGetProvider:
    """Tests for get_provider function."""

    def test_get_mock_provider(self):
        """get_provider returns mock provider."""
        provider = get_provider("mock")
        assert provider.provider_id == "mock"

    def test_get_unknown_provider(self):
        """get_provider raises for unknown provider."""
        with pytest.raises(LLMError) as exc:
            get_provider("unknown-provider")
        assert exc.value.code == "PROVIDER_NOT_FOUND"


class TestComplete:
    """Tests for complete function."""

    def test_complete_requires_prompt_pack_id(self):
        """complete raises if prompt_pack_id missing."""
        with pytest.raises(LLMError) as exc:
            complete(prompt="Hello", prompt_pack_id="")
        assert exc.value.code == "PROMPT_PACK_ID_REQUIRED"

    def test_complete_with_mock(self):
        """complete works with mock provider."""
        # complete() doesn't validate prompt file existence - it just uses
        # prompt_pack_id for evidence. The load_prompt() function validates.
        response = complete(
            prompt="Hello",
            prompt_pack_id="PRM-TEST-001",
            provider_id="mock",
        )

        assert isinstance(response, LLMResponse)
        assert response.content
        assert response.prompt_pack_id == "PRM-TEST-001"
        assert response.provider_id == "mock"
        assert "llm_call" in response.evidence


class TestLoadPrompt:
    """Tests for load_prompt function."""

    def test_load_prompt_requires_id(self):
        """load_prompt raises if ID missing."""
        with pytest.raises(LLMError) as exc:
            load_prompt("")
        assert exc.value.code == "PROMPT_ID_REQUIRED"

    def test_load_prompt_validates_format(self):
        """load_prompt validates ID format."""
        with pytest.raises(LLMError) as exc:
            load_prompt("invalid-format")
        assert exc.value.code == "INVALID_PROMPT_ID"

    def test_load_prompt_not_found(self):
        """load_prompt raises if file missing."""
        with pytest.raises(LLMError) as exc:
            load_prompt("PRM-MISSING-001")
        assert exc.value.code == "PROMPT_NOT_FOUND"


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_to_dict(self):
        """to_dict returns proper structure."""
        response = LLMResponse(
            content="Test content",
            model="test-model",
            usage={"input_tokens": 10, "output_tokens": 5},
            request_id="req-123",
            cached=False,
            evidence={},
            prompt_pack_id="PRM-TEST-001",
            provider_id="mock",
        )

        d = response.to_dict()
        assert d["content"] == "Test content"
        assert d["model"] == "test-model"
        assert d["prompt_pack_id"] == "PRM-TEST-001"
        assert d["provider_id"] == "mock"
