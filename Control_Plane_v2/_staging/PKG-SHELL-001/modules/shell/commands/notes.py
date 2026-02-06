"""Note management commands.

Provides: :notes, :n, :nd, :np, :n+, :nd+
"""

from typing import Dict, Callable

from modules.shell.interfaces import CPAgentCapability


def cmd_notes(shell, args: str) -> bool:
    """Show notes.

    Usage: :notes          - Show all notes
           :n              - Show all notes
           :notes dev      - Show developer notes
           :notes personal - Show personal notes
    """
    args_lower = args.lower().strip()

    if args_lower in ["dev", "developer"]:
        notes = shell.agent.get_notes("developer", n=10)
        shell.ui.print_notes(notes, "Developer Notes")
    elif args_lower in ["personal", "pers"]:
        notes = shell.agent.get_notes("personal", n=10)
        shell.ui.print_notes(notes, "Personal Notes")
    else:
        notes = shell.agent.get_notes(n=10)
        shell.ui.print_notes(notes, "Recent Notes (all)")

    return True


def cmd_notes_dev(shell, args: str) -> bool:
    """Show developer notes.

    Usage: :nd
    """
    notes = shell.agent.get_notes("developer", n=10)
    shell.ui.print_notes(notes, "Developer Notes")
    return True


def cmd_notes_personal(shell, args: str) -> bool:
    """Show personal notes.

    Usage: :np
    """
    notes = shell.agent.get_notes("personal", n=10)
    shell.ui.print_notes(notes, "Personal Notes")
    return True


def cmd_add_note(shell, args: str) -> bool:
    """Add a personal note.

    Usage: :n+ <note text>
    """
    if not args.strip():
        shell.ui.print_error("Usage: :n+ <note text>")
        return True

    result = shell.agent.add_note(args.strip(), "personal")
    if result.get("success"):
        shell.ui.print_success("Personal note added")
    else:
        shell.ui.print_error(result.get("message", "Failed to add note"))

    return True


def cmd_add_dev_note(shell, args: str) -> bool:
    """Add a developer note.

    Usage: :nd+ <note text>
    """
    if not args.strip():
        shell.ui.print_error("Usage: :nd+ <note text>")
        return True

    result = shell.agent.add_note(args.strip(), "developer")
    if result.get("success"):
        shell.ui.print_success("Developer note added")
    else:
        shell.ui.print_error(result.get("message", "Failed to add note"))

    return True


NOTE_COMMANDS: Dict[str, Callable] = {
    "notes": cmd_notes,
    "n": cmd_notes,
    "nd": cmd_notes_dev,
    "np": cmd_notes_personal,
    "n+": cmd_add_note,
    "nd+": cmd_add_dev_note,
}
