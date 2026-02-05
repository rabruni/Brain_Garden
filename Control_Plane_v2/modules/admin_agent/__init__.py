"""Admin Agent - Agent for explaining and validating Control Plane artifacts.

The first governed agent that operates inside the Control Plane's governance
model. Provides human-friendly explanations by wrapping trace.py, with
optional LLM-assisted capabilities for validation and synthesis.

This is a Tier 3 (T3) agent package.

Routing Modes:
- TOOLS_FIRST: Pattern-matched queries use deterministic handlers
- LLM_ASSISTED: Complex queries use governed prompts + LLM synthesis

Example usage:
    from modules.admin_agent import AdminAgent, admin_turn

    # Tools-first query (no LLM)
    result = admin_turn("What packages are installed?")

    # LLM-assisted query (requires capability)
    result = admin_turn("Summarize the frameworks")
"""

from modules.admin_agent.agent import AdminAgent, admin_turn
from modules.admin_agent.handlers import get_handler

__all__ = [
    "AdminAgent",
    "admin_turn",
    "get_handler",
]

__version__ = "0.2.0"
