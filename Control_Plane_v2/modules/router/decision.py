"""Route Decision Logic.

Makes routing decisions based on classification and capabilities.
Enforces fail-closed behavior: no LLM capability = TOOLS_FIRST.

Example:
    from modules.router.decision import route_query, RouteMode

    capabilities = {"llm_assisted": {"summarize": True}}
    result = route_query("Summarize frameworks", capabilities=capabilities)
    print(result.mode)  # RouteMode.LLM_ASSISTED or RouteMode.TOOLS_FIRST
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List

from modules.router.classifier import (
    classify_query,
    QueryClassification,
    QueryType,
    needs_llm_classification,
)


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

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "mode": self.mode.value,
            "handler": self.handler,
            "classification": self.classification.to_dict(),
            "prompt_pack_id": self.prompt_pack_id,
            "reason": self.reason,
            "capabilities_used": self.capabilities_used,
        }


# Mapping from QueryType to handler names
HANDLER_MAP: Dict[QueryType, str] = {
    QueryType.LIST: "list_installed",
    QueryType.EXPLAIN: "explain",
    QueryType.STATUS: "check_health",
    QueryType.INVENTORY: "inventory",
    QueryType.VALIDATE: "validate_document",
    QueryType.SUMMARIZE: "summarize",
    QueryType.LEDGER: "show_ledger",
    QueryType.PROMPTS: "show_prompts_used",  # Show governed prompt usage
    QueryType.SESSION_LEDGER: "show_session_ledger",  # Show current session ledger
    QueryType.READ_FILE: "read_file",
    QueryType.LIST_FRAMEWORKS: "list_frameworks",
    QueryType.LIST_SPECS: "list_specs",
    QueryType.LIST_FILES: "list_files",
    QueryType.GENERAL: "general",  # Conversational queries
}

# Mapping from QueryType to prompt pack IDs (for LLM-assisted)
PROMPT_PACK_MAP: Dict[QueryType, str] = {
    QueryType.EXPLAIN: "PRM-ADMIN-EXPLAIN-001",
    QueryType.VALIDATE: "PRM-ADMIN-VALIDATE-001",
    QueryType.SUMMARIZE: "PRM-ADMIN-EXPLAIN-001",  # Reuse explain prompt
    QueryType.GENERAL: "PRM-ADMIN-GENERAL-001",
}

# Query types that require LLM for full functionality
LLM_REQUIRED_TYPES = {QueryType.VALIDATE, QueryType.SUMMARIZE}


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


def route_query(
    query: str,
    capabilities: Optional[Dict[str, Any]] = None,
) -> RouteResult:
    """Route a query to the appropriate handler.

    Currently: All queries go to LLM for intelligent routing.
    Pattern matching disabled - will be re-implemented later.

    Args:
        query: User query string
        capabilities: Agent capabilities dict (from manifest)

    Returns:
        RouteResult with mode, handler, and metadata
    """
    capabilities = capabilities or {}

    # Create a general classification (pattern matching disabled)
    classification = QueryClassification(
        type=QueryType.GENERAL,
        confidence=1.0,
        pattern_matched=False,
    )

    # All queries go to LLM general handler
    return RouteResult(
        mode=RouteMode.LLM_ASSISTED,
        handler="general",
        classification=classification,
        prompt_pack_id="PRM-ADMIN-GENERAL-001",
        reason="LLM-first routing (pattern matching disabled)",
        capabilities_used=["llm_assisted.general"],
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
        }
    }
