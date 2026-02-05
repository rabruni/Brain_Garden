"""Shell command handlers.

This module provides modular command handlers for the Universal Shell.
Each submodule defines handlers for a category of commands.

Usage:
    from modules.shell.commands import get_all_commands

    handlers = get_all_commands()
    # handlers is a dict of {command_name: handler_function}
"""

from typing import Dict, Callable

from modules.shell.commands.core import CORE_COMMANDS
from modules.shell.commands.memory import MEMORY_COMMANDS
from modules.shell.commands.signals import SIGNAL_COMMANDS
from modules.shell.commands.notes import NOTE_COMMANDS
from modules.shell.commands.governance import GOVERNANCE_COMMANDS


def get_all_commands() -> Dict[str, Callable]:
    """Get all command handlers merged into single dict.

    Returns:
        Dict mapping command names to handler functions.
        Handler signature: (shell: UniversalShell, args: str) -> bool
    """
    commands = {}
    commands.update(CORE_COMMANDS)
    commands.update(MEMORY_COMMANDS)
    commands.update(SIGNAL_COMMANDS)
    commands.update(NOTE_COMMANDS)
    commands.update(GOVERNANCE_COMMANDS)
    return commands


__all__ = ["get_all_commands"]
