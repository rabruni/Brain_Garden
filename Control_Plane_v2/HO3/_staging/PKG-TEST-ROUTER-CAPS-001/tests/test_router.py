"""Tests for router module.

Tests verify pure routing: classify intent -> map to handler -> return.
No mode selection, no prompt pack selection, no capability checking.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import patch, MagicMock

from modules.router import (
    route_query,
    RouteResult,
    RouteMode,
)
from modules.router.decision import get_route_evidence, QueryClassification
from modules.router.prompt_router import IntentResult, classify_intent, _validate_output, VALID_INTENTS
from modules.router.capabilities import (
    gather_capabilities,
    _default_capabilities,
    format_capabilities_for_prompt,
    clear_capabilities_cache,
)


class TestPromptRouter:
    """Tests for prompt_router module."""

    def test_validate_output_valid(self):
        """Valid output passes validation."""
        result = {"intent": "list_packages", "confidence": 0.9, "reasoning": "test"}
        assert _validate_output(result) is True

    def test_validate_output_invalid_intent(self):
        """Invalid intent fails validation."""
        result = {"intent": "invalid_intent", "confidence": 0.9, "reasoning": "test"}
        assert _validate_output(result) is False

    def test_validate_output_invalid_confidence(self):
        """Out of range confidence fails validation."""
        result = {"intent": "list_packages", "confidence": 1.5, "reasoning": "test"}
        assert _validate_output(result) is False

    def test_validate_output_missing_reasoning(self):
        """Missing reasoning fails validation."""
        result = {"intent": "list_packages", "confidence": 0.9, "reasoning": ""}
        assert _validate_output(result) is False

    def test_validate_output_with_custom_intents(self):
        """Validation with custom intents set."""
        result = {"intent": "custom_intent", "confidence": 0.9, "reasoning": "test"}
        assert _validate_output(result) is False
        assert _validate_output(result, valid_intents={"custom_intent"}) is True

    def test_intent_result_to_dict(self):
        """IntentResult converts to dict."""
        result = IntentResult(
            intent="list_packages",
            confidence=0.9,
            artifact_id=None,
            file_path=None,
            reasoning="test"
        )
        d = result.to_dict()
        assert d["intent"] == "list_packages"
        assert d["confidence"] == 0.9
        assert d["reasoning"] == "test"


class TestRouteQuery:
    """Tests for route_query function — pure routing."""

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_route_list_to_handler(self, mock_classify, mock_caps):
        """List query routes to list_installed handler."""
        mock_classify.return_value = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="Requesting package list"
        )
        result = route_query("What packages are installed?")
        assert result.handler == "list_installed"
        assert result.mode == RouteMode.ROUTED

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_route_explain_to_handler(self, mock_classify, mock_caps):
        """Explain query routes to explain handler."""
        mock_classify.return_value = IntentResult(
            intent="explain_artifact",
            confidence=0.95,
            artifact_id="FMWK-000",
            reasoning="Asking about specific framework"
        )
        result = route_query("Explain FMWK-000")
        assert result.handler == "explain"
        assert result.classification.extracted_args["artifact_id"] == "FMWK-000"

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_route_validate_to_handler(self, mock_classify, mock_caps):
        """Validate query routes to validate_document handler."""
        mock_classify.return_value = IntentResult(
            intent="validate",
            confidence=0.85,
            reasoning="Request to validate document"
        )
        result = route_query("Validate this document")
        assert result.handler == "validate_document"
        assert result.mode == RouteMode.ROUTED

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_route_summarize_to_handler(self, mock_classify, mock_caps):
        """Summarize query routes to summarize handler."""
        mock_classify.return_value = IntentResult(
            intent="summarize",
            confidence=0.9,
            reasoning="Request to summarize frameworks"
        )
        result = route_query("Summarize frameworks")
        assert result.handler == "summarize"

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_route_general_to_handler(self, mock_classify, mock_caps):
        """General query routes to general handler."""
        mock_classify.return_value = IntentResult(
            intent="general",
            confidence=0.5,
            reasoning="Ambiguous query"
        )
        result = route_query("Random question")
        assert result.handler == "general"

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_route_unknown_intent_defaults_to_general(self, mock_classify, mock_caps):
        """Unknown intent defaults to general handler."""
        mock_classify.return_value = IntentResult(
            intent="nonexistent_xyz",
            confidence=0.6,
            reasoning="Unknown intent"
        )
        result = route_query("Any query")
        assert result.handler == "general"

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_route_result_to_dict(self, mock_classify, mock_caps):
        """RouteResult converts to dict."""
        mock_classify.return_value = IntentResult(
            intent="list_packages",
            confidence=0.9,
            reasoning="test"
        )
        result = route_query("List packages")
        d = result.to_dict()
        assert "mode" in d
        assert "handler" in d
        assert "classification" in d
        assert d["mode"] == "routed"

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_route_mode_is_always_routed(self, mock_classify, mock_caps):
        """route_query always returns ROUTED mode (never DENIED)."""
        for intent in ["list_packages", "general", "validate", "summarize"]:
            mock_classify.return_value = IntentResult(
                intent=intent,
                confidence=0.5,
                reasoning="test"
            )
            result = route_query("test")
            assert result.mode == RouteMode.ROUTED

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_no_prompt_pack_in_result(self, mock_classify, mock_caps):
        """RouteResult no longer has prompt_pack_id field."""
        mock_classify.return_value = IntentResult(
            intent="validate",
            confidence=0.9,
            reasoning="test"
        )
        result = route_query("Validate document")
        assert not hasattr(result, "prompt_pack_id")

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_capabilities_passed_to_classify(self, mock_classify, mock_caps):
        """When capabilities are gathered, they are passed to classify_intent."""
        mock_caps.return_value = _default_capabilities()
        mock_classify.return_value = IntentResult(
            intent="list_packages",
            confidence=0.9,
            reasoning="test"
        )
        result = route_query("List packages")
        assert result.handler == "list_installed"
        # classify_intent should receive capabilities
        call_kwargs = mock_classify.call_args
        assert call_kwargs[1].get("capabilities") is not None or \
               (len(call_kwargs[0]) > 1 and call_kwargs[0][1] is not None)


class TestGetRouteEvidence:
    """Tests for get_route_evidence function."""

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_evidence_structure(self, mock_classify, mock_caps):
        """Evidence has required structure."""
        mock_classify.return_value = IntentResult(
            intent="list_packages",
            confidence=0.9,
            reasoning="test"
        )
        result = route_query("List packages")
        evidence = get_route_evidence(result)

        assert "route_decision" in evidence
        rd = evidence["route_decision"]
        assert "mode" in rd
        assert "handler" in rd
        assert "confidence" in rd
        assert "reason" in rd
        assert "router_provider_id" in rd

    @patch("modules.router.decision.gather_capabilities", return_value=None)
    @patch("modules.router.prompt_router.classify_intent")
    def test_evidence_no_prompt_pack(self, mock_classify, mock_caps):
        """Evidence no longer includes prompt_pack_id."""
        mock_classify.return_value = IntentResult(
            intent="validate",
            confidence=0.6,
            reasoning="Validation request"
        )
        result = route_query("Validate document")
        evidence = get_route_evidence(result)

        assert "prompt_pack_id" not in evidence["route_decision"]


class TestCapabilitiesGathering:
    """Tests for pre-router framework capability gathering."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_capabilities_cache()

    def test_default_capabilities_returns_intents(self):
        """_default_capabilities returns dict with intents array."""
        caps = _default_capabilities()
        assert "intents" in caps
        assert len(caps["intents"]) == 11

    def test_default_capabilities_has_required_intents(self):
        """Default capabilities include all required intents."""
        caps = _default_capabilities()
        intent_ids = {i["id"] for i in caps["intents"]}
        required = {"list_packages", "list_frameworks", "list_specs",
                     "explain_artifact", "health_check", "show_ledger",
                     "show_session", "read_file", "validate", "summarize", "general"}
        assert required.issubset(intent_ids)

    def test_format_capabilities_for_prompt(self):
        """format_capabilities_for_prompt produces readable text."""
        caps = _default_capabilities()
        text = format_capabilities_for_prompt(caps)
        assert "Available intent types:" in text
        assert "list_packages" in text
        assert "general" in text

    def test_gather_capabilities_caches_result(self):
        """Second call returns same cached object (identity check)."""
        result1 = gather_capabilities()
        result2 = gather_capabilities()
        # Same object identity proves caching
        assert result1 is result2
        assert "intents" in result1

    def test_clear_capabilities_cache_works(self):
        """clear_capabilities_cache allows fresh result."""
        result1 = gather_capabilities()
        clear_capabilities_cache()
        result2 = gather_capabilities()
        # Both valid
        assert "intents" in result1
        assert "intents" in result2


class TestClassifyIntentIntegration:
    """Integration tests for classify_intent (requires stdlib_llm)."""

    def test_classify_intent_works_with_llm(self):
        """classify_intent returns valid result when LLM is available."""
        result = classify_intent("any query")
        # Should return a valid intent (general for vague queries)
        assert result.intent in VALID_INTENTS
        assert 0.0 <= result.confidence <= 1.0
        assert result.reasoning is not None
