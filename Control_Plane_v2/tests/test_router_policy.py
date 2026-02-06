"""Tests for router policy module."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from modules.router.policy import (
    RoutePolicy,
    load_policy,
    enforce_policy,
    PolicyResult,
)
from modules.router.decision import route_query, RouteMode


CONTROL_PLANE = Path(__file__).parent.parent


class TestRoutePolicy:
    """Tests for RoutePolicy dataclass."""

    def test_default_policy(self):
        """Default policy has sensible values."""
        policy = RoutePolicy()
        assert policy.max_llm_calls_per_session == 10
        assert policy.llm_deny_list == []
        assert policy.llm_allow_list == []

    def test_from_dict(self):
        """Policy loads from dict."""
        data = {
            "max_llm_calls_per_session": 5,
            "llm_deny_list": ["list"],
        }
        policy = RoutePolicy.from_dict(data)
        assert policy.max_llm_calls_per_session == 5
        assert policy.llm_deny_list == ["list"]

    def test_to_dict(self):
        """Policy converts to dict."""
        policy = RoutePolicy(max_llm_calls_per_session=5)
        d = policy.to_dict()
        assert d["max_llm_calls_per_session"] == 5


class TestLoadPolicy:
    """Tests for load_policy function."""

    def test_load_policy(self):
        """Policy loads from file."""
        policy = load_policy()
        assert isinstance(policy, RoutePolicy)
        # Config file exists with defaults
        assert policy.max_llm_calls_per_session == 10


class TestEnforcePolicy:
    """Tests for enforce_policy function."""

    def test_enforce_allows_tools_first(self):
        """Tools-first is always allowed."""
        result = route_query("List packages")
        policy = RoutePolicy()

        enforced = enforce_policy(result, policy)
        assert enforced.allowed is True
        assert enforced.route_result.mode == RouteMode.TOOLS_FIRST

    def test_enforce_deny_list(self):
        """Deny list blocks LLM."""
        capabilities = {"llm_assisted": {"validate": True}}
        result = route_query("Validate document", capabilities=capabilities)
        policy = RoutePolicy(llm_deny_list=["validate_document"])

        enforced = enforce_policy(result, policy)
        # Mode changed from LLM_ASSISTED to TOOLS_FIRST
        assert enforced.route_result.mode == RouteMode.TOOLS_FIRST
        assert len(enforced.violations) > 0
        assert len(enforced.modifications) > 0

    def test_enforce_session_limit(self):
        """Session LLM limit is enforced."""
        capabilities = {"llm_assisted": {"validate": True}}
        result = route_query("Validate document", capabilities=capabilities)
        policy = RoutePolicy(max_llm_calls_per_session=5)

        # At limit
        enforced = enforce_policy(result, policy, session_llm_count=5)
        assert enforced.route_result.mode == RouteMode.TOOLS_FIRST
        assert "limit reached" in str(enforced.violations)

    def test_enforce_below_limit(self):
        """Below limit allows LLM."""
        capabilities = {"llm_assisted": {"validate": True}}
        result = route_query("Validate document", capabilities=capabilities)
        policy = RoutePolicy(max_llm_calls_per_session=10)

        enforced = enforce_policy(result, policy, session_llm_count=5)
        assert enforced.route_result.mode == RouteMode.LLM_ASSISTED

    def test_enforce_custom_handler(self):
        """Custom handler overrides default."""
        result = route_query("List packages")
        policy = RoutePolicy(custom_handlers={"list_installed": "custom_list_handler"})

        enforced = enforce_policy(result, policy)
        assert enforced.route_result.handler == "custom_list_handler"
        assert "Changed handler" in str(enforced.modifications)

    def test_policy_result_to_dict(self):
        """PolicyResult converts to dict."""
        result = route_query("List packages")
        policy = RoutePolicy()
        enforced = enforce_policy(result, policy)

        d = enforced.to_dict()
        assert "allowed" in d
        assert "route_result" in d
        assert "violations" in d


class TestPipeCLI:
    """Tests for router CLI via pipe."""

    def run_pipe(self, input_data: dict) -> dict:
        """Run router via pipe."""
        result = subprocess.run(
            [sys.executable, "-m", "modules.router"],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            cwd=str(CONTROL_PLANE),
        )
        return json.loads(result.stdout)

    def test_classify_via_pipe(self):
        """Route operation classifies queries via pipe."""
        response = self.run_pipe({
            "operation": "route",
            "query": "What packages are installed?",
        })

        assert response["status"] == "ok"
        assert response["result"]["handler"] == "list_installed"
        assert response["result"]["mode"] == "tools_first"

    def test_route_via_pipe(self):
        """Route operation works via pipe."""
        response = self.run_pipe({
            "operation": "route",
            "query": "List packages",
        })

        assert response["status"] == "ok"
        assert response["result"]["mode"] == "tools_first"
        assert response["result"]["handler"] == "list_installed"

    def test_route_with_capabilities(self):
        """Route with capabilities works via pipe."""
        response = self.run_pipe({
            "operation": "route",
            "query": "Validate document",
            "capabilities": {"llm_assisted": {"validate": True}},
        })

        assert response["status"] == "ok"
        assert response["result"]["mode"] == "llm_assisted"

    def test_list_handlers_via_pipe(self):
        """List handlers operation works via pipe."""
        response = self.run_pipe({
            "operation": "list_handlers",
        })

        assert response["status"] == "ok"
        assert "handlers" in response["result"]
        assert "list_packages" in response["result"]["handlers"]

    def test_evidence_in_response(self):
        """Evidence is included in response."""
        response = self.run_pipe({
            "operation": "route",
            "query": "List packages",
        })

        assert "evidence" in response
        assert "timestamp" in response["evidence"]
        assert "route_decision" in response["evidence"]
        assert "policy" in response["evidence"]
