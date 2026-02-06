"""Brain Module Unit Tests.

Tests for brain_call(), BrainResponse, and provider configuration.

Tests:
1. brain_call returns structured BrainResponse with all fields
2. BRAIN_LLM_PROVIDER env var is respected
3. Default provider falls back to get_default_provider_id()
4. Evidence dict includes provider_id and prompt_pack_id
5. brain_call passes PRM-BRAIN-001 to complete()
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

CONTROL_PLANE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from modules.brain.brain import (
    brain_call,
    BrainResponse,
    get_brain_provider_id,
    BRAIN_PROVIDER_ENV,
    BRAIN_PROMPT_PACK_ID,
)
from modules.stdlib_llm.client import LLMResponse


# =============================================================================
# Helpers
# =============================================================================

def _make_brain_json(**overrides) -> str:
    """Build valid brain JSON response."""
    data = {
        "intent": "User wants system status",
        "confidence": 0.85,
        "suggested_handler": "check_health",
        "mode": "tools_first",
        "proposed_next_step": "Run health check to verify system integrity.",
    }
    data.update(overrides)
    return json.dumps(data)


def _make_llm_response(content: str, provider_id: str = "mock") -> LLMResponse:
    """Build a mock LLMResponse."""
    return LLMResponse(
        content=content,
        model="test-model",
        usage={"input_tokens": 50, "output_tokens": 30},
        request_id="req-brain-test",
        cached=False,
        evidence={
            "llm_call": {
                "prompt_hash": "sha256:abc123",
                "response_hash": "sha256:def456",
                "model": "test-model",
            },
            "duration_ms": 100,
        },
        prompt_pack_id=BRAIN_PROMPT_PACK_ID,
        provider_id=provider_id,
    )


# =============================================================================
# 1. brain_call returns structured JSON
# =============================================================================

class TestBrainCallStructuredOutput:
    """brain_call() returns BrainResponse with all expected fields."""

    def test_brain_call_returns_brain_response(self):
        """brain_call returns a BrainResponse dataclass."""
        content = _make_brain_json()
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("check health", {"health": {"status": "ok"}})

        assert isinstance(result, BrainResponse)

    def test_brain_call_fields_populated(self):
        """BrainResponse has all fields from JSON output."""
        content = _make_brain_json(
            intent="User wants health check",
            confidence=0.9,
            suggested_handler="check_health",
            mode="tools_first",
            proposed_next_step="Run trace.py --verify.",
        )
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("check health", {})

        assert result.intent == "User wants health check"
        assert result.confidence == 0.9
        assert result.suggested_handler == "check_health"
        assert result.mode == "tools_first"
        assert result.proposed_next_step == "Run trace.py --verify."

    def test_brain_call_includes_raw_dict(self):
        """BrainResponse.raw contains the full parsed JSON."""
        content = _make_brain_json()
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("test", {})

        assert isinstance(result.raw, dict)
        assert "intent" in result.raw
        assert "suggested_handler" in result.raw

    def test_brain_call_invalid_handler_falls_back(self):
        """Invalid suggested_handler in LLM output falls back to general."""
        content = _make_brain_json(suggested_handler="nonexistent_handler")
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("test", {})

        assert result.suggested_handler == "general"
        assert result.confidence == 0.0

    def test_brain_call_invalid_mode_falls_back(self):
        """Invalid mode falls back to general."""
        content = _make_brain_json(mode="invalid_mode")
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("test", {})

        assert result.mode == "llm_assisted"
        assert result.confidence == 0.0

    def test_brain_call_handles_json_in_code_fence(self):
        """brain_call extracts JSON from ```json ... ``` wrapper."""
        raw_json = _make_brain_json()
        content = f"```json\n{raw_json}\n```"
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("test", {})

        assert result.suggested_handler == "check_health"


# =============================================================================
# 2. Provider env var
# =============================================================================

class TestBrainProviderEnvVar:
    """BRAIN_LLM_PROVIDER env var configures the brain provider."""

    def test_brain_provider_env_var_used(self):
        """Setting BRAIN_LLM_PROVIDER overrides the default."""
        saved = os.environ.get(BRAIN_PROVIDER_ENV)
        os.environ[BRAIN_PROVIDER_ENV] = "custom-brain-provider"
        try:
            assert get_brain_provider_id() == "custom-brain-provider"
        finally:
            if saved is not None:
                os.environ[BRAIN_PROVIDER_ENV] = saved
            else:
                del os.environ[BRAIN_PROVIDER_ENV]

    def test_brain_provider_passed_to_complete(self):
        """brain_call passes the configured provider_id to complete()."""
        content = _make_brain_json()
        mock_response = _make_llm_response(content, provider_id="test-brain")

        with patch("modules.brain.brain.complete", return_value=mock_response) as mock_complete, \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            brain_call("test", {}, provider_id="test-brain")

        mock_complete.assert_called_once()
        assert mock_complete.call_args[1]["provider_id"] == "test-brain"


# =============================================================================
# 3. Default provider fallback
# =============================================================================

class TestBrainDefaultProvider:
    """Default brain provider falls back to system default."""

    def test_default_provider_is_system_default(self):
        """Without BRAIN_LLM_PROVIDER, falls back to get_default_provider_id()."""
        saved = os.environ.pop(BRAIN_PROVIDER_ENV, None)
        try:
            with patch("modules.brain.brain.get_default_provider_id", return_value="anthropic"):
                assert get_brain_provider_id() == "anthropic"
        finally:
            if saved is not None:
                os.environ[BRAIN_PROVIDER_ENV] = saved

    def test_empty_env_var_falls_back(self):
        """Empty string for BRAIN_LLM_PROVIDER falls back to system default."""
        saved = os.environ.get(BRAIN_PROVIDER_ENV)
        os.environ[BRAIN_PROVIDER_ENV] = ""
        try:
            with patch("modules.brain.brain.get_default_provider_id", return_value="anthropic"):
                assert get_brain_provider_id() == "anthropic"
        finally:
            if saved is not None:
                os.environ[BRAIN_PROVIDER_ENV] = saved
            else:
                del os.environ[BRAIN_PROVIDER_ENV]


# =============================================================================
# 4. Evidence logging
# =============================================================================

class TestBrainEvidenceLogged:
    """Evidence dict has provider_id and prompt_pack_id."""

    def test_evidence_includes_provider_id(self):
        """BrainResponse.provider_id reflects the provider used."""
        content = _make_brain_json()
        mock_response = _make_llm_response(content, provider_id="evidence-test")

        with patch("modules.brain.brain.complete", return_value=mock_response), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("test", {}, provider_id="evidence-test")

        assert result.provider_id == "evidence-test"

    def test_evidence_dict_populated(self):
        """BrainResponse.evidence comes from the LLM response."""
        content = _make_brain_json()
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("test", {})

        assert isinstance(result.evidence, dict)
        assert "llm_call" in result.evidence

    def test_evidence_on_error(self):
        """On LLM error, evidence contains error info."""
        from modules.stdlib_llm.client import LLMError

        with patch("modules.brain.brain.complete", side_effect=LLMError("test fail", code="TEST")), \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            result = brain_call("test", {})

        assert result.confidence == 0.0
        assert "error" in result.evidence
        assert "test fail" in result.evidence["error"]


# =============================================================================
# 5. Governed prompt usage
# =============================================================================

class TestBrainUsesGovernedPrompt:
    """brain_call passes PRM-BRAIN-001 to complete()."""

    def test_brain_call_uses_prm_brain_001(self):
        """complete() is called with prompt_pack_id=PRM-BRAIN-001."""
        content = _make_brain_json()
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response) as mock_complete, \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```") as mock_load:
            brain_call("test", {})

        # load_prompt called with PRM-BRAIN-001
        mock_load.assert_called_once_with(BRAIN_PROMPT_PACK_ID)

        # complete called with prompt_pack_id=PRM-BRAIN-001
        assert mock_complete.call_args[1]["prompt_pack_id"] == BRAIN_PROMPT_PACK_ID

    def test_brain_call_temperature_zero(self):
        """complete() is called with temperature=0 (deterministic)."""
        content = _make_brain_json()
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response) as mock_complete, \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\n{{query}} {{system_context}}\n```"):
            brain_call("test", {})

        assert mock_complete.call_args[1]["temperature"] == 0

    def test_brain_call_renders_query_into_prompt(self):
        """The prompt passed to complete() contains the user query."""
        content = _make_brain_json()
        mock_response = _make_llm_response(content)

        with patch("modules.brain.brain.complete", return_value=mock_response) as mock_complete, \
             patch("modules.brain.brain.load_prompt", return_value="## Prompt Template\n```\nQuery: {{query}}\nContext: {{system_context}}\n```"):
            brain_call("what should I do next?", {"packages": []})

        # prompt is the first positional arg
        call_args, call_kwargs = mock_complete.call_args
        prompt_arg = call_args[0] if call_args else call_kwargs.get("prompt", "")
        assert "what should I do next?" in prompt_arg
        assert "packages" in prompt_arg
