"""Work Order -- the atomic unit of cognitive dispatch.

HO2 creates work orders, HO1 executes them, HO2 verifies them.
This module provides the WorkOrder dataclass, state machine
(WorkOrderStateMachine), and validator (WorkOrderValidator).

Governed by FMWK-008 (Work Order Protocol).

Usage:
    from kernel.work_order import WorkOrder, WorkOrderStateMachine, WorkOrderValidator

    wo = WorkOrder.create(
        wo_type="classify",
        session_id="SES-A1B2C3D4",
        created_by="ADMIN.ho2",
        input_context={"user_input": "show me all frameworks"},
        constraints={"prompt_contract_id": "PC-C-001", "token_budget": 2000},
    )

    WorkOrderStateMachine.transition(wo, "dispatched")
"""

import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COGNITIVE_WO_TYPES: Set[str] = {"classify", "tool_call", "synthesize", "execute"}
WO_STATES: Set[str] = {"planned", "dispatched", "executing", "completed", "failed"}
TERMINAL_STATES: Set[str] = {"completed", "failed"}

# Types that invoke LLM and therefore need a prompt_contract_id
LLM_CALLING_TYPES: Set[str] = {"classify", "synthesize", "execute"}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InvalidTransitionError(Exception):
    """Raised on forbidden state transitions."""
    pass


class WorkOrderValidationError(Exception):
    """Raised on validation failure."""
    pass


# ---------------------------------------------------------------------------
# Sequence counter (thread-safe)
# ---------------------------------------------------------------------------

_seq_lock = threading.Lock()
_seq_counters: Dict[str, int] = {}


def _next_seq(session_id: str) -> int:
    """Get next sequence number for a session, thread-safe."""
    with _seq_lock:
        current = _seq_counters.get(session_id, 0) + 1
        _seq_counters[session_id] = current
        return current


# ---------------------------------------------------------------------------
# WorkOrder Dataclass
# ---------------------------------------------------------------------------

@dataclass
class WorkOrder:
    """Atomic unit of cognitive dispatch between HO2 and HO1.

    A work order is a structured, bounded, one-shot instruction that
    HO2 creates and HO1 executes. It carries data and validates
    transitions -- it does NOT call LLMs, execute tools, or manage sessions.
    """

    wo_id: str
    session_id: str
    wo_type: str                                    # classify | tool_call | synthesize | execute
    tier_target: str                                # "HO1" (always, for now)
    state: str                                      # planned | dispatched | executing | completed | failed
    created_at: str                                 # ISO8601 UTC
    created_by: str                                 # Agent ID (always an HO2 agent)

    # Optional identity
    parent_wo_id: Optional[str] = None              # Parent WO for chained dispatch

    # Input (set at creation by HO2)
    input_context: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    acceptance_criteria: Dict[str, Any] = field(default_factory=dict)

    # Output (set at completion by HO1)
    output_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    completed_at: Optional[str] = None

    # Cost tracking
    cost: Dict[str, Any] = field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "llm_calls": 0,
        "tool_calls": 0,
        "elapsed_ms": 0,
    })

    @classmethod
    def create(
        cls,
        wo_type: str,
        session_id: str,
        created_by: str,
        input_context: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        acceptance_criteria: Optional[Dict[str, Any]] = None,
        parent_wo_id: Optional[str] = None,
    ) -> "WorkOrder":
        """Create a new WorkOrder with auto-generated ID and timestamp.

        Args:
            wo_type: One of classify, tool_call, synthesize, execute
            session_id: Session ID (SES-...)
            created_by: Agent ID of the creator (HO2 agent)
            input_context: Input data for the WO
            constraints: Execution constraints (budget, contracts, tools)
            acceptance_criteria: Criteria for verification
            parent_wo_id: Parent WO ID for chained dispatch

        Returns:
            New WorkOrder in 'planned' state

        Raises:
            ValueError: If wo_type is invalid or required fields are empty
        """
        if wo_type not in COGNITIVE_WO_TYPES:
            raise ValueError(
                f"Invalid wo_type '{wo_type}'. Must be one of: {sorted(COGNITIVE_WO_TYPES)}"
            )
        if not session_id:
            raise ValueError("session_id is required")
        if not created_by:
            raise ValueError("created_by is required")

        seq = _next_seq(session_id)
        wo_id = f"WO-{session_id}-{seq:03d}"

        return cls(
            wo_id=wo_id,
            session_id=session_id,
            wo_type=wo_type,
            tier_target="HO1",
            state="planned",
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
            parent_wo_id=parent_wo_id,
            input_context=input_context or {},
            constraints=constraints or {},
            acceptance_criteria=acceptance_criteria or {},
        )

    def is_terminal(self) -> bool:
        """Check if WO is in a terminal state (completed or failed)."""
        return self.state in TERMINAL_STATES

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkOrder":
        """Deserialize from dict."""
        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "WorkOrder":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------

