"""Tests for PKG-LLM-GATEWAY-001 — LLM Gateway rename.

18 tests covering: class rename, aliases, all public exports,
backward-compat shim, route success path, constructor/method signatures.
No real LLM calls. All tests use MockProvider and tmp_path.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Dual-context path detection: installed root vs staging packages
_HERE = Path(__file__).resolve().parent
_HOT = _HERE.parent
_INSTALLED = (_HOT / "kernel" / "ledger_client.py").exists()

if _INSTALLED:
    # Installed layout — all packages merged under HOT/
    _paths = [_HOT / "kernel", _HOT, _HOT / "scripts"]
else:
    # Staging layout — sibling packages under _staging/
    _STAGING = _HERE.parents[2]
    _paths = [
        _STAGING / "PKG-KERNEL-001" / "HOT" / "kernel",
        _STAGING / "PKG-KERNEL-001" / "HOT",
        _STAGING / "PKG-TOKEN-BUDGETER-001" / "HOT" / "kernel",
        _STAGING / "PKG-LLM-GATEWAY-001" / "HOT" / "kernel",
    ]

for _p in _paths:
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)


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


# Tool-Use Observability Tests (2) — HANDOFF-21
class TestToolUseObservability:
    def test_exchange_logs_tools_offered_count(self, tmp_path):
        from llm_gateway import LLMGateway, PromptRequest, RouteOutcome
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(ledger_client=lc, dev_mode=True)
        gw.register_provider("mock", MockProvider())

        tools = [
            {"name": "gate_check", "description": "Run gates", "input_schema": {"type": "object", "properties": {}}},
            {"name": "list_packages", "description": "List pkgs", "input_schema": {"type": "object", "properties": {}}},
        ]
        req = PromptRequest(
            prompt="Hello", prompt_pack_id="PRM-TEST-001",
            contract_id="CT-TEST-001", agent_id="test-agent",
            agent_class="ADMIN", framework_id="FMWK-000",
            package_id="PKG-TEST-001", work_order_id="WO-TEST-001",
            session_id="SES-TEST0001", tier="hot",
            tools=tools,
        )
        resp = gw.route(req)
        assert resp.outcome == RouteOutcome.SUCCESS

        entries = lc.read_all()
        exchange = [e for e in entries if e.event_type == "EXCHANGE"]
        assert len(exchange) >= 1
        assert exchange[0].metadata.get("tools_offered") == 2

    def test_exchange_logs_tool_use_in_response(self, tmp_path):
        from llm_gateway import LLMGateway, PromptRequest, RouteOutcome
        from ledger_client import LedgerClient
        from provider import MockProvider, ProviderResponse

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(ledger_client=lc, dev_mode=True)

        # Use a MockProvider that returns finish_reason="tool_use"
        mock_prov = MockProvider()
        mock_prov._responses = [ProviderResponse(
            content='{}', model="mock-model-1",
            input_tokens=10, output_tokens=5,
            request_id="req-test01", provider_id="mock",
            finish_reason="tool_use",
        )]
        gw.register_provider("mock", mock_prov)

        req = PromptRequest(
            prompt="Hello", prompt_pack_id="PRM-TEST-001",
            contract_id="CT-TEST-001", agent_id="test-agent",
            agent_class="ADMIN", framework_id="FMWK-000",
            package_id="PKG-TEST-001", work_order_id="WO-TEST-001",
            session_id="SES-TEST0001", tier="hot",
        )
        resp = gw.route(req)
        assert resp.outcome == RouteOutcome.SUCCESS

        entries = lc.read_all()
        exchange = [e for e in entries if e.event_type == "EXCHANGE"]
        assert len(exchange) >= 1
        assert exchange[0].metadata.get("tool_use_in_response") is True


# Tool-Use Passthrough Tests (4) — HANDOFF-22
class TestToolUsePassthrough:
    def test_prompt_response_has_finish_reason_field(self):
        """PromptResponse dataclass has finish_reason with default 'stop'."""
        from llm_gateway import PromptResponse, RouteOutcome
        resp = PromptResponse(
            content="test", outcome=RouteOutcome.SUCCESS,
            input_tokens=10, output_tokens=5,
            model_id="m", provider_id="p",
            latency_ms=1.0, timestamp="2026-02-16T00:00:00Z",
            exchange_entry_id="LED-001",
        )
        assert hasattr(resp, "finish_reason")
        assert resp.finish_reason == "stop"

    def test_prompt_response_has_content_blocks_field(self):
        """PromptResponse dataclass has content_blocks with default None."""
        from llm_gateway import PromptResponse, RouteOutcome
        resp = PromptResponse(
            content="test", outcome=RouteOutcome.SUCCESS,
            input_tokens=10, output_tokens=5,
            model_id="m", provider_id="p",
            latency_ms=1.0, timestamp="2026-02-16T00:00:00Z",
            exchange_entry_id="LED-001",
        )
        assert hasattr(resp, "content_blocks")
        assert resp.content_blocks is None

    def test_route_passes_finish_reason_from_provider(self, tmp_path):
        """route() sets response.finish_reason from provider_response.finish_reason."""
        from llm_gateway import LLMGateway, PromptRequest, RouteOutcome
        from ledger_client import LedgerClient
        from provider import MockProvider, ProviderResponse

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(ledger_client=lc, dev_mode=True)

        mock_prov = MockProvider()
        mock_prov._responses = [ProviderResponse(
            content='{}', model="mock-model-1",
            input_tokens=10, output_tokens=5,
            request_id="req-test01", provider_id="mock",
            finish_reason="tool_use",
        )]
        gw.register_provider("mock", mock_prov)

        req = PromptRequest(
            prompt="Hello", prompt_pack_id="PRM-TEST-001",
            contract_id="CT-TEST-001", agent_id="test-agent",
            agent_class="ADMIN", framework_id="FMWK-000",
            package_id="PKG-TEST-001", work_order_id="WO-TEST-001",
            session_id="SES-TEST0001", tier="hot",
        )
        resp = gw.route(req)
        assert resp.outcome == RouteOutcome.SUCCESS
        assert resp.finish_reason == "tool_use"

    def test_route_passes_content_blocks_from_provider(self, tmp_path):
        """route() sets response.content_blocks from provider_response.content_blocks (via getattr)."""
        from llm_gateway import LLMGateway, PromptRequest, RouteOutcome
        from ledger_client import LedgerClient
        from provider import MockProvider, ProviderResponse
        from dataclasses import dataclass

        # Create a ProviderResponse subclass that has content_blocks (like AnthropicResponse)
        @dataclass(frozen=True)
        class TestAnthropicResponse(ProviderResponse):
            content_blocks: tuple = ()

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(ledger_client=lc, dev_mode=True)

        tool_block = {"type": "tool_use", "id": "toolu_01", "name": "list_packages", "input": {}}
        mock_prov = MockProvider()
        mock_prov._responses = [TestAnthropicResponse(
            content='{}', model="mock-model-1",
            input_tokens=10, output_tokens=5,
            request_id="req-test02", provider_id="mock",
            finish_reason="tool_use",
            content_blocks=(tool_block,),
        )]
        gw.register_provider("mock", mock_prov)

        req = PromptRequest(
            prompt="List packages", prompt_pack_id="PRM-TEST-001",
            contract_id="CT-TEST-001", agent_id="test-agent",
            agent_class="ADMIN", framework_id="FMWK-000",
            package_id="PKG-TEST-001", work_order_id="WO-TEST-001",
            session_id="SES-TEST0001", tier="hot",
        )
        resp = gw.route(req)
        assert resp.outcome == RouteOutcome.SUCCESS
        assert resp.content_blocks is not None
        assert len(resp.content_blocks) == 1
        assert resp.content_blocks[0]["type"] == "tool_use"
        assert resp.content_blocks[0]["name"] == "list_packages"


# ===========================================================================
# Domain Tag Routing Tests (3) -- HANDOFF-29C
# ===========================================================================

class TestDomainTagRouting:
    def test_domain_tag_routes_local(self, tmp_path):
        """PromptRequest with domain_tags=["consolidation"], map routes to "local" -> provider_id="local"."""
        from llm_gateway import LLMGateway, PromptRequest, RouteOutcome, RouterConfig
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        config = RouterConfig(
            default_provider="anthropic",
            domain_tag_routes={"consolidation": {"provider_id": "local", "model_id": "llama-3-8b"}},
        )
        gw = LLMGateway(ledger_client=lc, config=config, dev_mode=True)
        gw.register_provider("local", MockProvider())
        gw.register_provider("anthropic", MockProvider())

        req = PromptRequest(
            prompt="Analyze signals",
            prompt_pack_id="PRM-CONSOLIDATE-001",
            contract_id="PRC-CONSOLIDATE-001",
            agent_id="test-agent",
            agent_class="ADMIN",
            framework_id="FMWK-000",
            package_id="PKG-TEST-001",
            work_order_id="WO-TEST-001",
            session_id="SES-TEST0001",
            tier="hot",
            domain_tags=["consolidation"],
        )
        resp = gw.route(req)
        assert resp.outcome == RouteOutcome.SUCCESS
        assert resp.provider_id == "local"

    def test_no_tag_routes_default(self, tmp_path):
        """PromptRequest with no domain_tags -> default provider used."""
        from llm_gateway import LLMGateway, PromptRequest, RouteOutcome, RouterConfig
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        config = RouterConfig(
            default_provider="anthropic",
            domain_tag_routes={"consolidation": {"provider_id": "local"}},
        )
        gw = LLMGateway(ledger_client=lc, config=config, dev_mode=True)
        gw.register_provider("anthropic", MockProvider())

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
        assert resp.provider_id == "anthropic"

    def test_explicit_provider_overrides_tags(self, tmp_path):
        """request.provider_id='anthropic' + domain_tags=['consolidation'] -> 'anthropic' wins."""
        from llm_gateway import LLMGateway, PromptRequest, RouteOutcome, RouterConfig
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        config = RouterConfig(
            default_provider="mock",
            domain_tag_routes={"consolidation": {"provider_id": "local"}},
        )
        gw = LLMGateway(ledger_client=lc, config=config, dev_mode=True)
        gw.register_provider("local", MockProvider())
        gw.register_provider("anthropic", MockProvider())

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
            provider_id="anthropic",
            domain_tags=["consolidation"],
        )
        resp = gw.route(req)
        assert resp.outcome == RouteOutcome.SUCCESS
        assert resp.provider_id == "anthropic"


class TestBudgetModes:
    def _request(self):
        from llm_gateway import PromptRequest
        return PromptRequest(
            prompt="hello",
            prompt_pack_id="PRM-TEST-001",
            contract_id="CT-TEST-001",
            agent_id="test-agent",
            agent_class="ADMIN",
            framework_id="FMWK-000",
            package_id="PKG-TEST-001",
            work_order_id="WO-TEST-001",
            session_id="SES-TEST0001",
            tier="hot",
            max_tokens=500,
        )

    def test_budget_mode_enforce_rejects(self, tmp_path):
        from types import SimpleNamespace
        from llm_gateway import LLMGateway, RouteOutcome
        from ledger_client import LedgerClient

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        budgeter = MagicMock()
        budgeter.check.return_value = SimpleNamespace(allowed=False, remaining=0, reason="BUDGET_EXHAUSTED")

        gw = LLMGateway(ledger_client=lc, budgeter=budgeter, dev_mode=True, budget_mode="enforce")
        resp = gw.route(self._request())

        assert resp.outcome == RouteOutcome.REJECTED
        assert resp.error_code == "BUDGET_EXHAUSTED"

    def test_budget_mode_warn_allows_request(self, tmp_path):
        from types import SimpleNamespace
        from llm_gateway import LLMGateway, RouteOutcome
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        budgeter = MagicMock()
        budgeter.check.return_value = SimpleNamespace(allowed=False, remaining=0, reason="BUDGET_EXHAUSTED")
        budgeter.debit.return_value = SimpleNamespace(
            success=True, remaining=-10, total_consumed=510, cost_incurred=0.01, ledger_entry_id="LED-budget01"
        )

        gw = LLMGateway(ledger_client=lc, budgeter=budgeter, dev_mode=True, budget_mode="warn")
        gw.register_provider("mock", MockProvider())
        req = self._request()
        req.provider_id = "mock"

        resp = gw.route(req)

        assert resp.outcome == RouteOutcome.SUCCESS
        warnings = [e for e in lc.read_all() if e.event_type == "BUDGET_WARNING"]
        assert len(warnings) >= 1

    def test_budget_mode_warn_logs_warning(self, tmp_path):
        from types import SimpleNamespace
        from llm_gateway import LLMGateway
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        budgeter = MagicMock()
        budgeter.check.return_value = SimpleNamespace(allowed=False, remaining=0, reason="BUDGET_EXHAUSTED")
        budgeter.debit.return_value = SimpleNamespace(
            success=True, remaining=-10, total_consumed=510, cost_incurred=0.01, ledger_entry_id="LED-budget02"
        )

        gw = LLMGateway(ledger_client=lc, budgeter=budgeter, dev_mode=True, budget_mode="warn")
        gw.register_provider("mock", MockProvider())
        req = self._request()
        req.provider_id = "mock"
        gw.route(req)

        warnings = [e for e in lc.read_all() if e.event_type == "BUDGET_WARNING"]
        assert len(warnings) >= 1
        assert "Budget check failed" in warnings[0].reason

    def test_budget_mode_off_bypasses_check(self, tmp_path):
        from types import SimpleNamespace
        from llm_gateway import LLMGateway, RouteOutcome
        from ledger_client import LedgerClient
        from provider import MockProvider

        ledger_path = tmp_path / "ledger" / "test.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        budgeter = MagicMock()
        budgeter.check.side_effect = AssertionError("check should not run in off mode")
        budgeter.debit.return_value = SimpleNamespace(
            success=True, remaining=-10, total_consumed=510, cost_incurred=0.01, ledger_entry_id="LED-budget03"
        )

        gw = LLMGateway(ledger_client=lc, budgeter=budgeter, dev_mode=True, budget_mode="off")
        gw.register_provider("mock", MockProvider())
        req = self._request()
        req.provider_id = "mock"
        resp = gw.route(req)

        assert resp.outcome == RouteOutcome.SUCCESS
        assert budgeter.check.call_count == 0


class TestTimeoutRetryPolicy29P:
    def _request(self):
        from llm_gateway import PromptRequest

        return PromptRequest(
            prompt="verbose request",
            prompt_pack_id="PRM-SYNTHESIZE-001",
            contract_id="PRC-SYNTHESIZE-001",
            agent_id="admin-001.ho1",
            agent_class="ADMIN",
            framework_id="FMWK-000",
            package_id="PKG-HO1-EXECUTOR-001",
            work_order_id="WO-TEST-RETRY",
            session_id="SES-RETRY0001",
            tier="ho1",
        )

    def test_route_retries_on_timeout_then_success(self, tmp_path):
        from llm_gateway import LLMGateway, RouterConfig, RouteOutcome
        from ledger_client import LedgerClient
        from provider import ProviderError, ProviderResponse

        class FlakyProvider:
            provider_id = "flaky"

            def __init__(self):
                self.calls = 0

            def send(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise ProviderError("first call timed out", code="TIMEOUT", retryable=True)
                return ProviderResponse(
                    content="ok after retry",
                    model=kwargs["model_id"],
                    input_tokens=10,
                    output_tokens=5,
                    request_id="req-retry-ok",
                    provider_id=self.provider_id,
                )

        ledger_path = tmp_path / "ledger" / "retry.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(
            ledger_client=lc,
            config=RouterConfig(default_provider="flaky", max_retries=1),
            dev_mode=True,
        )
        provider = FlakyProvider()
        gw.register_provider("flaky", provider)

        resp = gw.route(self._request())

        assert resp.outcome == RouteOutcome.SUCCESS
        assert provider.calls == 2

    def test_route_stops_after_max_retries_on_timeout(self, tmp_path):
        from llm_gateway import LLMGateway, RouterConfig, RouteOutcome
        from ledger_client import LedgerClient
        from provider import ProviderError

        class AlwaysTimeoutProvider:
            provider_id = "always-timeout"

            def __init__(self):
                self.calls = 0

            def send(self, **kwargs):
                self.calls += 1
                raise ProviderError("timeout every time", code="TIMEOUT", retryable=True)

        ledger_path = tmp_path / "ledger" / "retry-stop.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(
            ledger_client=lc,
            config=RouterConfig(default_provider="always-timeout", max_retries=2),
            dev_mode=True,
        )
        provider = AlwaysTimeoutProvider()
        gw.register_provider("always-timeout", provider)

        resp = gw.route(self._request())

        assert resp.outcome == RouteOutcome.TIMEOUT
        assert provider.calls == 3  # initial + 2 retries

    def test_route_does_not_retry_non_retryable_auth_error(self, tmp_path):
        from llm_gateway import LLMGateway, RouterConfig, RouteOutcome
        from ledger_client import LedgerClient
        from provider import ProviderError

        class AuthErrorProvider:
            provider_id = "auth-fail"

            def __init__(self):
                self.calls = 0

            def send(self, **kwargs):
                self.calls += 1
                raise ProviderError("bad key", code="AUTH_ERROR", retryable=False)

        ledger_path = tmp_path / "ledger" / "retry-auth.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(
            ledger_client=lc,
            config=RouterConfig(default_provider="auth-fail", max_retries=5),
            dev_mode=True,
        )
        provider = AuthErrorProvider()
        gw.register_provider("auth-fail", provider)

        resp = gw.route(self._request())

        assert resp.outcome == RouteOutcome.ERROR
        assert resp.error_code == "AUTH_ERROR"
        assert provider.calls == 1

    def test_route_uses_configured_timeout_ms(self, tmp_path):
        from llm_gateway import LLMGateway, RouterConfig
        from ledger_client import LedgerClient
        from provider import ProviderResponse

        observed = {"timeout_ms": None}

        class TimeoutCaptureProvider:
            provider_id = "capture"

            def send(self, **kwargs):
                observed["timeout_ms"] = kwargs.get("timeout_ms")
                return ProviderResponse(
                    content="ok",
                    model=kwargs["model_id"],
                    input_tokens=5,
                    output_tokens=2,
                    request_id="req-timeout-capture",
                    provider_id=self.provider_id,
                )

        ledger_path = tmp_path / "ledger" / "timeout-capture.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lc = LedgerClient(ledger_path=ledger_path)
        gw = LLMGateway(
            ledger_client=lc,
            config=RouterConfig(default_provider="capture", default_timeout_ms=65432),
            dev_mode=True,
        )
        gw.register_provider("capture", TimeoutCaptureProvider())

        gw.route(self._request())

        assert observed["timeout_ms"] == 65432
