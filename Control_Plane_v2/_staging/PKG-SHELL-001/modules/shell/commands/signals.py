"""Signal display commands.

Provides: :sig, :signals, :trust, :learn
"""

from typing import Dict, Callable

from modules.shell.interfaces import CPAgentCapability
from modules.shell.chat_ui import Colors


def cmd_signals(shell, args: str) -> bool:
    """Show detailed signal information.

    Usage: :sig
           :signals
    """
    shell.ui.print_system_message("Signal Status")

    signals = shell.agent.get_signals()

    # Core signals
    print(f"\n  {Colors.BOLD}Core Signals{Colors.RESET}")
    print(f"  ├─ Stance:    {Colors.CYAN}{signals.stance}{Colors.RESET}")
    print(f"  ├─ Altitude:  {signals.altitude}")
    print(f"  ├─ Turn:      #{signals.turn_number}")
    print(f"  └─ Health:    {signals.health}")

    # Quality signals
    print(f"\n  {Colors.BOLD}Quality{Colors.RESET}")
    print(f"  ├─ Drift:     {signals.drift:.2f}")
    if signals.trust_level is not None:
        print(f"  └─ Trust:     {signals.trust_level:.2f}")
    else:
        print(f"  └─ Trust:     {Colors.DIM}not available{Colors.RESET}")

    # CP signals
    print(f"\n  {Colors.BOLD}Control Plane{Colors.RESET}")
    print(f"  ├─ Tier:      {signals.tier}")
    print(f"  ├─ Role:      {signals.role or 'none'}")
    print(f"  ├─ Work Order: {signals.active_wo or 'none'}")
    print(f"  ├─ Ledger:    {'synced' if signals.ledger_synced else 'pending'}")
    print(f"  └─ Gate:      {signals.gate_state}")

    # Compact display
    print(f"\n  {Colors.BOLD}Compact:{Colors.RESET} {signals.to_compact_display()}")

    return True


def cmd_trust(shell, args: str) -> bool:
    """Show trust panel.

    Usage: :trust
           :t
    """
    if CPAgentCapability.TRUST in shell.agent.capabilities:
        panel = shell.agent.get_trust_panel()
        print(panel)
    else:
        shell.ui.print_error("Agent does not support trust system")
        print(f"\n  {Colors.DIM}Trust tracking requires TRUST capability.{Colors.RESET}")
    return True


def cmd_learn(shell, args: str) -> bool:
    """Show learning panel.

    Usage: :learn
           :l
    """
    if CPAgentCapability.TRUST in shell.agent.capabilities:
        panel = shell.agent.get_learning_panel()
        print(panel)
    else:
        shell.ui.print_error("Agent does not support learning system")
        print(
            f"\n  {Colors.DIM}Learning tracking requires TRUST capability.{Colors.RESET}"
        )
    return True


SIGNAL_COMMANDS: Dict[str, Callable] = {
    "sig": cmd_signals,
    "signals": cmd_signals,
    "trust": cmd_trust,
    "t": cmd_trust,
    "learn": cmd_learn,
    "l": cmd_learn,
    "learning": cmd_learn,
}
