"""Query Router Module.

Routes queries to appropriate handlers based on pattern matching (tools-first)
or LLM classification (when explicitly enabled).

Key Principles:
- TOOLS_FIRST is the default mode
- LLM-assisted requires explicit capability flag
- Fail-closed: no capability = TOOLS_FIRST

Example usage:
    from modules.router import route_query, classify_query, RouteResult

    # Classify a query
    classification = classify_query("What packages are installed?")
    print(classification)  # {"type": "list", "confidence": 1.0, "mode": "tools_first"}

    # Route with capabilities
    capabilities = {"llm_assisted": {"summarize": True}}
    result = route_query("Summarize the frameworks", capabilities=capabilities)
    print(result.mode)  # TOOLS_FIRST or LLM_ASSISTED
"""

from modules.router.classifier import classify_query, QueryClassification
from modules.router.decision import route_query, RouteResult, RouteMode
from modules.router.policy import load_policy, enforce_policy

__all__ = [
    "classify_query",
    "route_query",
    "load_policy",
    "enforce_policy",
    "QueryClassification",
    "RouteResult",
    "RouteMode",
]

__version__ = "0.1.0"
