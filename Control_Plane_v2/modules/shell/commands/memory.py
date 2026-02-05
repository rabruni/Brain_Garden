"""Memory and context commands.

Provides: :memory, :m, :memory clear, :memory reset
"""

from typing import Dict, Callable

from modules.shell.interfaces import CPAgentCapability


def cmd_memory(shell, args: str) -> bool:
    """Show memory/consent status.

    Usage: :memory
           :memory clear   - Clear conversation history
           :memory reset   - Reset to defaults
    """
    args_lower = args.lower().strip()

    if args_lower == "clear":
        if hasattr(shell.agent, "clear_conversation"):
            shell.agent.clear_conversation()
            shell.ui.print_success("Cleared conversation history")
        else:
            shell.ui.print_error("Agent does not support memory clearing")
        return True

    if args_lower == "reset":
        if hasattr(shell.agent, "clear_memory"):
            shell.agent.clear_memory()
            shell.ui.print_success("Memory reset")
        else:
            shell.ui.print_error("Agent does not support memory reset")
        return True

    # Show status
    shell.ui.print_system_message("Memory Status")

    if CPAgentCapability.CONSENT in shell.agent.capabilities:
        consent = shell.agent.get_consent_summary()
        if consent.get("status") == "configured":
            print(
                f"  Conversation history:  {'✓ enabled' if consent.get('conversation_history') else '✗ disabled'}"
            )
            print(
                f"  Interaction signals:   {'✓ enabled' if consent.get('interaction_signals') else '✗ disabled'}"
            )
        else:
            print("  No consent preferences configured")
    else:
        print("  Consent management not available")

    history = shell.agent.get_history() if hasattr(shell.agent, "get_history") else []
    print(f"\n  Messages in context: {len(history)}")
    print(f"  Context mode: {shell.context_mode}")

    print("\n  Commands:")
    print("    :memory clear   - Clear conversation history")
    print("    :memory reset   - Reset memory")

    return True


MEMORY_COMMANDS: Dict[str, Callable] = {
    "memory": cmd_memory,
    "m": cmd_memory,
}