class WorkOrderStateMachine:
    """Enforces valid state transitions for WorkOrders.

    Implements the 5-state lifecycle:
        planned -> dispatched -> executing -> completed
                                           -> failed
        planned -> failed (validation fail at planning)

    Terminal states (completed, failed) never regress.
    HO1 can only set executing, completed, or failed.
    """

    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        "planned": {"dispatched", "failed"},
        "dispatched": {"executing"},
        "executing": {"completed", "failed"},
        "completed": set(),
        "failed": set(),
    }

    TERMINAL_STATES: Set[str] = TERMINAL_STATES

    # States HO1 is allowed to transition to
    HO1_ALLOWED_STATES: Set[str] = {"executing", "completed", "failed"}

    @classmethod
    def transition(
        cls,
        wo: WorkOrder,
        new_state: str,
        actor_tier: str = "HO2",
    ) -> WorkOrder:
        """Validate and perform a state transition.

        Args:
            wo: WorkOrder to transition
            new_state: Target state
            actor_tier: Tier of the actor performing the transition ("HO1" or "HO2")

        Returns:
            The updated WorkOrder (same instance, mutated)

        Raises:
            InvalidTransitionError: On forbidden transition
        """
        if new_state not in WO_STATES:
            raise InvalidTransitionError(
                f"Invalid state '{new_state}'. Must be one of: {sorted(WO_STATES)}"
            )

        # Tier ownership check: HO1 can only set executing, completed, failed
        if actor_tier == "HO1" and new_state not in cls.HO1_ALLOWED_STATES:
            raise InvalidTransitionError(
                f"HO1 cannot transition to '{new_state}'. "
                f"HO1 can only set: {sorted(cls.HO1_ALLOWED_STATES)}"
            )

        # Transition validity check
        allowed = cls.VALID_TRANSITIONS.get(wo.state, set())
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from '{wo.state}' to '{new_state}'. "
                f"Allowed transitions from '{wo.state}': {sorted(allowed) if allowed else 'NONE (terminal state)'}"
            )

        wo.state = new_state
        if new_state in cls.TERMINAL_STATES:
            wo.completed_at = datetime.now(timezone.utc).isoformat()

        return wo


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class WorkOrderValidator:
    """Validates WorkOrder instances for completeness and correctness."""

    @classmethod
    def validate(cls, wo: WorkOrder) -> Tuple[bool, List[str]]:
        """Validate a WorkOrder.

        Checks:
        - Required fields are present
        - wo_type is valid
        - LLM-calling types have prompt_contract_id
        - tool_call has tools_allowed
        - token_budget is positive

        Args:
            wo: WorkOrder to validate

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors: List[str] = []

        # Type check
        if wo.wo_type not in COGNITIVE_WO_TYPES:
            errors.append(f"Invalid wo_type '{wo.wo_type}'")

        # Required fields
        if not wo.session_id:
            errors.append("session_id is required")
        if not wo.created_by:
            errors.append("created_by is required")

        # LLM-calling types need prompt_contract_id
        if wo.wo_type in LLM_CALLING_TYPES:
            if not wo.constraints.get("prompt_contract_id"):
                errors.append(
                    f"wo_type '{wo.wo_type}' requires constraints.prompt_contract_id"
                )

        # tool_call needs tools_allowed
        if wo.wo_type == "tool_call":
            if not wo.constraints.get("tools_allowed"):
                errors.append("wo_type 'tool_call' requires constraints.tools_allowed")

        # token_budget must be positive if specified
        budget = wo.constraints.get("token_budget")
        if budget is not None and budget <= 0:
            errors.append(f"constraints.token_budget must be positive, got {budget}")

        return (len(errors) == 0, errors)

    @classmethod
    def validate_against_schema(
        cls,
        wo_dict: Dict[str, Any],
        schema_path: "Path",
    ) -> Tuple[bool, List[str]]:
        """Validate a WO dict against cognitive_work_order.schema.json.

        Args:
            wo_dict: WorkOrder as dict
            schema_path: Path to the JSON schema file

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        from pathlib import Path as _Path

        errors: List[str] = []
        try:
            schema = json.loads(_Path(schema_path).read_text())
        except Exception as e:
            return (False, [f"Cannot load schema: {e}"])

        # Check required fields
        for req in schema.get("required", []):
            if req not in wo_dict:
                errors.append(f"Missing required field: {req}")

        # Check enum constraints for present fields
        props = schema.get("properties", {})
        for field_name, field_schema in props.items():
            if field_name in wo_dict and "enum" in field_schema:
                if wo_dict[field_name] not in field_schema["enum"]:
                    errors.append(
                        f"Field '{field_name}' value '{wo_dict[field_name]}' "
                        f"not in enum {field_schema['enum']}"
                    )

        return (len(errors) == 0, errors)
