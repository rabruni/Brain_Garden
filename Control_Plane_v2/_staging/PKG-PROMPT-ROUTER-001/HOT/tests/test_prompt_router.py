"""Tests for prompt router exchange recording model.

DTT: tests written FIRST, implementation follows.
All tests use MockProvider and a tmp_path ledger.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add kernel paths
_staging = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-PROMPT-ROUTER-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-TOKEN-BUDGETER-001" / "HOT" / "kernel"))

from ledger_client import LedgerClient  # noqa: E402
from prompt_router import (  # noqa: E402
    CircuitBreaker,
    CircuitBreakerConfig,
    PromptRequest,
    PromptRouter,
    RouteOutcome,
    RouterConfig,
)
from provider import MockProvider, ProviderError  # noqa: E402
from token_budgeter import (  # noqa: E402
    BudgetAllocation,
    BudgetConfig,
    BudgetScope,
    TokenBudgeter,
)


@pytest.fixture(autouse=True)
def _bypass_pristine():
    """Bypass pristine boundary checks for tmp_path ledger writes."""
    with patch("kernel.pristine.assert_append_only", return_value=None):
        yield


def _make_ledger(tmp_path: Path) -> LedgerClient:
    """Create a fresh ledger in tmp_path."""
    ledger_path = tmp_path / "ledger" / "governance.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    return LedgerClient(ledger_path=ledger_path)


def _default_router_config() -> RouterConfig:
    """Default router config for tests."""
    return RouterConfig(
        default_provider="mock",
        default_model="mock-model-1",
        default_timeout_ms=5000,
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout_ms=1000,
            half_open_max=1,
        ),
    )


def _default_budget_config() -> BudgetConfig:
    """Default budget config for router tests."""
    return BudgetConfig(
        session_token_limit=100000,
        wo_token_limit=50000,
        agent_token_limit=10000,
        wo_turn_limit=20,
        wo_timeout_seconds=3600,
        pricing={
            "mock-model-1": {"input_per_1k": 0.01, "output_per_1k": 0.03},
        },
    )


def _make_router(
    tmp_path: Path,
    provider: MockProvider | None = None,
    budgeter: TokenBudgeter | None = None,
    dev_mode: bool = True,
    config: RouterConfig | None = None,
) -> tuple[PromptRouter, LedgerClient]:
    """Create a router with mock provider and optional budgeter."""
    ledger = _make_ledger(tmp_path)
    if provider is None:
        provider = MockProvider()
    cfg = config or _default_router_config()
    router = PromptRouter(
        ledger_client=ledger,
        budgeter=budgeter,
        config=cfg,
        dev_mode=dev_mode,
    )
    router.register_provider("mock", provider)
    return router, ledger


def _default_request(**overrides) -> PromptRequest:
    """Create a default valid prompt request."""
    defaults = dict(
        prompt="What is 2+2?",
        prompt_pack_id="PRM-TEST-001",
        contract_id="PRC-TEST-001",
        agent_id="agent-test-001",
        agent_class="KERNEL.syntactic",
        framework_id="FMWK-000",
        package_id="PKG-TEST-001",
        work_order_id="WO-20260210-001",
        session_id="SES-TEST0001",
        tier="hot",
    )
    defaults.update(overrides)
    return PromptRequest(**defaults)


def _first_exchange(ledger: LedgerClient):
    exchanges = ledger.read_by_event_type("EXCHANGE")
    assert len(exchanges) == 1
    return exchanges[0]


def _first_dispatch(ledger: LedgerClient):
    dispatches = ledger.read_by_event_type("DISPATCH")
    assert len(dispatches) == 1
    return dispatches[0]


class TestPromptRouterExchangeModel:
    """Prompt router exchange recording tests."""

    # Exchange recording tests (1-10)

    def test_exchange_contains_prompt_text(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)
        request = _default_request(prompt="Explain gravity")

        router.route(request)

        ex = _first_exchange(ledger)
        assert ex.metadata["prompt"] == request.prompt

    def test_exchange_contains_response_text(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert ex.metadata["response"] == "Mock response"

    def test_exchange_contains_outcome(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert ex.metadata["outcome"] == "success"

    def test_single_exchange_per_roundtrip(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        assert len(ledger.read_by_event_type("EXCHANGE")) == 1

    def test_no_prompt_sent_or_received_entries(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        assert len(ledger.read_by_event_type("PROMPT_SENT")) == 0
        assert len(ledger.read_by_event_type("PROMPT_RECEIVED")) == 0

    def test_exchange_has_normalized_identity(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        for key in [
            "agent_id",
            "session_id",
            "work_order_id",
            "tier",
            "contract_id",
            "framework_id",
        ]:
            assert key in ex.metadata

    def test_exchange_has_cost_fields(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert ex.metadata["input_tokens"] == 100
        assert ex.metadata["output_tokens"] == 50

    def test_exchange_has_model_id(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert ex.metadata["model_id"] == "mock-model-1"

    def test_exchange_no_redundant_fields(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        redundant = {
            "agent_class",
            "package_id",
            "prompt_pack_id",
            "max_tokens",
            "temperature",
            "domain_tags",
            "provider_id",
        }
        assert redundant.isdisjoint(set(ex.metadata.keys()))

    def test_exchange_has_context_hash(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert re.match(r"^[a-f0-9]{64}$", ex.metadata["context_hash"])

    # Dispatch marker tests (11-14)

    def test_dispatch_marker_written_before_exchange(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        all_entries = ledger.read_all()
        assert len(all_entries) == 2
        assert all_entries[0].event_type == "DISPATCH"
        assert all_entries[1].event_type == "EXCHANGE"

    def test_dispatch_marker_is_lightweight(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        dispatch = _first_dispatch(ledger)
        assert set(dispatch.metadata.keys()) == {"contract_id", "agent_id", "session_id"}

    def test_exchange_links_to_dispatch(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        router.route(_default_request())

        dispatch = _first_dispatch(ledger)
        exchange = _first_exchange(ledger)
        assert exchange.metadata["dispatch_entry_id"] == dispatch.id

    def test_dispatch_without_exchange_on_error(self, tmp_path: Path) -> None:
        provider = MockProvider(
            fail_after=0,
            fail_with=ProviderError(message="boom", code="SERVER_ERROR", retryable=False),
        )
        router, ledger = _make_router(tmp_path, provider=provider)

        router.route(_default_request())

        dispatch = _first_dispatch(ledger)
        exchange = _first_exchange(ledger)
        assert dispatch.event_type == "DISPATCH"
        assert exchange.metadata["outcome"] == "error"

    # Error path tests (15-19)

    def test_error_exchange_contains_prompt(self, tmp_path: Path) -> None:
        provider = MockProvider(
            fail_after=0,
            fail_with=ProviderError(message="provider exploded", code="SERVER_ERROR", retryable=False),
        )
        router, ledger = _make_router(tmp_path, provider=provider)
        request = _default_request(prompt="Risky prompt")

        router.route(request)

        ex = _first_exchange(ledger)
        assert ex.metadata["prompt"] == request.prompt

    def test_error_exchange_has_error_fields(self, tmp_path: Path) -> None:
        provider = MockProvider(
            fail_after=0,
            fail_with=ProviderError(message="timeout reached", code="TIMEOUT", retryable=True),
        )
        router, ledger = _make_router(tmp_path, provider=provider)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert ex.metadata["error_code"] == "TIMEOUT"
        assert "timeout reached" in ex.metadata["error_message"]

    def test_timeout_exchange_outcome(self, tmp_path: Path) -> None:
        provider = MockProvider(
            fail_after=0,
            fail_with=ProviderError(message="timeout reached", code="TIMEOUT", retryable=True),
        )
        router, ledger = _make_router(tmp_path, provider=provider)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert ex.metadata["outcome"] == "timeout"

    def test_server_error_exchange_outcome(self, tmp_path: Path) -> None:
        provider = MockProvider(
            fail_after=0,
            fail_with=ProviderError(message="server down", code="SERVER_ERROR", retryable=False),
        )
        router, ledger = _make_router(tmp_path, provider=provider)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert ex.metadata["outcome"] == "error"

    def test_error_exchange_has_latency(self, tmp_path: Path) -> None:
        provider = MockProvider(
            fail_after=0,
            fail_with=ProviderError(message="slow fail", code="SERVER_ERROR", retryable=False),
            latency_ms=5,
        )
        router, ledger = _make_router(tmp_path, provider=provider)

        router.route(_default_request())

        ex = _first_exchange(ledger)
        assert ex.metadata["latency_ms"] >= 0

    # Rejection tests (20-22)

    def test_rejection_is_lightweight(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path, dev_mode=False)

        router.route(_default_request(auth_token=None))

        rej = ledger.read_by_event_type("PROMPT_REJECTED")
        assert len(rej) == 1
        assert set(rej[0].metadata.keys()) == {
            "agent_id",
            "session_id",
            "contract_id",
            "error_code",
            "error_message",
        }

    def test_rejection_no_prompt_text(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path, dev_mode=False)

        router.route(_default_request(auth_token=None))

        rej = ledger.read_by_event_type("PROMPT_REJECTED")
        assert "prompt" not in rej[0].metadata

    def test_rejection_no_dispatch_marker(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path, dev_mode=False)

        response = router.route(_default_request(auth_token=None))

        assert response.dispatch_entry_id == ""
        assert len(ledger.read_by_event_type("DISPATCH")) == 0

    # Backward compatibility tests (23-28)

    def test_valid_request_round_trip(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        response = router.route(_default_request())

        assert response.outcome == RouteOutcome.SUCCESS
        assert response.content == "Mock response"
        assert response.input_tokens == 100
        assert response.output_tokens == 50

    def test_circuit_breaker_opens(self, tmp_path: Path) -> None:
        provider = MockProvider(
            fail_after=0,
            fail_with=ProviderError(message="Server error", code="SERVER_ERROR", retryable=False),
        )
        config = RouterConfig(
            default_provider="mock",
            default_model="mock-model-1",
            default_timeout_ms=5000,
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout_ms=60000,
                half_open_max=1,
            ),
            max_retries=0,
        )
        router, ledger = _make_router(tmp_path, provider=provider, config=config)

        for _ in range(3):
            resp = router.route(_default_request())
            assert resp.outcome in (RouteOutcome.ERROR, RouteOutcome.TIMEOUT)

        call_count_before = provider.call_count
        resp = router.route(_default_request())
        assert resp.outcome == RouteOutcome.REJECTED
        assert resp.error_code == "CIRCUIT_OPEN"
        assert provider.call_count == call_count_before

    def test_circuit_breaker_recovery(self, tmp_path: Path) -> None:
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=2, recovery_timeout_ms=50, half_open_max=1)
        )

        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.allow_request() is False

        time.sleep(0.06)

        assert cb.allow_request() is True
        assert cb.state == "HALF_OPEN"

        cb.record_success()
        assert cb.state == "CLOSED"

    def test_budget_exhausted(self, tmp_path: Path) -> None:
        ledger = _make_ledger(tmp_path)
        budgeter = TokenBudgeter(ledger_client=ledger, config=_default_budget_config())

        scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
        )
        budgeter.allocate(scope, BudgetAllocation(token_limit=10))

        provider = MockProvider()
        router = PromptRouter(
            ledger_client=ledger,
            budgeter=budgeter,
            config=_default_router_config(),
            dev_mode=True,
        )
        router.register_provider("mock", provider)

        response = router.route(_default_request(max_tokens=5000))

        assert response.outcome == RouteOutcome.REJECTED
        assert response.error_code == "BUDGET_EXHAUSTED"
        assert provider.call_count == 0

    def test_output_validation_failure(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        response = router.route(
            _default_request(output_schema={"type": "object", "required": ["answer"]})
        )

        assert response.outcome == RouteOutcome.SUCCESS
        assert response.output_valid is False
        assert len(response.output_validation_errors) > 0

    def test_dev_mode_bypasses_auth(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path, dev_mode=True)

        response = router.route(_default_request(auth_token=None))

        assert response.outcome == RouteOutcome.SUCCESS

    # Response dataclass tests (29-30)

    def test_response_has_exchange_entry_id(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        response = router.route(_default_request())

        assert re.match(r"^LED-[a-f0-9]{8}$", response.exchange_entry_id)

    def test_response_has_dispatch_entry_id(self, tmp_path: Path) -> None:
        router, ledger = _make_router(tmp_path)

        success = router.route(_default_request())
        assert re.match(r"^LED-[a-f0-9]{8}$", success.dispatch_entry_id)

        rejection = _make_router(tmp_path / "rej", dev_mode=False)[0].route(
            _default_request(auth_token=None)
        )
        assert rejection.dispatch_entry_id == ""
