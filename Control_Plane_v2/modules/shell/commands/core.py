"""Core shell commands.

Provides: :help, :quit, :clear, :state, :agent
These are handled directly in shell.py but aliases are defined here.
"""

from typing import Dict, Callable


def cmd_debug(shell, args: str) -> bool:
    """Toggle debug mode.

    Usage: :debug
    """
    shell.debug = not shell.debug
    status = "enabled" if shell.debug else "disabled"
    shell.ui.print_success(f"Debug mode {status}")

    if shell.debug:
        shell.ui.print_debug_panel(shell.agent.get_state())

    return True


def cmd_session(shell, args: str) -> bool:
    """Show session info.

    Usage: :session
    """
    shell.ui.print_system_message("Session Info")

    if shell._session:
        print(f"  Session ID: {shell._session.session_id}")
        print(f"  Tier: {shell._session.tier}")
        print(f"  Turn: {shell._turn}")
        print(f"  Ledger: {shell._session.ledger_path}")
    else:
        print("  No active session")

    return True


def cmd_version(shell, args: str) -> bool:
    """Show version info.

    Usage: :version
    """
    shell.ui.print_system_message("Version Info")
    print(f"  Shell: Universal Shell 1.0.0")
    print(f"  Agent: {shell.agent.name} v{shell.agent.version}")
    print(f"  Root: {shell.root}")
    return True


CORE_COMMANDS: Dict[str, Callable] = {
    "debug": cmd_debug,
    "session": cmd_session,
    "version": cmd_version,
    "ver": cmd_version,
}
