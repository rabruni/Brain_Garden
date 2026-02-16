"""Tests for PKG-LLM-GATEWAY-001 — LLM Gateway rename.

18 tests covering: class rename, aliases, all public exports,
backward-compat shim, route success path, constructor/method signatures.
No real LLM calls. All tests use MockProvider and tmp_path.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_staging = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT"))
sys.path.insert(0, str(_staging / "PKG-TOKEN-BUDGETER-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel"))


@pytest.fixture(autouse=True)
def _bypass_pristine():
    with patch("kernel.pristine.assert_append_only", return_value=None):
        yield


class TestClassRename:
    def test_llm_gateway_class_exists(self):
        from llm_gateway import LLMGateway
        assert LLMGateway is not None

    def test_prompt_router_alias_in_gateway(self):
        from llm_gateway import LLMGateway, PromptRouter
        assert PromptRouter is LLMGateway

    def test_route_method_exists(self):
        from llm_gateway import LLMGateway
        assert hasattr(LLMGateway, "route")

    def test_from_config_file_exists(self):
        from llm_gateway import LLMGateway
        assert hasattr(LLMGateway, "from_config_file")

    def test_register_provider_exists(self):
        from llm_gateway import LLMGateway
        assert hasattr(LLMGateway, "register_provider")


class TestPublicExports:
    def test_prompt_request_dataclass(self):
        from llm_gateway import PromptRequest
        assert PromptRequest is not None

    def test_prompt_response_dataclass(self):
        from llm_gateway import PromptResponse
        assert PromptResponse is not None

    def test_route_outcome_enum(self):
        from llm_gateway import RouteOutcome
        assert RouteOutcome.SUCCESS.value == "SUCCESS"
        assert RouteOutcome.REJECTED.value == "REJECTED"
        assert RouteOutcome.TIMEOUT.value == "TIMEOUT"
        assert RouteOutcome.ERROR.value == "ERROR"

    def test_circuit_state_enum(self):
        from llm_gateway import CircuitState
        assert CircuitState.CLOSED.value == "CLOSED"

    def test_router_config_dataclass(self):
        from llm_gateway import RouterConfig
        rc = RouterConfig()
        assert rc.default_provider == "mock"

    def test_circuit_breaker_config_dataclass(self):
        from llm_gateway import CircuitBreakerConfig
        cbc = CircuitBreakerConfig()
        assert cbc.failure_threshold == 3

    def test_circuit_breaker_class(self):
        from llm_gateway import CircuitBreaker, CircuitBreakerConfig
        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.allow_request() is True


class TestRouteSuccess:
    def test_route_success(self, tmp_path):
        from llm_gateway import LLMGateway, PromptRequest, RouteOutcome
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(ledger_client=lc, dev_mode=True)
        gw.register_provider("mock", MockProvider())

        req = PromptRequest(
            prompt="Hello",
            prompt_pack_id="PRM-TEST-001",
            contract_id="CT-TEST-001",
            agent_id="test-agent",
            agent_class="ADMIN",
            framework_id="FMWK-000",
            package_id="PKG-TEST-001",
            work_order_id="WO-TEST-001",
            session_id="SES-TEST0001",
            tier="hot",
        )
        resp = gw.route(req)
        assert resp.outcome == RouteOutcome.SUCCESS
        assert resp.input_tokens > 0 or resp.output_tokens >= 0


class TestBackwardCompat:
    def test_backward_compat_import_shim(self):
        from prompt_router import PromptRouter
        from llm_gateway import LLMGateway
        assert PromptRouter is LLMGateway

    def test_backward_compat_route_via_shim(self, tmp_path):
        from prompt_router import PromptRouter, PromptRequest, RouteOutcome
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        router = PromptRouter(ledger_client=lc, dev_mode=True)
        router.register_provider("mock", MockProvider())

        req = PromptRequest(
            prompt="Hello via shim",
            prompt_pack_id="PRM-TEST-001",
            contract_id="CT-TEST-001",
            agent_id="test-agent",
            agent_class="ADMIN",
            framework_id="FMWK-000",
            package_id="PKG-TEST-001",
            work_order_id="WO-TEST-001",
            session_id="SES-TEST0001",
            tier="hot",
        )
        resp = router.route(req)
        assert resp.outcome == RouteOutcome.SUCCESS

    def test_all_exports_present(self):
        from llm_gateway import (
            LLMGateway, PromptRouter, PromptRequest, PromptResponse,
            RouteOutcome, CircuitState, CircuitBreaker, CircuitBreakerConfig,
            RouterConfig,
        )
        assert all(x is not None for x in [
            LLMGateway, PromptRouter, PromptRequest, PromptResponse,
            RouteOutcome, CircuitState, CircuitBreaker, CircuitBreakerConfig,
            RouterConfig,
        ])


class TestAPIUnchanged:
    def test_no_api_change_route_signature(self):
        import inspect
        from llm_gateway import LLMGateway
        sig = inspect.signature(LLMGateway.route)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "request" in params

    def test_no_api_change_constructor(self):
        import inspect
        from llm_gateway import LLMGateway
        sig = inspect.signature(LLMGateway.__init__)
        params = list(sig.parameters.keys())
        assert "ledger_client" in params
        assert "budgeter" in params
        assert "config" in params
