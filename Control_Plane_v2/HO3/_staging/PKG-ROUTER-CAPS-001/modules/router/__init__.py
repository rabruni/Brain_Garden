"""Query Router Module.

Routes queries to appropriate handlers based on LLM classification.
Router routes. Handler handles. Each handler decides its own execution strategy.

Example usage:
    from modules.router import route_query, RouteResult, gather_capabilities

    # Route to handler (auto-gathers capabilities)
    result = route_query("Summarize the frameworks")
    print(result.handler)  # "summarize"

    # Explicitly gather capabilities
    caps = gather_capabilities()
    result = route_query("list packages", capabilities=caps)
"""

from modules.router.decision import route_query, RouteResult, RouteMode
from modules.router.capabilities import gather_capabilities

__all__ = [
    "route_query",
    "gather_capabilities",
    "RouteResult",
    "RouteMode",
]

__version__ = "0.3.0"
