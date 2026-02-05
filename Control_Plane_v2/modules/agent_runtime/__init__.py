"""Agent Runtime Module.

Provides the execution framework for agents operating within the Control Plane
governance model. Handles capability enforcement, session management, sandbox
isolation, ledger writing, and context assembly.

This is a Tier 1 (T1) runtime module.

Example usage:
    from modules.agent_runtime import AgentRunner, Session, TurnRequest, TurnResult

    runner = AgentRunner("PKG-ADMIN-001", tier="ho1")

    def my_handler(request: TurnRequest) -> TurnResult:
        # Agent logic here
        return TurnResult(status="ok", result={"answer": "..."}, evidence={})

    request = TurnRequest(
        session_id="SES-abc123",
        turn_number=1,
        query={"question": "What is FMWK-000?"},
        declared_inputs=[],
        declared_outputs=[]
    )

    result = runner.execute_turn(request, my_handler)
"""

from modules.agent_runtime.runner import AgentRunner, TurnRequest, TurnResult
from modules.agent_runtime.capability import CapabilityEnforcer
from modules.agent_runtime.session import Session
from modules.agent_runtime.sandbox import TurnSandbox
from modules.agent_runtime.prompt_builder import PromptBuilder
from modules.agent_runtime.memory import AgentMemory
from modules.agent_runtime.ledger_writer import LedgerWriter
from modules.agent_runtime.exceptions import (
    CapabilityViolation,
    PackageNotFoundError,
    SessionError,
    SandboxError,
)

__all__ = [
    "AgentRunner",
    "TurnRequest",
    "TurnResult",
    "CapabilityEnforcer",
    "Session",
    "TurnSandbox",
    "PromptBuilder",
    "AgentMemory",
    "LedgerWriter",
    "CapabilityViolation",
    "PackageNotFoundError",
    "SessionError",
    "SandboxError",
]

__version__ = "0.1.0"
