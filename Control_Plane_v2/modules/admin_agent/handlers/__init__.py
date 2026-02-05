"""Admin Agent Handlers.

Provides handlers for different query types, separated by routing mode:
- tools_first: Deterministic handlers using trace.py and registries
- llm_assisted: LLM-enhanced handlers using governed prompts

Example:
    from modules.admin_agent.handlers import get_handler

    handler = get_handler("list_installed", mode="tools_first")
    result = handler(agent, query)
"""

from typing import Callable, Optional

from modules.router.decision import RouteMode


def get_handler(
    handler_name: str,
    mode: RouteMode = RouteMode.TOOLS_FIRST,
) -> Optional[Callable]:
    """Get handler function by name and mode.

    Args:
        handler_name: Name of the handler
        mode: Routing mode (tools_first or llm_assisted)

    Returns:
        Handler function or None if not found
    """
    if mode == RouteMode.TOOLS_FIRST:
        from modules.admin_agent.handlers import tools_first
        return getattr(tools_first, handler_name, None)
    elif mode == RouteMode.LLM_ASSISTED:
        from modules.admin_agent.handlers import llm_assisted
        return getattr(llm_assisted, handler_name, None)
    else:
        return None


__all__ = ["get_handler"]
