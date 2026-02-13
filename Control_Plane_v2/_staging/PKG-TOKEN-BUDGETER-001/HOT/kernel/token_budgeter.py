"""Token budgeter — hierarchical budget management with rate limiting.

Manages token budgets across session → work order → agent hierarchy.
All state changes are logged to the ledger for auditability and cold-start reconstruction.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class BudgetDenialReason(str, Enum):
    """Reasons a budget check can be denied."""

    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    HIERARCHY_EXCEEDED = "HIERARCHY_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    TURN_LIMIT = "TURN_LIMIT"
    NOT_ALLOCATED = "NOT_ALLOCATED"


@dataclass
class BudgetScope:
    """Identifies the scope for a budget operation."""

    session_id: str
    work_order_id: Optional[str] = None
    agent_id: Optional[str] = None
    requested_tokens: int = 0
    model_id: Optional[str] = None

    @property
    def scope_key(self) -> str:
        """Canonical scope key for internal tracking."""
        parts = [self.session_id]
        if self.work_order_id:
            parts.append(self.work_order_id)
        if self.agent_id:
            parts.append(self.agent_id)
        return "/".join(parts)

    @property
    def parent_key(self) -> Optional[str]:
        """Parent scope key (agent→WO, WO→session, session→None)."""
        if self.agent_id and self.work_order_id:
            return f"{self.session_id}/{self.work_order_id}"
        if self.work_order_id:
            return self.session_id
        return None


@dataclass
class TokenUsage:
    """Token consumption from a single LLM call."""

    input_tokens: int
    output_tokens: int
    model_id: str

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class BudgetAllocation:
    """Budget allocation parameters."""

    token_limit: int
    turn_limit: Optional[int] = None
    timeout_seconds: Optional[int] = None


@dataclass
class BudgetCheckResult:
    """Result of a budget check (read-only)."""

    allowed: bool
    remaining: int
    reason: Optional[BudgetDenialReason] = None
    retry_after_ms: Optional[int] = None
    cost_estimate: Optional[float] = None
    warning: Optional[str] = None


@dataclass
class DebitResult:
    """Result of a budget debit (write)."""

    success: bool
    remaining: int
    total_consumed: int
    cost_incurred: float
    ledger_entry_id: str


@dataclass
class BudgetStatus:
    """Current status of a budget scope."""

    scope_key: str
    allocated: int
    consumed_input: int
    consumed_output: int
    consumed_total: int
    remaining: int
    request_count: int
    cost_estimate: float
    turn_limit: Optional[int]
    turns_used: int
    last_request_at: Optional[str]


@dataclass
class SessionSummary:
    """Aggregated summary for a session."""

    session_id: str
    total_input: int
    total_output: int
    total_consumed: int
    total_cost: float
    work_orders: list[dict[str, Any]]


@dataclass
class BudgetConfig:
    """Budget configuration (loaded from schema or constructed directly)."""

    session_token_limit: int = 100000
    wo_token_limit: int = 50000
    agent_token_limit: int = 10000
    wo_turn_limit: int = 20
    wo_timeout_seconds: int = 3600
    pricing: dict[str, dict[str, float]] = field(default_factory=dict)
    enforcement_hard_limit: bool = True
    enforcement_warn_threshold: float = 0.8

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BudgetConfig:
        """Create from config dict (matching schema)."""
        defaults = data.get("defaults", {})
        enforcement = data.get("enforcement", {})
        return cls(
            session_token_limit=defaults.get("session_token_limit", 100000),
            wo_token_limit=defaults.get("wo_token_limit", 50000),
            agent_token_limit=defaults.get("agent_token_limit", 10000),
            wo_turn_limit=defaults.get("wo_turn_limit", 20),
            wo_timeout_seconds=defaults.get("wo_timeout_seconds", 3600),
            pricing=data.get("pricing", {}),
            enforcement_hard_limit=enforcement.get("hard_limit", True),
            enforcement_warn_threshold=enforcement.get("warn_threshold", 0.8),
        )


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    requests_per_minute: int = 60
    tokens_per_minute: int = 1000000
    burst_allowance: float = 1.0
    cooldown_ms: int = 0
    window_seconds: int = 60


@dataclass
class _ScopeState:
    """Internal mutable state for a budget scope."""

    allocated: int = 0
    consumed_input: int = 0
    consumed_output: int = 0
    request_count: int = 0
    turn_limit: Optional[int] = None
    timeout_seconds: Optional[int] = None
    request_timestamps: list[float] = field(default_factory=list)
    last_request_at: Optional[str] = None

    @property
    def consumed_total(self) -> int:
        return self.consumed_input + self.consumed_output

    @property
    def remaining(self) -> int:
        return max(0, self.allocated - self.consumed_total)


class TokenBudgeter:
    """Hierarchical token budget manager with rate limiting and ledger integration."""

    def __init__(
        self,
        ledger_client: Any,
        config: BudgetConfig,
        rate_limit_config: Optional[RateLimitConfig] = None,
    ):
        self._ledger = ledger_client
        self._config = config
        self._rate_config = rate_limit_config
        self._scopes: dict[str, _ScopeState] = {}

    @classmethod
    def from_config_file(cls, path: Path, ledger_client: Any) -> TokenBudgeter:
        """Create budgeter from a JSON config file."""
        with open(path) as f:
            data = json.load(f)
        config = BudgetConfig.from_dict(data)
        rate_data = data.get("rate_limits")
        rate_config = None
        if rate_data:
            rate_config = RateLimitConfig(
                requests_per_minute=rate_data.get("requests_per_minute", 60),
                tokens_per_minute=rate_data.get("tokens_per_minute", 1000000),
                burst_allowance=rate_data.get("burst_allowance", 1.0),
                cooldown_ms=rate_data.get("cooldown_ms", 0),
                window_seconds=rate_data.get("window_seconds", 60),
            )
        return cls(ledger_client=ledger_client, config=config, rate_limit_config=rate_config)

    @classmethod
    def from_ledger(cls, ledger_client: Any, config: BudgetConfig) -> TokenBudgeter:
        """Reconstruct budgeter state from ledger entries (cold-start)."""
        budgeter = cls(ledger_client=ledger_client, config=config)

        # Replay BUDGET_ALLOCATE and BUDGET_DEBIT entries
        all_entries = ledger_client.read_all()
        budget_entries = [
            e for e in all_entries if e.event_type in ("BUDGET_ALLOCATE", "BUDGET_DEBIT")
        ]
        # Sort by timestamp for correct replay order
        budget_entries.sort(key=lambda e: e.timestamp)

        for entry in budget_entries:
            meta = entry.metadata
            scope_key = meta.get("scope_key", "")

            if entry.event_type == "BUDGET_ALLOCATE":
                state = _ScopeState(
                    allocated=meta.get("token_limit", 0),
                    turn_limit=meta.get("turn_limit"),
                    timeout_seconds=meta.get("timeout_seconds"),
                )
                budgeter._scopes[scope_key] = state

            elif entry.event_type == "BUDGET_DEBIT":
                state = budgeter._scopes.get(scope_key)
                if state:
                    state.consumed_input += meta.get("input_tokens", 0)
                    state.consumed_output += meta.get("output_tokens", 0)
                    state.request_count += 1
                    state.last_request_at = entry.timestamp
                # Also debit parent scopes
                parent_key = meta.get("parent_scope_key")
                if parent_key and parent_key in budgeter._scopes:
                    parent = budgeter._scopes[parent_key]
                    parent.consumed_input += meta.get("input_tokens", 0)
                    parent.consumed_output += meta.get("output_tokens", 0)
                    parent.request_count += 1
                    parent.last_request_at = entry.timestamp

        return budgeter

    def allocate(self, scope: BudgetScope, allocation: BudgetAllocation) -> str:
        """Allocate a budget for the given scope. Returns ledger entry ID."""
        from ledger_client import LedgerEntry

        state = _ScopeState(
            allocated=allocation.token_limit,
            turn_limit=allocation.turn_limit,
            timeout_seconds=allocation.timeout_seconds,
        )
        self._scopes[scope.scope_key] = state

        entry = LedgerEntry(
            event_type="BUDGET_ALLOCATE",
            submission_id=scope.scope_key,
            decision="ALLOCATED",
            reason=f"Budget allocated: {allocation.token_limit} tokens",
            metadata={
                "scope_key": scope.scope_key,
                "scope_session_id": scope.session_id,
                "scope_work_order_id": scope.work_order_id,
                "scope_agent_id": scope.agent_id,
                "token_limit": allocation.token_limit,
                "turn_limit": allocation.turn_limit,
                "timeout_seconds": allocation.timeout_seconds,
            },
        )
        return self._ledger.write(entry)

    def _resolve_scope(self, scope: BudgetScope) -> tuple[str, Optional[_ScopeState]]:
        """Find the nearest allocated scope (exact or parent fallback)."""
        key = scope.scope_key
        state = self._scopes.get(key)
        if state is not None:
            return key, state
        # Walk up to parent scopes
        parent_key = scope.parent_key
        while parent_key:
            state = self._scopes.get(parent_key)
            if state is not None:
                return parent_key, state
            parts = parent_key.split("/")
            parent_key = "/".join(parts[:-1]) if len(parts) > 1 else None
        return key, None

    def check(self, scope: BudgetScope) -> BudgetCheckResult:
        """Check if a request is within budget (read-only)."""
        resolved_key, state = self._resolve_scope(scope)
        if state is None:
            return BudgetCheckResult(
                allowed=False,
                remaining=0,
                reason=BudgetDenialReason.NOT_ALLOCATED,
            )

        # Rate limit check
        if self._rate_config:
            rate_result = self._check_rate_limit(scope)
            if rate_result is not None:
                return rate_result

        # Turn limit check
        if state.turn_limit is not None and state.request_count >= state.turn_limit:
            return BudgetCheckResult(
                allowed=False,
                remaining=state.remaining,
                reason=BudgetDenialReason.TURN_LIMIT,
            )

        # Budget exhaustion check
        requested = scope.requested_tokens
        if requested > 0 and requested > state.remaining:
            return BudgetCheckResult(
                allowed=False,
                remaining=state.remaining,
                reason=BudgetDenialReason.BUDGET_EXHAUSTED,
            )

        # Hierarchy check — walk up to parent scopes
        hierarchy_result = self._check_hierarchy(scope)
        if hierarchy_result is not None:
            return hierarchy_result

        # Warning check
        warning = None
        if state.allocated > 0:
            usage_ratio = state.consumed_total / state.allocated
            if usage_ratio >= self._config.enforcement_warn_threshold:
                warning = f"Budget usage at {usage_ratio:.0%}"

        # Cost estimate
        cost_estimate = None
        if scope.model_id and requested > 0:
            cost_estimate = self.estimate_cost(scope.model_id, requested, 0)

        return BudgetCheckResult(
            allowed=True,
            remaining=state.remaining,
            cost_estimate=cost_estimate,
            warning=warning,
        )

    def debit(self, scope: BudgetScope, usage: TokenUsage) -> DebitResult:
        """Debit token usage from the budget. Returns DebitResult."""
        from ledger_client import LedgerEntry

        resolved_key, state = self._resolve_scope(scope)
        if state is None:
            return DebitResult(
                success=False,
                remaining=0,
                total_consumed=0,
                cost_incurred=0.0,
                ledger_entry_id="",
            )

        # Record timestamp for rate limiting
        now = time.time()
        state.request_timestamps.append(now)
        state.consumed_input += usage.input_tokens
        state.consumed_output += usage.output_tokens
        state.request_count += 1

        timestamp_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
        state.last_request_at = timestamp_iso

        # Debit parent scopes (walk up from the resolved key, not the original)
        resolved_parts = resolved_key.split("/")
        parent_key = "/".join(resolved_parts[:-1]) if len(resolved_parts) > 1 else None
        parent_scope_key = None
        while parent_key:
            parent_state = self._scopes.get(parent_key)
            if parent_state:
                parent_state.consumed_input += usage.input_tokens
                parent_state.consumed_output += usage.output_tokens
                parent_state.request_count += 1
                parent_state.request_timestamps.append(now)
                parent_state.last_request_at = timestamp_iso
                if parent_scope_key is None:
                    parent_scope_key = parent_key
            # Walk up
            parts = parent_key.split("/")
            parent_key = "/".join(parts[:-1]) if len(parts) > 1 else None

        cost = self.estimate_cost(usage.model_id, usage.input_tokens, usage.output_tokens)

        entry = LedgerEntry(
            event_type="BUDGET_DEBIT",
            submission_id=resolved_key,
            decision="DEBITED",
            reason=f"Debit: {usage.total} tokens ({usage.input_tokens}in/{usage.output_tokens}out)",
            metadata={
                "scope_key": resolved_key,
                "parent_scope_key": parent_scope_key,
                "scope_session_id": scope.session_id,
                "scope_work_order_id": scope.work_order_id,
                "scope_agent_id": scope.agent_id,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total,
                "model_id": usage.model_id,
                "cost_incurred": cost,
                "remaining": state.remaining,
            },
        )
        entry_id = self._ledger.write(entry)

        return DebitResult(
            success=True,
            remaining=state.remaining,
            total_consumed=state.consumed_total,
            cost_incurred=cost,
            ledger_entry_id=entry_id,
        )

    def get_status(self, scope: BudgetScope) -> BudgetStatus:
        """Get current status of a budget scope."""
        state = self._scopes.get(scope.scope_key)
        if state is None:
            return BudgetStatus(
                scope_key=scope.scope_key,
                allocated=0,
                consumed_input=0,
                consumed_output=0,
                consumed_total=0,
                remaining=0,
                request_count=0,
                cost_estimate=0.0,
                turn_limit=None,
                turns_used=0,
                last_request_at=None,
            )

        return BudgetStatus(
            scope_key=scope.scope_key,
            allocated=state.allocated,
            consumed_input=state.consumed_input,
            consumed_output=state.consumed_output,
            consumed_total=state.consumed_total,
            remaining=state.remaining,
            request_count=state.request_count,
            cost_estimate=0.0,
            turn_limit=state.turn_limit,
            turns_used=state.request_count,
            last_request_at=state.last_request_at,
        )

    def get_session_summary(self, session_id: str) -> SessionSummary:
        """Get aggregated summary for a session across all work orders."""
        session_key = session_id
        wo_summaries = []
        total_input = 0
        total_output = 0
        total_cost = 0.0

        for key, state in self._scopes.items():
            if not key.startswith(session_id):
                continue
            # Skip the session-level scope itself
            parts = key.split("/")
            if len(parts) < 2:
                continue
            wo_id = parts[1]
            wo_input = state.consumed_input
            wo_output = state.consumed_output
            wo_summaries.append(
                {
                    "work_order_id": wo_id,
                    "consumed_input": wo_input,
                    "consumed_output": wo_output,
                    "consumed_total": state.consumed_total,
                    "request_count": state.request_count,
                }
            )
            total_input += wo_input
            total_output += wo_output

        return SessionSummary(
            session_id=session_id,
            total_input=total_input,
            total_output=total_output,
            total_consumed=total_input + total_output,
            total_cost=total_cost,
            work_orders=wo_summaries,
        )

    def estimate_cost(
        self, model_id: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Estimate cost for given token counts."""
        pricing = self._config.pricing.get(model_id)
        if not pricing:
            return 0.0
        input_cost = (input_tokens / 1000.0) * pricing.get("input_per_1k", 0)
        output_cost = (output_tokens / 1000.0) * pricing.get("output_per_1k", 0)
        return input_cost + output_cost

    def _check_rate_limit(self, scope: BudgetScope) -> Optional[BudgetCheckResult]:
        """Check rate limits. Returns BudgetCheckResult if denied, None if OK."""
        if not self._rate_config:
            return None

        state = self._scopes.get(scope.scope_key)
        if state is None:
            return None

        now = time.time()
        window = self._rate_config.window_seconds
        burst_limit = int(
            self._rate_config.requests_per_minute * self._rate_config.burst_allowance
        )

        # Clean old timestamps outside window
        cutoff = now - window
        state.request_timestamps = [t for t in state.request_timestamps if t > cutoff]

        if len(state.request_timestamps) >= burst_limit:
            # Calculate retry_after from oldest timestamp in window
            oldest = min(state.request_timestamps)
            retry_after_ms = int((oldest + window - now) * 1000)
            retry_after_ms = max(retry_after_ms, self._rate_config.cooldown_ms)
            return BudgetCheckResult(
                allowed=False,
                remaining=state.remaining,
                reason=BudgetDenialReason.RATE_LIMITED,
                retry_after_ms=retry_after_ms,
            )

        return None

    def _check_hierarchy(self, scope: BudgetScope) -> Optional[BudgetCheckResult]:
        """Check hierarchy constraints. Returns BudgetCheckResult if denied, None if OK."""
        requested = scope.requested_tokens
        if requested <= 0:
            return None

        parent_key = scope.parent_key
        while parent_key:
            parent_state = self._scopes.get(parent_key)
            if parent_state and requested > parent_state.remaining:
                return BudgetCheckResult(
                    allowed=False,
                    remaining=parent_state.remaining,
                    reason=BudgetDenialReason.HIERARCHY_EXCEEDED,
                )
            parts = parent_key.split("/")
            parent_key = "/".join(parts[:-1]) if len(parts) > 1 else None

        return None
