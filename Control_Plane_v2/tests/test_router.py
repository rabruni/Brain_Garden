"""Tests for router module."""

import pytest

from modules.router import (
    classify_query,
    route_query,
    RouteResult,
    RouteMode,
    QueryClassification,
)
from modules.router.classifier import QueryType, needs_llm_classification
from modules.router.decision import get_route_evidence


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


class TestRouteQuery:
    """Tests for route_query function."""

    def test_route_list_tools_first(self):
        """List query routes to tools-first."""
        result = route_query("What packages are installed?")
        assert result.mode == RouteMode.TOOLS_FIRST
        assert result.handler == "list_installed"

    def test_route_explain_tools_first(self):
        """Explain query routes to tools-first."""
        result = route_query("Explain FMWK-000")
        assert result.mode == RouteMode.TOOLS_FIRST
        assert result.handler == "explain"

    def test_route_validate_denied_no_capability(self):
        """Validate query denied without capability."""
        result = route_query("Validate this document")
        assert result.mode == RouteMode.DENIED
        assert "LLM capability" in result.reason

    def test_route_validate_llm_with_capability(self):
        """Validate query uses LLM with capability."""
        capabilities = {"llm_assisted": {"validate": True}}
        result = route_query("Validate this document", capabilities=capabilities)
        assert result.mode == RouteMode.LLM_ASSISTED
        assert result.handler == "validate_document"
        assert result.prompt_pack_id == "PRM-ADMIN-VALIDATE-001"

    def test_route_summarize_denied_no_capability(self):
        """Summarize query denied without capability."""
        result = route_query("Summarize frameworks")
        assert result.mode == RouteMode.DENIED

    def test_route_summarize_llm_with_capability(self):
        """Summarize query uses LLM with capability."""
        capabilities = {"llm_assisted": {"summarize": True}}
        result = route_query("Summarize frameworks", capabilities=capabilities)
        assert result.mode == RouteMode.LLM_ASSISTED

    def test_route_fail_closed(self):
        """Unknown query fails closed to tools-first."""
        result = route_query("Random unknown query")
        assert result.mode == RouteMode.TOOLS_FIRST
        assert "Fail-closed" in result.reason or "Pattern matched" in result.reason

    def test_route_result_to_dict(self):
        """RouteResult converts to dict."""
        result = route_query("List packages")
        d = result.to_dict()
        assert "mode" in d
        assert "handler" in d
        assert "classification" in d


class TestGetRouteEvidence:
    """Tests for get_route_evidence function."""

    def test_evidence_structure(self):
        """Evidence has required structure."""
        result = route_query("List packages")
        evidence = get_route_evidence(result)

        assert "route_decision" in evidence
        assert "mode" in evidence["route_decision"]
        assert "handler" in evidence["route_decision"]
        assert "query_type" in evidence["route_decision"]
        assert "pattern_matched" in evidence["route_decision"]

    def test_evidence_llm_assisted(self):
        """Evidence includes prompt_pack_id for LLM."""
        capabilities = {"llm_assisted": {"validate": True}}
        result = route_query("Validate document", capabilities=capabilities)
        evidence = get_route_evidence(result)

        assert evidence["route_decision"]["mode"] == "llm_assisted"
        assert evidence["route_decision"]["prompt_pack_id"] == "PRM-ADMIN-VALIDATE-001"
