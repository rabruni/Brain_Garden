"""Route Decision Logic.

Pure routing: classify intent, map to handler name, return.
Router routes. Handler handles. Each handler decides its own execution strategy.

Example:
    from modules.router.decision import route_query

    result = route_query("Summarize frameworks")
    print(result.handler)  # "summarize"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List


class QueryType(str, Enum):
    """Types of queries."""
    LIST = "list"
    EXPLAIN = "explain"
    STATUS = "status"
    INVENTORY = "inventory"
    VALIDATE = "validate"
    SUMMARIZE = "summarize"
    LEDGER = "ledger"
    PROMPTS = "prompts"
    SESSION_LEDGER = "session_ledger"
    READ_FILE = "read_file"
    LIST_FRAMEWORKS = "list_frameworks"
    LIST_SPECS = "list_specs"
    LIST_FILES = "list_files"
    GENERAL = "general"


@dataclass
class QueryClassification:
    """Result of query classification."""

    type: QueryType
    confidence: float
    pattern_matched: bool
    matched_pattern: Optional[str] = None
    extracted_args: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "confidence": self.confidence,
            "pattern_matched": self.pattern_matched,
            "matched_pattern": self.matched_pattern,
            "extracted_args": self.extracted_args,
        }


class RouteMode(str, Enum):
    """Routing modes.

    ROUTED is the normal mode — router classified and mapped to a handler.
    DENIED is used when handler is not found (fail-closed).
    """
    ROUTED = "routed"
    DENIED = "denied"


@dataclass
class RouteResult:
    """Result of routing decision."""

    mode: RouteMode
    handler: str
    classification: QueryClassification
    reason: str = ""
    router_provider_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "mode": self.mode.value,
            "handler": self.handler,
            "classification": self.classification.to_dict(),
            "reason": self.reason,
            "router_provider_id": self.router_provider_id,
        }


# Mapping from router intent to handler names
INTENT_HANDLER_MAP: Dict[str, str] = {
    "list_packages": "list_installed",
    "list_frameworks": "list_frameworks",
    "list_specs": "list_specs",
    "explain_artifact": "explain",
    "health_check": "check_health",
    "show_ledger": "show_ledger",
    "show_session": "show_session_ledger",
    "read_file": "read_file",
    "validate": "validate_document",
    "summarize": "summarize",
    "general": "general",
}


def route_query(
    query: str,
    capabilities: Optional[Dict[str, Any]] = None,
) -> RouteResult:
    """Route a query to a handler name.

    Uses PRM-ROUTER-001 governed prompt to classify the query intent,
    then maps to the appropriate handler. That's it — no mode selection,
    no prompt pack selection, no capability checking.

    Args:
        query: User query string
        capabilities: Ignored (kept for API compatibility)

    Returns:
        RouteResult with handler and classification
    """
    from modules.router.prompt_router import classify_intent

    # Classify query via governed prompt (one-shot LLM call)
    intent = classify_intent(query)

    # Map intent to handler
    handler = INTENT_HANDLER_MAP.get(intent.intent, "general")

    # Build classification for compatibility with existing code
    classification = QueryClassification(
        type=QueryType.GENERAL,  # Default; exact type not critical
        confidence=intent.confidence,
        pattern_matched=False,
        extracted_args={
            "artifact_id": intent.artifact_id,
            "file_path": intent.file_path,
        },
    )

    return RouteResult(
        mode=RouteMode.ROUTED,
        handler=handler,
        classification=classification,
        reason=intent.reasoning or "PC-C classification via PRM-ROUTER-001",
        router_provider_id=intent.provider_id,
    )


def get_route_evidence(result: RouteResult) -> dict:
    """Build evidence record for routing decision.

    Args:
        result: RouteResult from route_query

    Returns:
        Evidence dict for logging
    """
    return {
        "route_decision": {
            "mode": result.mode.value,
            "handler": result.handler,
            "query_type": result.classification.type.value,
            "pattern_matched": result.classification.pattern_matched,
            "confidence": result.classification.confidence,
            "reason": result.reason,
            "router_provider_id": result.router_provider_id,
        }
    }
