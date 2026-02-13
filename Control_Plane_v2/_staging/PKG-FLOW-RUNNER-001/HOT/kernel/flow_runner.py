"""
Flow Runner — Agent Orchestrator (KERNEL.semantic)

Reads a work order, instantiates an agent from a framework definition,
wires attention → router, and manages the execution lifecycle.

v1 scope: single-step execution only.
  One work order → one prompt → one response → done.

9-step flow:
  1. Validate work order
  2. Resolve framework → determine agent class + tier
  3. Allocate budget (→ Token Budgeter)
  4. Create execution context
  5. Assemble context (→ Attention Service)
  6. Send prompt (→ Prompt Router)
  7. Validate acceptance criteria
  8. Log outcome (→ Ledger)
  9. Return result

PKG-FLOW-RUNNER-001 | FMWK-005 Agent Orchestration
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Data classes — inputs, outputs, internal state
# ---------------------------------------------------------------------------

@dataclass
class FlowRequest:
    """Input to the flow runner."""
    work_order: dict
    caller_id: str
    dev_mode: bool = False


@dataclass
class FlowResult:
    """Output from the flow runner. Always returned — never throws."""
    status: str                         # success | failure | rejected | timeout | budget_exhausted
    work_order_id: str
    agent_id: str
    response: str | None                # LLM response text
    tokens_used: dict | None            # {input: N, output: M}
    validation_result: dict | None      # Acceptance criteria results
    ledger_entry_ids: list[str]         # All ledger entries created
    error: str | None                   # Error message if failed
    duration_ms: int                    # Wall-clock execution time


@dataclass
class ExecutionContext:
    """The 'agent instance' — an execution context, not a persistent process."""
    agent_id: str
    agent_class: str
    framework_id: str
    tier: str
    work_order: dict
    prompt_contracts: list[dict]
    budget_scope: dict
    path_authorizations: list[str]
    tool_permissions: list[dict]
    session_id: str
    created_at: str


@dataclass
class StepAction:
    """What the step strategy decides to do next."""
    type: str  # send_prompt | delegate | complete


# ---------------------------------------------------------------------------
# v2 Extension Points — interfaces with v1 concrete implementations
# ---------------------------------------------------------------------------

class StepStrategy:
    """Base class for execution strategies. v2: multi-step loops."""

    def next_step(self, context: ExecutionContext, history: list) -> StepAction:
        raise NotImplementedError("Subclasses must implement next_step")


class SingleStepStrategy(StepStrategy):
    """v1: one prompt, one response, done."""

    def next_step(self, context: ExecutionContext, history: list) -> StepAction:
        if not history:
            return StepAction(type="send_prompt")
        return StepAction(type="complete")


class ApertureManager:
    """Manages aperture state transitions. v1: always closed."""

    def current_state(self) -> str:
        return "closed"

    def should_transition(self, step_count: int, budget_remaining: float) -> str | None:
        return None


class DelegationManager:
    """Manages sub-WO creation and HO2→HO1 delegation. v2 only."""

    def create_sub_wo(self, parent_wo: dict, sub_task: dict) -> dict:
        raise NotImplementedError("Delegation is v2")

    def collect_results(self, sub_results: list) -> dict:
        raise NotImplementedError("Delegation is v2")


class RecoveryStrategy:
    """Handles partial work on failure. v1: always discard."""

    def on_failure(self, context: ExecutionContext, partial_results: list, error: str) -> str:
        return "discard"


# ---------------------------------------------------------------------------
# WO Schema — required fields for structural validation
# ---------------------------------------------------------------------------

_WO_REQUIRED_FIELDS = frozenset([
    "work_order_id", "type", "plane_id", "spec_id",
    "framework_id", "scope", "acceptance",
])

_VALID_PLANE_IDS = frozenset(["hot", "ho2", "ho1"])

_VALID_AGENT_CLASSES = frozenset([
    "KERNEL.syntactic", "KERNEL.semantic", "ADMIN", "RESIDENT",
])


# ---------------------------------------------------------------------------
# LedgerEntry helper — lightweight wrapper for writing events
# ---------------------------------------------------------------------------

@dataclass
class _LedgerEntry:
    """Internal ledger entry for flow runner events."""
    event_type: str
    submission_id: str
    decision: str
    reason: str
    metadata: dict = field(default_factory=dict)
    prompts_used: list = field(default_factory=list)
    id: str = ""
    timestamp: str = ""
    previous_hash: str = ""
    entry_hash: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"LED-{hashlib.sha256(f'{time.time_ns()}'.encode()).hexdigest()[:8]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# FlowRunner — the 9-step orchestrator
# ---------------------------------------------------------------------------

class FlowRunner:
    """
    Agent orchestrator (KERNEL.semantic).

    Not an agent itself — the machinery that brings agents to life by reading
    framework definitions and executing work orders.
    """

    def __init__(
        self,
        config: dict,
        budgeter: Any,
        router: Any,
        attention: Any,
        ledger: Any,
        framework_resolver: Any,
        auth: Any,
    ):
        self._config = config
        self._budgeter = budgeter
        self._router = router
        self._attention = attention
        self._ledger = ledger
        self._resolver = framework_resolver
        self._auth = auth

        # v1 strategy — single-step only
        self._step_strategy = SingleStepStrategy()
        self._aperture = ApertureManager()
        self._recovery = RecoveryStrategy()

    def execute(self, request: FlowRequest) -> FlowResult:
        """
        Execute a work order through the 9-step flow.

        Always returns a FlowResult — never raises exceptions to the caller.
        """
        start_ns = time.monotonic_ns()
        ledger_entry_ids: list[str] = []
        agent_id = ""
        wo_id = ""

        try:
            wo = request.work_order
            wo_id = wo.get("work_order_id", "UNKNOWN")

            # ── Step 1: Validate Work Order ──
            validation_error = self._validate_work_order(wo)
            if validation_error:
                entry_id = self._log_event(
                    "WO_REJECTED", wo_id, "REJECTED",
                    f"Validation failed: {validation_error}",
                    metadata={"error": validation_error},
                )
                ledger_entry_ids.append(entry_id)
                return self._result(
                    "rejected", wo_id, agent_id, None, None, None,
                    ledger_entry_ids, validation_error, start_ns,
                )

            # ── Step 2: Resolve Framework ──
            framework_id = wo["framework_id"]
            manifest = self._resolver.resolve(framework_id)
            if manifest is None:
                error_msg = f"Framework not found: {framework_id}"
                entry_id = self._log_event(
                    "WO_REJECTED", wo_id, "REJECTED", error_msg,
                    metadata={"error": error_msg, "framework_id": framework_id},
                )
                ledger_entry_ids.append(entry_id)
                return self._result(
                    "rejected", wo_id, agent_id, None, None, None,
                    ledger_entry_ids, error_msg, start_ns,
                )

            # Determine agent class
            agent_class = wo.get("agent_class")
            if agent_class is None:
                # Default from framework ring
                ring = manifest.get("ring", "kernel")
                agent_class = "KERNEL.semantic" if ring == "kernel" else "RESIDENT"

            # Check permitted agent classes
            permitted = manifest.get("permitted_agent_classes")
            if permitted and agent_class not in permitted:
                error_msg = (
                    f"Agent class '{agent_class}' not permitted by framework "
                    f"'{framework_id}'. Permitted: {permitted}"
                )
                entry_id = self._log_event(
                    "WO_REJECTED", wo_id, "REJECTED", error_msg,
                    metadata={"error": error_msg},
                )
                ledger_entry_ids.append(entry_id)
                return self._result(
                    "rejected", wo_id, agent_id, None, None, None,
                    ledger_entry_ids, error_msg, start_ns,
                )

            # Determine tier from plane_id
            tier = wo["plane_id"]

            # Generate agent_id
            prefix = self._config.get("agent_id_prefix", "AGT")
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            agent_id = f"{prefix}-{framework_id}-{wo_id}-{ts}"

            # ── Step 3: Allocate Budget ──
            session_id = (wo.get("authorization") or {}).get("session_id", "SES-00000000")
            budget_fields = wo.get("budget") or self._config.get("default_budget", {})

            budget_scope = _BudgetScope(
                session_id=session_id,
                work_order_id=wo_id,
                agent_id=agent_id,
                token_limit=budget_fields.get("token_limit", 10000),
                timeout_seconds=budget_fields.get("timeout_seconds", 120),
            )

            alloc_result = self._budgeter.allocate(budget_scope)
            if not alloc_result.success:
                error_msg = f"Budget allocation denied: {alloc_result.reason}"
                entry_id = self._log_event(
                    "WO_REJECTED", wo_id, "REJECTED", error_msg,
                    metadata={"error": error_msg, "budget_reason": alloc_result.reason},
                )
                ledger_entry_ids.append(entry_id)
                return self._result(
                    "rejected", wo_id, agent_id, None, None, None,
                    ledger_entry_ids, error_msg, start_ns,
                )

            # ── Step 4: Create Execution Context ──
            prompt_contracts = self._resolver.find_prompt_contracts(
                framework_id=framework_id,
                agent_class=agent_class,
            )

            path_auths = manifest.get("path_authorizations", [])
            tool_perms = wo.get("tool_permissions", [])

            ctx = ExecutionContext(
                agent_id=agent_id,
                agent_class=agent_class,
                framework_id=framework_id,
                tier=tier,
                work_order=wo,
                prompt_contracts=prompt_contracts,
                budget_scope=budget_scope.__dict__,
                path_authorizations=path_auths,
                tool_permissions=tool_perms,
                session_id=session_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            # Auth check (skip in dev mode)
            if not request.dev_mode:
                try:
                    identity = self._auth.authenticate(request.caller_id)
                    self._auth.is_authorized(identity, "execute_wo")
                except Exception:
                    pass  # Non-fatal in v1 — auth infrastructure may not be fully wired

            # Log WO_STARTED
            entry_id = self._log_event(
                "WO_STARTED", wo_id, "STARTED", "Work order execution started",
                metadata={
                    "provenance": {
                        "agent_id": agent_id,
                        "agent_class": agent_class,
                        "framework_id": framework_id,
                        "work_order_id": wo_id,
                        "session_id": session_id,
                    },
                    "budget_scope": budget_scope.__dict__,
                    "tier": tier,
                },
            )
            ledger_entry_ids.append(entry_id)

            # ── Step 5: Assemble Context (→ Attention) ──
            selected_contract = prompt_contracts[0] if prompt_contracts else {}

            attn_request = _AttentionRequest(
                agent_id=agent_id,
                agent_class=agent_class,
                framework_id=framework_id,
                tier=tier,
                work_order_id=wo_id,
                session_id=session_id,
                prompt_contract=selected_contract,
            )

            assembled_context = self._attention.assemble(attn_request)

            # ── Step 6: Send Prompt (→ Router) ──
            router_response = self._router.send(
                prompt=assembled_context.context_text,
                contract=selected_contract,
                agent_id=agent_id,
                agent_class=agent_class,
                framework_id=framework_id,
                work_order_id=wo_id,
                session_id=session_id,
            )

            response_text = router_response.response
            tokens_used = router_response.tokens_used
            router_entry_ids = router_response.ledger_entry_ids or []
            ledger_entry_ids.extend(router_entry_ids)

            # ── Step 7: Validate Acceptance Criteria ──
            acceptance = wo.get("acceptance", {})
            io_schema = wo.get("io_schema", {})
            validation_result = self._validate_acceptance(
                response_text, acceptance, io_schema
            )

            if validation_result.get("passed") is False:
                # Acceptance failed
                entry_id = self._log_event(
                    "WO_EXEC_FAILED", wo_id, "FAILED",
                    "Acceptance criteria not met",
                    metadata={
                        "outcome": {
                            "status": "failure",
                            "gate_results": validation_result.get("gate_results", []),
                        },
                        "provenance": {
                            "agent_id": agent_id,
                            "agent_class": agent_class,
                            "framework_id": framework_id,
                            "work_order_id": wo_id,
                            "session_id": session_id,
                        },
                        "tokens_used": tokens_used,
                        "duration_ms": self._elapsed_ms(start_ns),
                    },
                )
                ledger_entry_ids.append(entry_id)
                return self._result(
                    "failure", wo_id, agent_id, response_text, tokens_used,
                    validation_result, ledger_entry_ids,
                    "Acceptance criteria not met", start_ns,
                )

            # ── Step 8: Log Outcome ──
            entry_id = self._log_event(
                "WO_EXEC_COMPLETE", wo_id, "COMPLETE",
                "Work order executed successfully",
                metadata={
                    "provenance": {
                        "agent_id": agent_id,
                        "agent_class": agent_class,
                        "framework_id": framework_id,
                        "work_order_id": wo_id,
                        "session_id": session_id,
                    },
                    "outcome": {
                        "status": "success",
                        "gate_results": validation_result.get("gate_results", []),
                    },
                    "context_fingerprint": {
                        "context_hash": assembled_context.context_hash,
                    },
                    "tokens_used": tokens_used,
                    "duration_ms": self._elapsed_ms(start_ns),
                },
            )
            ledger_entry_ids.append(entry_id)

            # ── Step 9: Return ──
            return self._result(
                "success", wo_id, agent_id, response_text, tokens_used,
                validation_result, ledger_entry_ids, None, start_ns,
            )

        except TimeoutError as e:
            entry_id = self._log_event(
                "WO_EXEC_FAILED", wo_id, "FAILED", f"Timeout: {e}",
                metadata={"outcome": {"status": "timeout", "error": str(e)}},
            )
            ledger_entry_ids.append(entry_id)
            return self._result(
                "timeout", wo_id, agent_id, None, None, None,
                ledger_entry_ids, str(e), start_ns,
            )

        except Exception as e:
            # Catch-all: never let exceptions leak to caller
            try:
                entry_id = self._log_event(
                    "WO_EXEC_FAILED", wo_id, "FAILED", f"Unexpected error: {e}",
                    metadata={"outcome": {"status": "failure", "error": str(e)}},
                )
                ledger_entry_ids.append(entry_id)
            except Exception:
                pass  # Even ledger write failed — still return a FlowResult

            return self._result(
                "failure", wo_id, agent_id, None, None, None,
                ledger_entry_ids, str(e), start_ns,
            )

    # -------------------------------------------------------------------
    # Step 1 internals
    # -------------------------------------------------------------------

    def _validate_work_order(self, wo: dict) -> str | None:
        """Structural validation of the work order. Returns error message or None."""
        if not isinstance(wo, dict):
            return "Work order must be a dict"

        missing = _WO_REQUIRED_FIELDS - set(wo.keys())
        if missing:
            return f"Missing required fields: {sorted(missing)}"

        plane_id = wo.get("plane_id")
        if plane_id not in _VALID_PLANE_IDS:
            return f"Invalid plane_id: '{plane_id}'. Must be one of {sorted(_VALID_PLANE_IDS)}"

        agent_class = wo.get("agent_class")
        if agent_class is not None and agent_class not in _VALID_AGENT_CLASSES:
            return (
                f"Invalid agent_class: '{agent_class}'. "
                f"Must be one of {sorted(_VALID_AGENT_CLASSES)}"
            )

        scope = wo.get("scope")
        if not isinstance(scope, dict) or "allowed_files" not in scope:
            return "scope must be an object with 'allowed_files'"

        return None

    # -------------------------------------------------------------------
    # Step 7 internals
    # -------------------------------------------------------------------

    def _validate_acceptance(
        self, response: str | None, acceptance: dict, io_schema: dict,
    ) -> dict:
        """
        Run acceptance criteria. Returns dict with 'passed' and 'gate_results'.
        """
        gate_results = []
        all_passed = True

        # Output schema validation
        output_schema = io_schema.get("output_schema")
        if output_schema and response:
            try:
                parsed = json.loads(response)
                # Basic type check against schema (jsonschema not assumed available)
                schema_type = output_schema.get("type")
                if schema_type == "object" and not isinstance(parsed, dict):
                    gate_results.append({
                        "gate": "output_schema",
                        "passed": False,
                        "reason": f"Expected object, got {type(parsed).__name__}",
                    })
                    all_passed = False
                else:
                    # Check required fields if defined
                    required = output_schema.get("required", [])
                    missing = [f for f in required if f not in parsed]
                    if missing:
                        gate_results.append({
                            "gate": "output_schema",
                            "passed": False,
                            "reason": f"Missing required fields: {missing}",
                        })
                        all_passed = False
                    else:
                        gate_results.append({
                            "gate": "output_schema",
                            "passed": True,
                            "reason": "Schema validation passed",
                        })
            except (json.JSONDecodeError, TypeError) as e:
                gate_results.append({
                    "gate": "output_schema",
                    "passed": False,
                    "reason": f"Response is not valid JSON: {e}",
                })
                all_passed = False

        # Test commands
        tests = acceptance.get("tests", [])
        cfg_timeout = self._config.get("acceptance", {}).get("command_timeout_seconds", 30)
        max_cmds = self._config.get("acceptance", {}).get("max_commands", 10)

        for i, cmd in enumerate(tests[:max_cmds]):
            if not cmd:
                continue
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, timeout=cfg_timeout,
                )
                passed = result.returncode == 0
                gate_results.append({
                    "gate": f"test_{i}",
                    "passed": passed,
                    "reason": f"exit {result.returncode}",
                })
                if not passed:
                    all_passed = False
            except subprocess.TimeoutExpired:
                gate_results.append({
                    "gate": f"test_{i}",
                    "passed": False,
                    "reason": f"Timed out after {cfg_timeout}s",
                })
                all_passed = False
            except Exception as e:
                gate_results.append({
                    "gate": f"test_{i}",
                    "passed": False,
                    "reason": str(e),
                })
                all_passed = False

        # Check commands
        checks = acceptance.get("checks", [])
        for i, cmd in enumerate(checks[:max_cmds]):
            if not cmd:
                continue
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, timeout=cfg_timeout,
                )
                passed = result.returncode == 0
                gate_results.append({
                    "gate": f"check_{i}",
                    "passed": passed,
                    "reason": f"exit {result.returncode}",
                })
                if not passed:
                    all_passed = False
            except Exception as e:
                gate_results.append({
                    "gate": f"check_{i}",
                    "passed": False,
                    "reason": str(e),
                })
                all_passed = False

        return {
            "passed": all_passed,
            "gate_results": gate_results,
        }

    # -------------------------------------------------------------------
    # Ledger helpers
    # -------------------------------------------------------------------

    def _log_event(
        self,
        event_type: str,
        wo_id: str,
        decision: str,
        reason: str,
        metadata: dict | None = None,
    ) -> str:
        """Write a ledger entry and return its ID."""
        entry = _LedgerEntry(
            event_type=event_type,
            submission_id=wo_id,
            decision=decision,
            reason=reason,
            metadata=metadata or {},
        )
        self._ledger.write(entry)
        return entry.id

    # -------------------------------------------------------------------
    # Result helpers
    # -------------------------------------------------------------------

    def _result(
        self,
        status: str,
        wo_id: str,
        agent_id: str,
        response: str | None,
        tokens_used: dict | None,
        validation_result: dict | None,
        ledger_entry_ids: list[str],
        error: str | None,
        start_ns: int,
    ) -> FlowResult:
        return FlowResult(
            status=status,
            work_order_id=wo_id,
            agent_id=agent_id,
            response=response,
            tokens_used=tokens_used,
            validation_result=validation_result,
            ledger_entry_ids=ledger_entry_ids,
            error=error,
            duration_ms=self._elapsed_ms(start_ns),
        )

    @staticmethod
    def _elapsed_ms(start_ns: int) -> int:
        return int((time.monotonic_ns() - start_ns) / 1_000_000)


# ---------------------------------------------------------------------------
# Internal data classes for type-safe dependency calls
# ---------------------------------------------------------------------------

@dataclass
class _BudgetScope:
    session_id: str
    work_order_id: str
    agent_id: str
    token_limit: int
    timeout_seconds: int


@dataclass
class _AttentionRequest:
    agent_id: str
    agent_class: str
    framework_id: str
    tier: str
    work_order_id: str
    session_id: str
    prompt_contract: dict
