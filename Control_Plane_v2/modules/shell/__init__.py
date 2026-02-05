"""Universal Shell for Control Plane.

Provides a rich terminal interface for interacting with the Control Plane,
featuring vim-style commands, signal visualization, session management,
and ledger integration.

Example:
    from modules.shell import UniversalShell, CPAgentInterface
    from modules.shell import create_default_agent

    agent = create_default_agent()
    shell = UniversalShell(agent, debug=True)
    shell.run()
"""

from modules.shell.interfaces import (
    CPAgentInterface,
    CPAgentCapability,
    CPSignalBundle,
    AgentResponse,
)
from modules.shell.shell import UniversalShell, create_default_agent
from modules.shell.chat_ui import ChatUI, Colors

__all__ = [
    "UniversalShell",
    "CPAgentInterface",
    "CPAgentCapability",
    "CPSignalBundle",
    "AgentResponse",
    "ChatUI",
    "Colors",
    "create_default_agent",
]
