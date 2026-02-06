"""Tests for router module."""

import pytest
from unittest.mock import patch, MagicMock

from modules.router import (
    classify_query,
    route_query,
    RouteResult,
    RouteMode,
    QueryClassification,
)
from modules.router.classifier import QueryType, needs_llm_classification
from modules.router.decision import get_route_evidence
from modules.router.prompt_router import IntentResult, classify_intent, _validate_output, VALID_INTENTS


class TestClassifyQuery:
    """Tests for classify_query function."""

    def test_classify_list_packages(self):
        """List packages query classified correctly."""
        result = classify_query("What packages are installed?")
        assert result.type == QueryType.LIST
        assert result.confidence == 1.0
        assert result.pattern_matched is True

    def test_classify_list_variants(self):
        """Various list query variants work."""
        queries = [
            "list packages",
            "show installed packages",
            "packages",
            "list all packages",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.LIST, f"Failed for: {query}"

    def test_classify_explain_artifact(self):
        """Explain artifact query classified correctly."""
        result = classify_query("Explain FMWK-000")
        assert result.type == QueryType.EXPLAIN
        assert result.pattern_matched is True
        assert result.extracted_args.get("artifact_id") == "FMWK-000"

    def test_classify_explain_variants(self):
        """Various explain query variants work."""
        queries = [
            ("What is SPEC-CORE-001", "SPEC-CORE-001"),
            ("Describe PKG-KERNEL-001", "PKG-KERNEL-001"),
            ("Tell me about FMWK-100", "FMWK-100"),
            ("FMWK-000", "FMWK-000"),  # Direct ID
        ]
        for query, expected_id in queries:
            result = classify_query(query)
            assert result.type == QueryType.EXPLAIN, f"Failed for: {query}"
            assert result.extracted_args.get("artifact_id") == expected_id

    def test_classify_status(self):
        """Status query classified correctly."""
        result = classify_query("System health check")
        assert result.type == QueryType.STATUS
        assert result.pattern_matched is True

    def test_classify_status_variants(self):
        """Various status query variants work."""
        queries = [
            "health",
            "system status",
            "verify",
            "is everything ok?",
        ]
        for query in queries:
            result = classify_query(query)
            assert result.type == QueryType.STATUS, f"Failed for: {query}"

    def test_classify_inventory(self):
        """Inventory query classified correctly."""
        result = classify_query("show inventory")
        assert result.type == QueryType.INVENTORY
        assert result.pattern_matched is True

    def test_classify_validate(self):
        """Validate query classified correctly."""
        result = classify_query("Validate this document")
        assert result.type == QueryType.VALIDATE
        assert result.pattern_matched is True

    def test_classify_summarize(self):
        """Summarize query classified correctly."""
        result = classify_query("Summarize the frameworks")
        assert result.type == QueryType.SUMMARIZE
        assert result.pattern_matched is True

    def test_classify_general(self):
        """Unknown query returns general type."""
        result = classify_query("Some random question")
        assert result.type == QueryType.GENERAL
        assert result.pattern_matched is False
        assert result.confidence < 1.0

    def test_classify_empty(self):
        """Empty query returns general with low confidence."""
        result = classify_query("")
        assert result.type == QueryType.GENERAL
        assert result.confidence == 0.0


class TestNeedsLLMClassification:
    """Tests for needs_llm_classification function."""

    def test_pattern_matched_no_llm(self):
        """Pattern matched queries don't need LLM."""
        result = classify_query("What packages are installed?")
        assert needs_llm_classification(result) is False

    def test_general_needs_llm(self):
        """General queries might need LLM."""
        result = classify_query("Some random question")
        assert needs_llm_classification(result) is True


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
    """Tests for route_query function with mocked LLM classification."""

    @patch("modules.router.prompt_router.classify_intent")
    def test_route_list_tools_first(self, mock_classify):
        """List query routes to tools-first with high confidence."""
        mock_classify.return_value = IntentResult(
            intent="list_packages",
            confidence=0.95,
            reasoning="Requesting package list"
        )
        result = route_query("What packages are installed?")
        assert result.mode == RouteMode.TOOLS_FIRST
        assert result.handler == "list_installed"

    @patch("modules.router.prompt_router.classify_intent")
    def test_route_explain_tools_first(self, mock_classify):
        """Explain query routes to tools-first with high confidence."""
        mock_classify.return_value = IntentResult(
            intent="explain_artifact",
            confidence=0.95,
            artifact_id="FMWK-000",
            reasoning="Asking about specific framework"
        )
        result = route_query("Explain FMWK-000")
        assert result.mode == RouteMode.TOOLS_FIRST
        assert result.handler == "explain"
        assert result.classification.extracted_args["artifact_id"] == "FMWK-000"

    @patch("modules.router.prompt_router.classify_intent")
    def test_route_validate_llm_assisted(self, mock_classify):
        """Validate query uses LLM-assisted mode."""
        mock_classify.return_value = IntentResult(
            intent="validate",
            confidence=0.85,
            reasoning="Request to validate document"
        )
        result = route_query("Validate this document")
        assert result.mode == RouteMode.LLM_ASSISTED  # LLM-required intent
        assert result.handler == "validate_document"
        assert result.prompt_pack_id == "PRM-ADMIN-VALIDATE-001"

    @patch("modules.router.prompt_router.classify_intent")
    def test_route_summarize_llm_assisted(self, mock_classify):
        """Summarize query uses LLM-assisted mode."""
        mock_classify.return_value = IntentResult(
            intent="summarize",
            confidence=0.9,
            reasoning="Request to summarize frameworks"
        )
        result = route_query("Summarize frameworks")
        assert result.mode == RouteMode.LLM_ASSISTED  # LLM-required intent
        assert result.handler == "summarize"

    @patch("modules.router.prompt_router.classify_intent")
    def test_route_low_confidence_llm_assisted(self, mock_classify):
        """Low confidence routes to LLM-assisted."""
        mock_classify.return_value = IntentResult(
            intent="general",
            confidence=0.5,
            reasoning="Ambiguous query"
        )
        result = route_query("Random question")
        assert result.mode == RouteMode.LLM_ASSISTED
        assert result.handler == "general"

    @patch("modules.router.prompt_router.classify_intent")
    def test_route_error_fallback(self, mock_classify):
        """Router error falls back to general handler."""
        mock_classify.return_value = IntentResult(
            intent="general",
            confidence=0.0,
            reasoning="LLM error: connection failed"
        )
        result = route_query("Any query")
        assert result.mode == RouteMode.LLM_ASSISTED
        assert result.handler == "general"

    @patch("modules.router.prompt_router.classify_intent")
    def test_route_result_to_dict(self, mock_classify):
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


class TestGetRouteEvidence:
    """Tests for get_route_evidence function."""

    @patch("modules.router.prompt_router.classify_intent")
    def test_evidence_structure(self, mock_classify):
        """Evidence has required structure."""
        mock_classify.return_value = IntentResult(
            intent="list_packages",
            confidence=0.9,
            reasoning="test"
        )
        result = route_query("List packages")
        evidence = get_route_evidence(result)

        assert "route_decision" in evidence
        assert "mode" in evidence["route_decision"]
        assert "handler" in evidence["route_decision"]
        assert "query_type" in evidence["route_decision"]
        assert "pattern_matched" in evidence["route_decision"]

    @patch("modules.router.prompt_router.classify_intent")
    def test_evidence_llm_assisted(self, mock_classify):
        """Evidence includes prompt_pack_id for LLM."""
        mock_classify.return_value = IntentResult(
            intent="validate",
            confidence=0.6,  # Low confidence triggers LLM_ASSISTED
            reasoning="Validation request"
        )
        result = route_query("Validate document")
        evidence = get_route_evidence(result)

        assert evidence["route_decision"]["mode"] == "llm_assisted"
        assert evidence["route_decision"]["prompt_pack_id"] == "PRM-ADMIN-VALIDATE-001"


class TestClassifyIntentIntegration:
    """Integration tests for classify_intent (requires stdlib_llm)."""

    def test_classify_intent_works_with_llm(self):
        """classify_intent returns valid result when LLM is available."""
        result = classify_intent("any query")
        # Should return a valid intent (general for vague queries)
        assert result.intent in VALID_INTENTS
        assert 0.0 <= result.confidence <= 1.0
        assert result.reasoning is not None
