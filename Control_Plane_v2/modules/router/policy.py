"""Route Policy Enforcement.

Loads and enforces routing policies from configuration.
Provides additional constraints beyond capability checks.

Example:
    from modules.router.policy import load_policy, enforce_policy

    policy = load_policy()
    result = enforce_policy(route_result, policy)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional

from modules.router.decision import RouteResult, RouteMode


@dataclass
class RoutePolicy:
    """Routing policy configuration."""

    # Maximum LLM calls per session
    max_llm_calls_per_session: int = 10

    # Query types that are always denied LLM
    llm_deny_list: List[str] = field(default_factory=list)

    # Query types that are always allowed LLM (if capability exists)
    llm_allow_list: List[str] = field(default_factory=list)

    # Required capabilities for LLM-assisted mode
    required_capabilities: Dict[str, List[str]] = field(default_factory=dict)

    # Custom handlers for specific patterns
    custom_handlers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "RoutePolicy":
        """Create policy from dictionary."""
        return cls(
            max_llm_calls_per_session=data.get("max_llm_calls_per_session", 10),
            llm_deny_list=data.get("llm_deny_list", []),
            llm_allow_list=data.get("llm_allow_list", []),
            required_capabilities=data.get("required_capabilities", {}),
            custom_handlers=data.get("custom_handlers", {}),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "max_llm_calls_per_session": self.max_llm_calls_per_session,
            "llm_deny_list": self.llm_deny_list,
            "llm_allow_list": self.llm_allow_list,
            "required_capabilities": self.required_capabilities,
            "custom_handlers": self.custom_handlers,
        }


def _get_policy_path() -> Path:
    """Get router_policy.json path."""
    current = Path(__file__).resolve()
    while current.name != "Control_Plane_v2" and current.parent != current:
        current = current.parent
    if current.name == "Control_Plane_v2":
        return current / "config" / "router_policy.json"
    return Path.cwd() / "config" / "router_policy.json"


def load_policy() -> RoutePolicy:
    """Load routing policy from configuration.

    Returns:
        RoutePolicy instance (defaults if file missing)
    """
    policy_path = _get_policy_path()

    if not policy_path.exists():
        return RoutePolicy()

    try:
        data = json.loads(policy_path.read_text())
        return RoutePolicy.from_dict(data)
    except Exception:
        return RoutePolicy()


@dataclass
class PolicyResult:
    """Result of policy enforcement."""

    allowed: bool
    route_result: RouteResult
    violations: List[str] = field(default_factory=list)
    modifications: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "allowed": self.allowed,
            "route_result": self.route_result.to_dict(),
            "violations": self.violations,
            "modifications": self.modifications,
        }


def enforce_policy(
    route_result: RouteResult,
    policy: Optional[RoutePolicy] = None,
    session_llm_count: int = 0,
) -> PolicyResult:
    """Enforce routing policy on a route result.

    Args:
        route_result: Result from route_query
        policy: Policy to enforce (loads default if None)
        session_llm_count: Current LLM call count for session

    Returns:
        PolicyResult with enforcement outcome
    """
    policy = policy or load_policy()
    violations = []
    modifications = []
    allowed = True
    result = route_result

    query_type = route_result.classification.type.value

    # Check deny list
    if query_type in policy.llm_deny_list:
        if route_result.mode == RouteMode.LLM_ASSISTED:
            violations.append(f"Query type '{query_type}' is in LLM deny list")
            # Force to tools-first
            result = RouteResult(
                mode=RouteMode.TOOLS_FIRST,
                handler=route_result.handler,
                classification=route_result.classification,
                reason="Policy: LLM denied for this query type",
            )
            modifications.append("Changed mode from LLM_ASSISTED to TOOLS_FIRST")

    # Check session LLM limit
    if route_result.mode == RouteMode.LLM_ASSISTED:
        if session_llm_count >= policy.max_llm_calls_per_session:
            violations.append(
                f"Session LLM limit reached ({policy.max_llm_calls_per_session})"
            )
            result = RouteResult(
                mode=RouteMode.TOOLS_FIRST,
                handler=route_result.handler,
                classification=route_result.classification,
                reason="Policy: Session LLM limit reached",
            )
            modifications.append("Changed mode from LLM_ASSISTED to TOOLS_FIRST")

    # Check required capabilities
    if query_type in policy.required_capabilities:
        required = policy.required_capabilities[query_type]
        for cap in required:
            if cap not in route_result.capabilities_used:
                violations.append(f"Missing required capability: {cap}")
                allowed = False

    # Check custom handlers
    if query_type in policy.custom_handlers:
        custom_handler = policy.custom_handlers[query_type]
        if route_result.handler != custom_handler:
            result = RouteResult(
                mode=route_result.mode,
                handler=custom_handler,
                classification=route_result.classification,
                prompt_pack_id=route_result.prompt_pack_id,
                reason=f"Policy: Custom handler for {query_type}",
                capabilities_used=route_result.capabilities_used,
            )
            modifications.append(f"Changed handler to {custom_handler}")

    return PolicyResult(
        allowed=allowed,
        route_result=result,
        violations=violations,
        modifications=modifications,
    )
