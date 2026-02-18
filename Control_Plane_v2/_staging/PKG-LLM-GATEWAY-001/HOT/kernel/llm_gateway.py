"""LLM Gateway — single-shot exchange recording.

Dumb router: validate → auth → budget → dispatch marker → send →
exchange record → debit → validate output → return.
Every path (success or error) logs to the ledger. No silent failures.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class RouteOutcome(str, Enum):
    """Outcome of a route() call."""

    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class PromptRequest:
    """Request to route a prompt to an LLM provider."""

    prompt: str
    prompt_pack_id: str
    contract_id: str
    agent_id: str
    agent_class: str
    framework_id: str
    package_id: str
    work_order_id: str
    session_id: str
    tier: str
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.0
    structured_output: Optional[dict[str, Any]] = None
    input_schema: Optional[dict[str, Any]] = None
    output_schema: Optional[dict[str, Any]] = None
    tools: Optional[list[dict[str, Any]]] = None
    template_variables: Optional[dict[str, Any]] = None
    domain_tags: list[str] = field(default_factory=list)
    auth_token: Optional[str] = None


@dataclass
class PromptResponse:
    """Response from a route() call."""

    content: str
    outcome: RouteOutcome
    input_tokens: int
    output_tokens: int
    model_id: str
    provider_id: str
    latency_ms: float
    timestamp: str
    exchange_entry_id: str
    dispatch_entry_id: str = ""
    output_valid: Optional[bool] = None
    output_validation_errors: list[str] = field(default_factory=list)
    context_hash: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    cost_incurred: float = 0.0
    budget_remaining: Optional[int] = None
    finish_reason: str = "stop"
    content_blocks: Optional[tuple] = None


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    failure_threshold: int = 3
    recovery_timeout_ms: int = 30000
    half_open_max: int = 1


@dataclass
class RouterConfig:
    """Router configuration."""

    default_provider: str = "mock"
    default_model: str = "mock-model-1"
    default_timeout_ms: int = 30000
    circuit_breaker: Optional[CircuitBreakerConfig] = None
    max_retries: int = 0
    domain_tag_routes: dict = field(default_factory=dict)


class CircuitBreaker:
    """Circuit breaker for provider resilience."""

    def __init__(self, config: CircuitBreakerConfig):
        self._config = config
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._state: CircuitState = CircuitState.CLOSED
        self._half_open_count: int = 0

    @property
    def state(self) -> str:
        """Current circuit state, with automatic OPEN→HALF_OPEN transition."""
        if self._state == CircuitState.OPEN:
            elapsed_ms = (time.time() - self._last_failure_time) * 1000
            if elapsed_ms >= self._config.recovery_timeout_ms:
                self._state = CircuitState.HALF_OPEN
                self._half_open_count = 0
        return self._state.value

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit."""
        current = self.state  # triggers OPEN→HALF_OPEN check
        if current == CircuitState.CLOSED.value:
            return True
        if current == CircuitState.HALF_OPEN.value:
            if self._half_open_count < self._config.half_open_max:
                self._half_open_count += 1
                return True
            return False
        return False  # OPEN

    def record_success(self) -> None:
        """Record a successful request."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._half_open_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._config.failure_threshold:
            self._state = CircuitState.OPEN
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN


class LLMGateway:
    """Single-shot prompt router with ledger logging."""

    def __init__(
        self,
        ledger_client: Any,
        budgeter: Any = None,
        config: Optional[RouterConfig] = None,
        auth_provider: Any = None,
        dev_mode: bool = False,
        budget_mode: str = "enforce",
    ):
        self._ledger = ledger_client
        self._budgeter = budgeter
        self._config = config or RouterConfig()
        self._auth_provider = auth_provider
        self._dev_mode = dev_mode
        self._budget_mode = str(budget_mode).lower()
        if self._budget_mode not in {"enforce", "warn", "off"}:
            self._budget_mode = "enforce"
        self._providers: dict[str, Any] = {}
        self._circuit_breaker = CircuitBreaker(
            self._config.circuit_breaker or CircuitBreakerConfig()
        )

    @classmethod
    def from_config_file(
        cls,
        path: Path,
        ledger_client: Any,
        budgeter: Any = None,
        dev_mode: bool = False,
    ) -> LLMGateway:
        """Create router from a JSON config file."""
        with open(path) as f:
            data = json.load(f)
        cb_data = data.get("circuit_breaker", {})
        cb_config = CircuitBreakerConfig(
            failure_threshold=cb_data.get("failure_threshold", 3),
            recovery_timeout_ms=cb_data.get("recovery_timeout_ms", 30000),
            half_open_max=cb_data.get("half_open_max", 1),
        )
        config = RouterConfig(
            default_provider=data["default_provider"],
            default_model=data["default_model"],
            default_timeout_ms=data["default_timeout_ms"],
            circuit_breaker=cb_config,
            domain_tag_routes=data.get("domain_tag_routes", {}),
        )
        return cls(
            ledger_client=ledger_client,
            budgeter=budgeter,
            config=config,
            dev_mode=dev_mode,
        )

    def register_provider(self, provider_id: str, provider: Any) -> None:
        """Register an LLM provider."""
        self._providers[provider_id] = provider

    def _resolve_domain_tags(self, tags: list) -> Optional[str]:
        """Resolve domain tags to a provider_id via the routing map.

        Returns the first matching provider_id from domain_tag_routes,
        or None if no tags match (falls through to default).
        """
        if not tags or not self._config.domain_tag_routes:
            return None
        for tag in tags:
            route = self._config.domain_tag_routes.get(tag)
            if route and isinstance(route, dict):
                pid = route.get("provider_id")
                if pid:
                    return pid
            elif route and isinstance(route, str):
                return route
        return None

    def route(self, request: PromptRequest) -> PromptResponse:
        """Route a prompt through the 10-step pipeline."""
        from hashing import sha256_string

        start_time = time.time()
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(start_time))

        model_id = request.model_id or self._config.default_model
        provider_id = (
            request.provider_id
            or self._resolve_domain_tags(request.domain_tags)
            or self._config.default_provider
        )
        timeout_ms = self._config.default_timeout_ms

        # Step 1: Validate input
        validation_error = self._validate_input(request)
        if validation_error:
            return self._reject(
                request, "INVALID_INPUT", validation_error, start_time, timestamp,
                model_id, provider_id,
            )

        # Step 2: Check auth
        if not self._dev_mode:
            auth_error = self._check_auth(request)
            if auth_error:
                return self._reject(
                    request, "AUTH_ERROR", auth_error, start_time, timestamp,
                    model_id, provider_id,
                )

        # Step 3: Check budget
        if self._budgeter and self._budget_mode != "off":
            budget_error = self._check_budget(request, model_id)
            if budget_error:
                return self._reject(
                    request, "BUDGET_EXHAUSTED", budget_error, start_time, timestamp,
                    model_id, provider_id,
                )

        # Step 4: Compute context hash
        context_hash = sha256_string(request.prompt)

        # Step 5: Check circuit breaker
        if not self._circuit_breaker.allow_request():
            return self._reject(
                request,
                "CIRCUIT_OPEN",
                "Circuit breaker is open",
                start_time,
                timestamp,
                model_id,
                provider_id,
            )

        # Step 6: Write pre-send dispatch marker
        dispatch_entry_id = self._write_dispatch_marker(request, model_id, provider_id)

        # Step 7: Dispatch to provider
        provider = self._providers.get(provider_id)
        if provider is None:
            self._circuit_breaker.record_failure()
            exchange_entry_id = self._write_exchange_error(
                request=request,
                dispatch_entry_id=dispatch_entry_id,
                error_code="PROVIDER_NOT_FOUND",
                error_message=f"Provider '{provider_id}' not registered",
                context_hash=context_hash,
                model_id=model_id,
                latency_ms=self._elapsed_ms(start_time),
            )
            return PromptResponse(
                content="",
                outcome=RouteOutcome.ERROR,
                input_tokens=0,
                output_tokens=0,
                model_id=model_id,
                provider_id=provider_id,
                latency_ms=self._elapsed_ms(start_time),
                timestamp=timestamp,
                exchange_entry_id=exchange_entry_id,
                dispatch_entry_id=dispatch_entry_id,
                context_hash=context_hash,
                error_code="PROVIDER_NOT_FOUND",
                error_message=f"Provider '{provider_id}' not registered",
            )

        try:
            from provider import ProviderError

            provider_response = provider.send(
                model_id=model_id,
                prompt=request.prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                timeout_ms=timeout_ms,
                structured_output=request.structured_output,
                tools=request.tools,
            )
        except Exception as e:
            self._circuit_breaker.record_failure()
            # Determine outcome based on error type
            error_code = "PROVIDER_ERROR"
            outcome = RouteOutcome.ERROR
            try:
                from provider import ProviderError as PE
                if isinstance(e, PE):
                    error_code = e.code
                    if e.code == "TIMEOUT":
                        outcome = RouteOutcome.TIMEOUT
            except ImportError:
                pass

            exchange_entry_id = self._write_exchange_error(
                request=request,
                dispatch_entry_id=dispatch_entry_id,
                error_code=error_code,
                error_message=str(e),
                context_hash=context_hash,
                model_id=model_id,
                latency_ms=self._elapsed_ms(start_time),
            )
            return PromptResponse(
                content="",
                outcome=outcome,
                input_tokens=0,
                output_tokens=0,
                model_id=model_id,
                provider_id=provider_id,
                latency_ms=self._elapsed_ms(start_time),
                timestamp=timestamp,
                exchange_entry_id=exchange_entry_id,
                dispatch_entry_id=dispatch_entry_id,
                context_hash=context_hash,
                error_code=error_code,
                error_message=str(e),
            )

        # Success path
        self._circuit_breaker.record_success()

        # Step 8: Write exchange record
        exchange_entry_id = self._write_exchange(
            request=request,
            dispatch_entry_id=dispatch_entry_id,
            provider_response=provider_response,
            context_hash=context_hash,
            model_id=model_id,
            latency_ms=self._elapsed_ms(start_time),
        )

        # Step 9: Debit budget
        cost_incurred = 0.0
        budget_remaining = None
        if self._budgeter:
            from token_budgeter import BudgetScope, TokenUsage

            scope = BudgetScope(
                session_id=request.session_id,
                work_order_id=request.work_order_id,
                agent_id=request.agent_id,
            )
            usage = TokenUsage(
                input_tokens=provider_response.input_tokens,
                output_tokens=provider_response.output_tokens,
                model_id=provider_response.model,
            )
            debit_result = self._budgeter.debit(scope, usage)
            cost_incurred = debit_result.cost_incurred
            budget_remaining = debit_result.remaining

        # Step 10: Validate output
        output_valid = None
        output_errors: list[str] = []
        if request.output_schema:
            output_valid, output_errors = self._validate_output(
                provider_response.content, request.output_schema
            )

        # Step 11: Return
        return PromptResponse(
            content=provider_response.content,
            outcome=RouteOutcome.SUCCESS,
            input_tokens=provider_response.input_tokens,
            output_tokens=provider_response.output_tokens,
            model_id=model_id,
            provider_id=provider_id,
            latency_ms=self._elapsed_ms(start_time),
            timestamp=timestamp,
            exchange_entry_id=exchange_entry_id,
            dispatch_entry_id=dispatch_entry_id,
            output_valid=output_valid,
            output_validation_errors=output_errors,
            context_hash=context_hash,
            cost_incurred=cost_incurred,
            budget_remaining=budget_remaining,
            finish_reason=getattr(provider_response, "finish_reason", "stop"),
            content_blocks=getattr(provider_response, "content_blocks", None),
        )

    # ── Internal pipeline steps ──

    def _validate_input(self, request: PromptRequest) -> Optional[str]:
        """Step 1: Validate the prompt request."""
        if not request.prompt or not request.prompt.strip():
            return "Prompt is empty"
        if not request.contract_id:
            return "contract_id is required"
        if not request.session_id:
            return "session_id is required"
        return None

    def _check_auth(self, request: PromptRequest) -> Optional[str]:
        """Step 2: Check authentication. Returns error string or None."""
        if not request.auth_token:
            return "Authentication required"
        return None

    def _check_budget(self, request: PromptRequest, model_id: str) -> Optional[str]:
        """Step 3: Check budget. Returns error string or None."""
        from token_budgeter import BudgetScope

        if self._budget_mode == "off":
            return None

        scope = BudgetScope(
            session_id=request.session_id,
            work_order_id=request.work_order_id,
            agent_id=request.agent_id,
            requested_tokens=request.max_tokens,
            model_id=model_id,
        )
        result = self._budgeter.check(scope)
        if not result.allowed:
            reason = f"Budget check failed: {result.reason}"
            if self._budget_mode == "enforce":
                return reason
            if self._budget_mode == "warn":
                self._write_budget_warning(request, reason, getattr(result, "remaining", None), model_id)
                return None
        return None

    def _write_budget_warning(
        self,
        request: PromptRequest,
        reason: str,
        remaining: Optional[int],
        model_id: str,
    ) -> str:
        from ledger_client import LedgerEntry

        entry = LedgerEntry(
            event_type="BUDGET_WARNING",
            submission_id=request.contract_id,
            decision="WARNING",
            reason=reason,
            metadata={
                "agent_id": request.agent_id,
                "session_id": request.session_id,
                "work_order_id": request.work_order_id,
                "contract_id": request.contract_id,
                "model_id": model_id,
                "requested_tokens": request.max_tokens,
                "remaining": remaining,
                "budget_mode": self._budget_mode,
            },
        )
        return self._ledger.write(entry)

    def _write_dispatch_marker(
        self,
        request: PromptRequest,
        model_id: str,
        provider_id: str,
    ) -> str:
        """Write lightweight DISPATCH marker to ledger."""
        from ledger_client import LedgerEntry

        entry = LedgerEntry(
            event_type="DISPATCH",
            submission_id=request.contract_id,
            decision="DISPATCHED",
            reason=f"Dispatching to {provider_id}/{model_id}",
            metadata={
                "contract_id": request.contract_id,
                "agent_id": request.agent_id,
                "session_id": request.session_id,
            },
        )
        return self._ledger.write(entry)

    def _write_exchange(
        self,
        request: PromptRequest,
        dispatch_entry_id: str,
        provider_response: Any,
        context_hash: str,
        model_id: str,
        latency_ms: float,
    ) -> str:
        """Write EXCHANGE record for successful round-trip."""
        from ledger_client import LedgerEntry

        # Tool-use observability
        tools_offered = len(request.tools) if request.tools else 0
        tool_use_in_response = getattr(provider_response, "finish_reason", "") == "tool_use"

        entry = LedgerEntry(
            event_type="EXCHANGE",
            submission_id=request.contract_id,
            decision="SUCCESS",
            reason="Exchange completed",
            metadata={
                # Identity
                "agent_id": request.agent_id,
                "session_id": request.session_id,
                "work_order_id": request.work_order_id,
                "tier": request.tier,
                "contract_id": request.contract_id,
                "framework_id": request.framework_id,
                # Content
                "prompt": request.prompt,
                "response": provider_response.content,
                "outcome": "success",
                # Cost
                "input_tokens": provider_response.input_tokens,
                "output_tokens": provider_response.output_tokens,
                # Context
                "context_hash": context_hash,
                # Correlation
                "dispatch_entry_id": dispatch_entry_id,
                # Provider detail
                "model_id": model_id,
                "finish_reason": provider_response.finish_reason,
                # Timing
                "latency_ms": latency_ms,
                # Tool observability
                "tools_offered": tools_offered,
                "tool_use_in_response": tool_use_in_response,
            },
        )
        return self._ledger.write(entry)

    def _write_exchange_error(
        self,
        request: PromptRequest,
        dispatch_entry_id: str,
        error_code: str,
        error_message: str,
        context_hash: str,
        model_id: str,
        latency_ms: float,
    ) -> str:
        """Write EXCHANGE record for failed round-trip."""
        from ledger_client import LedgerEntry

        outcome = "timeout" if error_code == "TIMEOUT" else "error"
        entry = LedgerEntry(
            event_type="EXCHANGE",
            submission_id=request.contract_id,
            decision="ERROR",
            reason=f"{error_code}: {error_message}",
            metadata={
                # Identity
                "agent_id": request.agent_id,
                "session_id": request.session_id,
                "work_order_id": request.work_order_id,
                "tier": request.tier,
                "contract_id": request.contract_id,
                "framework_id": request.framework_id,
                # Content
                "prompt": request.prompt,
                "response": "",
                "outcome": outcome,
                "error_code": error_code,
                "error_message": error_message,
                # Context
                "context_hash": context_hash,
                # Correlation
                "dispatch_entry_id": dispatch_entry_id,
                # Provider detail
                "model_id": model_id,
                # Timing
                "latency_ms": latency_ms,
            },
        )
        return self._ledger.write(entry)

    def _validate_output(
        self, content: str, schema: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Step 9: Validate output against schema. Returns (valid, errors)."""
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return False, [f"Response is not valid JSON: {content[:100]}"]

        errors = []
        # Basic schema validation (required fields)
        if schema.get("type") == "object" and "required" in schema:
            for req_field in schema["required"]:
                if req_field not in parsed:
                    errors.append(f"Missing required field: {req_field}")

        return (len(errors) == 0, errors)

    def _reject(
        self, request: PromptRequest, error_code: str, error_message: str,
        start_time: float, timestamp: str, model_id: str, provider_id: str,
    ) -> PromptResponse:
        """Create a rejection response and log to ledger."""
        from ledger_client import LedgerEntry

        entry = LedgerEntry(
            event_type="PROMPT_REJECTED",
            submission_id=request.contract_id,
            decision="REJECTED",
            reason=f"{error_code}: {error_message}",
            metadata={
                "agent_id": request.agent_id,
                "session_id": request.session_id,
                "contract_id": request.contract_id,
                "error_code": error_code,
                "error_message": error_message,
            },
        )
        entry_id = self._ledger.write(entry)

        return PromptResponse(
            content="",
            outcome=RouteOutcome.REJECTED,
            input_tokens=0,
            output_tokens=0,
            model_id=model_id,
            provider_id=provider_id,
            latency_ms=self._elapsed_ms(start_time),
            timestamp=timestamp,
            exchange_entry_id=entry_id,
            dispatch_entry_id="",
            error_code=error_code,
            error_message=error_message,
        )

    @staticmethod
    def _elapsed_ms(start_time: float) -> float:
        """Calculate elapsed milliseconds since start_time."""
        return (time.time() - start_time) * 1000


# Backward-compatibility alias
PromptRouter = LLMGateway
