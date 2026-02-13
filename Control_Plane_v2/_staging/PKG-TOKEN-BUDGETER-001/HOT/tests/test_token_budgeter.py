"""Tests for token budgeter — hierarchical budget management with rate limiting.

DTT: tests written FIRST, implementation follows.
All tests use tmp_path ledger — no shared state.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add kernel to path for imports
_staging = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_staging / "PKG-KERNEL-001" / "HOT" / "kernel"))
sys.path.insert(0, str(_staging / "PKG-TOKEN-BUDGETER-001" / "HOT" / "kernel"))

from ledger_client import LedgerClient, LedgerEntry  # noqa: E402
from token_budgeter import (  # noqa: E402
    BudgetAllocation,
    BudgetCheckResult,
    BudgetConfig,
    BudgetDenialReason,
    BudgetScope,
    DebitResult,
    RateLimitConfig,
    TokenBudgeter,
    TokenUsage,
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


def _default_config() -> BudgetConfig:
    """Default budget config for tests."""
    return BudgetConfig(
        session_token_limit=100000,
        wo_token_limit=50000,
        agent_token_limit=10000,
        wo_turn_limit=20,
        wo_timeout_seconds=3600,
        pricing={
            "claude-opus-4-6": {"input_per_1k": 0.015, "output_per_1k": 0.075},
            "claude-sonnet-4-5": {"input_per_1k": 0.003, "output_per_1k": 0.015},
        },
        enforcement_hard_limit=True,
        enforcement_warn_threshold=0.8,
    )


def _rate_config(rpm: int = 10, burst: float = 1.5) -> RateLimitConfig:
    """Rate limit config for tests."""
    return RateLimitConfig(
        requests_per_minute=rpm,
        tokens_per_minute=1000000,
        burst_allowance=burst,
        cooldown_ms=100,
        window_seconds=60,
    )


class TestTokenBudgeter:
    """Token budgeter tests."""

    def test_allocate_budget(self, tmp_path: Path) -> None:
        """Allocate → status shows correct allocated/remaining, BUDGET_ALLOCATE in ledger."""
        ledger = _make_ledger(tmp_path)
        budgeter = TokenBudgeter(ledger_client=ledger, config=_default_config())

        scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
        )
        allocation = BudgetAllocation(token_limit=50000, turn_limit=10)

        entry_id = budgeter.allocate(scope, allocation)

        # Verify entry ID format
        assert entry_id.startswith("LED-"), f"Expected LED- prefix, got {entry_id}"

        # Verify status
        status = budgeter.get_status(scope)
        assert status.allocated == 50000
        assert status.remaining == 50000
        assert status.consumed_total == 0
        assert status.turn_limit == 10

        # Verify ledger has BUDGET_ALLOCATE
        entries = ledger.read_by_event_type("BUDGET_ALLOCATE")
        assert len(entries) == 1
        assert entries[0].metadata["scope_session_id"] == "SES-TEST0001"
        assert entries[0].metadata["token_limit"] == 50000

    def test_check_within_budget(self, tmp_path: Path) -> None:
        """check(1000 requested, 50000 allocated) → allowed=True."""
        ledger = _make_ledger(tmp_path)
        budgeter = TokenBudgeter(ledger_client=ledger, config=_default_config())

        scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
            requested_tokens=1000,
        )
        budgeter.allocate(scope, BudgetAllocation(token_limit=50000))

        result = budgeter.check(scope)
        assert result.allowed is True
        assert result.remaining == 50000

    def test_check_over_budget(self, tmp_path: Path) -> None:
        """check(2000 requested, 1000 allocated) → allowed=False, BUDGET_EXHAUSTED."""
        ledger = _make_ledger(tmp_path)
        budgeter = TokenBudgeter(ledger_client=ledger, config=_default_config())

        scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
            requested_tokens=2000,
        )
        budgeter.allocate(scope, BudgetAllocation(token_limit=1000))

        result = budgeter.check(scope)
        assert result.allowed is False
        assert result.reason == BudgetDenialReason.BUDGET_EXHAUSTED

    def test_debit_updates_remaining(self, tmp_path: Path) -> None:
        """debit(100+200) → remaining=49700, request_count=1, BUDGET_DEBIT in ledger."""
        ledger = _make_ledger(tmp_path)
        budgeter = TokenBudgeter(ledger_client=ledger, config=_default_config())

        scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
        )
        budgeter.allocate(scope, BudgetAllocation(token_limit=50000))

        usage = TokenUsage(input_tokens=100, output_tokens=200, model_id="claude-opus-4-6")
        result = budgeter.debit(scope, usage)

        assert result.success is True
        assert result.remaining == 49700
        assert result.total_consumed == 300
        assert result.ledger_entry_id.startswith("LED-")

        # Verify status
        status = budgeter.get_status(scope)
        assert status.remaining == 49700
        assert status.request_count == 1
        assert status.consumed_input == 100
        assert status.consumed_output == 200

        # Verify ledger
        debits = ledger.read_by_event_type("BUDGET_DEBIT")
        assert len(debits) == 1

    def test_hierarchy_enforcement(self, tmp_path: Path) -> None:
        """WO can't exceed session remaining → HIERARCHY_EXCEEDED."""
        ledger = _make_ledger(tmp_path)
        budgeter = TokenBudgeter(ledger_client=ledger, config=_default_config())

        # Allocate session with 10000
        session_scope = BudgetScope(
            session_id="SES-TEST0001",
        )
        budgeter.allocate(session_scope, BudgetAllocation(token_limit=10000))

        # Allocate WO with 50000 (more than session)
        wo_scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
        )
        budgeter.allocate(wo_scope, BudgetAllocation(token_limit=50000))

        # Consume most of session budget via WO
        usage = TokenUsage(input_tokens=4000, output_tokens=5500, model_id="claude-opus-4-6")
        budgeter.debit(wo_scope, usage)

        # Now request more than session remaining (500 left)
        check_scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
            requested_tokens=1000,
        )
        result = budgeter.check(check_scope)
        assert result.allowed is False
        assert result.reason == BudgetDenialReason.HIERARCHY_EXCEEDED

    def test_rate_limiting(self, tmp_path: Path) -> None:
        """RPM+1 rapid requests → RATE_LIMITED with retry_after_ms."""
        ledger = _make_ledger(tmp_path)
        config = _default_config()
        rate_config = _rate_config(rpm=5, burst=1.0)  # 5 RPM, no burst
        budgeter = TokenBudgeter(
            ledger_client=ledger, config=config, rate_limit_config=rate_config
        )

        scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
            requested_tokens=100,
        )
        budgeter.allocate(scope, BudgetAllocation(token_limit=50000))

        # Make 5 requests (should all pass)
        for _ in range(5):
            usage = TokenUsage(input_tokens=10, output_tokens=10, model_id="claude-opus-4-6")
            budgeter.debit(scope, usage)

        # 6th request should be rate limited
        result = budgeter.check(scope)
        assert result.allowed is False
        assert result.reason == BudgetDenialReason.RATE_LIMITED
        assert result.retry_after_ms is not None
        assert result.retry_after_ms > 0

    def test_burst_allowance(self, tmp_path: Path) -> None:
        """14 rapid requests (under 10*1.5=15 burst) pass; 16th fails."""
        ledger = _make_ledger(tmp_path)
        config = _default_config()
        rate_config = _rate_config(rpm=10, burst=1.5)  # 10 RPM * 1.5 = 15 burst
        budgeter = TokenBudgeter(
            ledger_client=ledger, config=config, rate_limit_config=rate_config
        )

        scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
            requested_tokens=100,
        )
        budgeter.allocate(scope, BudgetAllocation(token_limit=500000))

        # Make 14 requests (under burst limit of 15)
        for i in range(14):
            usage = TokenUsage(input_tokens=10, output_tokens=10, model_id="claude-opus-4-6")
            result = budgeter.debit(scope, usage)
            assert result.success is True, f"Request {i+1} should pass under burst"

        # 15th should still pass (== burst limit)
        result = budgeter.debit(
            scope, TokenUsage(input_tokens=10, output_tokens=10, model_id="claude-opus-4-6")
        )
        assert result.success is True, "15th request should pass at burst limit"

        # 16th should fail
        check = budgeter.check(scope)
        assert check.allowed is False
        assert check.reason == BudgetDenialReason.RATE_LIMITED

    def test_cost_calculation(self, tmp_path: Path) -> None:
        """1000 input + 500 output @ opus pricing → $0.0525."""
        ledger = _make_ledger(tmp_path)
        budgeter = TokenBudgeter(ledger_client=ledger, config=_default_config())

        # opus: input $0.015/1k, output $0.075/1k
        # 1000 input = $0.015, 500 output = $0.0375, total = $0.0525
        cost = budgeter.estimate_cost("claude-opus-4-6", input_tokens=1000, output_tokens=500)
        assert abs(cost - 0.0525) < 1e-10

    def test_session_summary(self, tmp_path: Path) -> None:
        """Debit from 2 WOs → summary aggregates correctly."""
        ledger = _make_ledger(tmp_path)
        budgeter = TokenBudgeter(ledger_client=ledger, config=_default_config())

        session_id = "SES-TEST0001"

        # Allocate session
        session_scope = BudgetScope(session_id=session_id)
        budgeter.allocate(session_scope, BudgetAllocation(token_limit=100000))

        # Allocate and debit WO-1
        wo1_scope = BudgetScope(session_id=session_id, work_order_id="WO-20260210-001")
        budgeter.allocate(wo1_scope, BudgetAllocation(token_limit=50000))
        budgeter.debit(
            wo1_scope,
            TokenUsage(input_tokens=1000, output_tokens=500, model_id="claude-opus-4-6"),
        )

        # Allocate and debit WO-2
        wo2_scope = BudgetScope(session_id=session_id, work_order_id="WO-20260210-002")
        budgeter.allocate(wo2_scope, BudgetAllocation(token_limit=50000))
        budgeter.debit(
            wo2_scope,
            TokenUsage(input_tokens=2000, output_tokens=1000, model_id="claude-opus-4-6"),
        )

        summary = budgeter.get_session_summary(session_id)
        assert summary.session_id == session_id
        assert summary.total_input == 3000
        assert summary.total_output == 1500
        assert summary.total_consumed == 4500
        assert len(summary.work_orders) == 2

    def test_budget_from_ledger(self, tmp_path: Path) -> None:
        """Destroy + reconstruct from ledger → same state."""
        ledger = _make_ledger(tmp_path)
        config = _default_config()
        budgeter = TokenBudgeter(ledger_client=ledger, config=config)

        scope = BudgetScope(
            session_id="SES-TEST0001",
            work_order_id="WO-20260210-001",
        )
        budgeter.allocate(scope, BudgetAllocation(token_limit=50000, turn_limit=10))
        budgeter.debit(
            scope,
            TokenUsage(input_tokens=500, output_tokens=250, model_id="claude-opus-4-6"),
        )
        budgeter.debit(
            scope,
            TokenUsage(input_tokens=300, output_tokens=150, model_id="claude-opus-4-6"),
        )

        original_status = budgeter.get_status(scope)

        # Reconstruct from ledger
        reconstructed = TokenBudgeter.from_ledger(ledger_client=ledger, config=config)
        reconstructed_status = reconstructed.get_status(scope)

        assert reconstructed_status.allocated == original_status.allocated
        assert reconstructed_status.consumed_total == original_status.consumed_total
        assert reconstructed_status.remaining == original_status.remaining
        assert reconstructed_status.request_count == original_status.request_count
        assert reconstructed_status.turn_limit == original_status.turn_limit
