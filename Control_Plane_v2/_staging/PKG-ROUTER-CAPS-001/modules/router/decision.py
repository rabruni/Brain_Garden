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

from modules.router.capabilities import gather_capabilities


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


# Static mapping from router intent to handler names (fallback)
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


def _build_handler_map(capabilities: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Build intent-to-handler map from capabilities, falling back to static map.

    Args:
        capabilities: Optional capabilities dict with "intents" array

    Returns:
        Dict mapping intent IDs to handler names
    """
    if not capabilities or "intents" not in capabilities:
        return INTENT_HANDLER_MAP

    # Build dynamic map from capabilities
    dynamic_map = {}
    for intent in capabilities["intents"]:
        dynamic_map[intent["id"]] = intent["handler"]

    # Static map is authoritative for known intents; dynamic adds new ones
    merged = dict(dynamic_map)
    merged.update(INTENT_HANDLER_MAP)
    return merged


def route_query(
    query: str,
    capabilities: Optional[Dict[str, Any]] = None,
) -> RouteResult:
    """Route a query to a handler name.

    Uses PRM-ROUTER-001 governed prompt to classify the query intent,
    then maps to the appropriate handler.

    When capabilities are provided:
    1. Passes them to classify_intent for dynamic intent validation
    2. Uses them to build the intent-to-handler map

    Args:
        query: User query string
        capabilities: Optional capabilities from gather_capabilities()

    Returns:
        RouteResult with handler and classification
    """
    from modules.router.prompt_router import classify_intent

    # Gather capabilities if not provided
    if capabilities is None:
        try:
            capabilities = gather_capabilities()
        except Exception:
            capabilities = None

    # Classify query via governed prompt (one-shot LLM call)
    intent = classify_intent(query, capabilities=capabilities)

    # Map intent to handler (dynamic map from capabilities)
    handler_map = _build_handler_map(capabilities)
    handler = handler_map.get(intent.intent, "general")

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
