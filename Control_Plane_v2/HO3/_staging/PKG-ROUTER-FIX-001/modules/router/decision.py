"""Route Decision Logic.

Makes routing decisions based on LLM classification and capabilities.
Uses PRM-ROUTER-001 governed prompt for intelligent query routing.

Example:
    from modules.router.decision import route_query, RouteMode

    capabilities = {"llm_assisted": {"summarize": True}}
    result = route_query("Summarize frameworks", capabilities=capabilities)
    print(result.mode)  # RouteMode.LLM_ASSISTED or RouteMode.TOOLS_FIRST
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
    """Routing modes."""
    TOOLS_FIRST = "tools_first"
    LLM_ASSISTED = "llm_assisted"
    DENIED = "denied"


@dataclass
class RouteResult:
    """Result of routing decision."""

    mode: RouteMode
    handler: str
    classification: QueryClassification
    prompt_pack_id: Optional[str] = None
    reason: str = ""
    capabilities_used: List[str] = field(default_factory=list)
    router_provider_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "mode": self.mode.value,
            "handler": self.handler,
            "classification": self.classification.to_dict(),
            "prompt_pack_id": self.prompt_pack_id,
            "reason": self.reason,
            "capabilities_used": self.capabilities_used,
            "router_provider_id": self.router_provider_id,
        }


# Mapping from QueryType to prompt pack IDs (for LLM-assisted)
PROMPT_PACK_MAP: Dict[QueryType, str] = {
    QueryType.EXPLAIN: "PRM-ADMIN-EXPLAIN-001",
    QueryType.VALIDATE: "PRM-ADMIN-VALIDATE-001",
    QueryType.SUMMARIZE: "PRM-ADMIN-EXPLAIN-001",  # Reuse explain prompt
    QueryType.GENERAL: "PRM-ADMIN-GENERAL-001",
}

# Query types that require LLM for full functionality
LLM_REQUIRED_TYPES = {QueryType.VALIDATE, QueryType.SUMMARIZE, QueryType.GENERAL}

# Intents that require LLM-assisted mode regardless of confidence
LLM_REQUIRED_INTENTS = {"validate", "summarize", "general"}


def _check_llm_capability(
    query_type: QueryType,
    capabilities: Dict[str, Any],
) -> tuple[bool, str]:
    """Check if LLM capability is enabled for query type.

    Args:
        query_type: Type of query
        capabilities: Agent capabilities dict

    Returns:
        Tuple of (allowed, capability_name)
    """
    llm_caps = capabilities.get("llm_assisted", {})

    # Map query types to capability names
    cap_map = {
        QueryType.VALIDATE: "validate",
        QueryType.SUMMARIZE: "summarize",
        QueryType.EXPLAIN: "explain",
        QueryType.GENERAL: "general",
    }

    cap_name = cap_map.get(query_type)
    if cap_name and llm_caps.get(cap_name, False):
        return True, cap_name

    return False, ""


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

# Mapping from router intent to prompt pack IDs
INTENT_PROMPT_MAP: Dict[str, str] = {
    "explain_artifact": "PRM-ADMIN-EXPLAIN-001",
    "validate": "PRM-ADMIN-VALIDATE-001",
    "summarize": "PRM-ADMIN-EXPLAIN-001",
    "general": "PRM-ADMIN-GENERAL-001",
}


def route_query(
    query: str,
    capabilities: Optional[Dict[str, Any]] = None,
) -> RouteResult:
    """Route a query using PC-C prompt contract.

    Uses PRM-ROUTER-001 governed prompt to classify the query intent,
    then maps to the appropriate handler and routing mode.

    Args:
        query: User query string
        capabilities: Agent capabilities dict (from manifest)

    Returns:
        RouteResult with mode, handler, and metadata
    """
    from modules.router.prompt_router import classify_intent

    capabilities = capabilities or {}

    # Classify query via governed prompt (one-shot LLM call)
    intent = classify_intent(query)

    # Map intent to handler
    handler = INTENT_HANDLER_MAP.get(intent.intent, "general")

    # Determine routing mode
    if intent.intent in LLM_REQUIRED_INTENTS:
        mode = RouteMode.LLM_ASSISTED
    elif intent.confidence >= 0.8:
        mode = RouteMode.TOOLS_FIRST
    else:
        mode = RouteMode.LLM_ASSISTED

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

    # Get prompt pack for LLM-assisted handlers
    prompt_pack_id = INTENT_PROMPT_MAP.get(intent.intent, "PRM-ADMIN-GENERAL-001")

    return RouteResult(
        mode=mode,
        handler=handler,
        classification=classification,
        prompt_pack_id=prompt_pack_id,
        reason=intent.reasoning or "PC-C classification via PRM-ROUTER-001",
        capabilities_used=["llm_assisted.router"],
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
            "prompt_pack_id": result.prompt_pack_id,
            "capabilities_used": result.capabilities_used,
            "reason": result.reason,
            "router_provider_id": result.router_provider_id,
        }
    }
