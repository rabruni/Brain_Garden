"""Universal Shell - Main shell for Control Plane interaction.

This shell provides a consistent interface for interacting with the Control Plane,
featuring vim-style commands, signal visualization, session management,
and ledger integration.

Adapted from _locked_system_flattened/shell/main.py with CP integration.

Usage:
    python scripts/shell.py                    # Default agent
    python scripts/shell.py --debug            # Enable debug mode
"""

import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from modules.shell.interfaces import (
    CPAgentInterface,
    CPAgentCapability,
    CPSignalBundle,
    AgentResponse,
    DefaultCPAgent,
)
from modules.shell.chat_ui import ChatUI, Colors


class UniversalShell:
    """Universal shell for Control Plane interaction."""

    def __init__(
        self,
        agent: CPAgentInterface,
        debug: bool = False,
        root: Optional[Path] = None,
    ):
        """Initialize shell with an agent.

        Args:
            agent: Any CPAgentInterface implementation
            debug: Enable debug mode
            root: Control Plane root directory
        """
        self.agent = agent
        self.debug = debug
        self.root = root or self._get_default_root()

        # Context mode: 'persistent' (default) or 'isolated' (reset each turn)
        self.context_mode = "persistent"

        # Initialize UI with agent-specific history file
        history_file = self.root / "tmp" / f".shell_history_{agent.name}"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        self.ui = ChatUI(history_file)

        # Session and ledger integration
        self._session = None
        self._ledger = None
        self._turn = 0
        self._reads_this_turn = []

        # Command handlers (populated by command modules)
        self._command_handlers: Dict[str, callable] = {}
        self._load_commands()

    def _get_default_root(self) -> Path:
        """Get default Control Plane root."""
        current = Path(__file__).resolve()
        while current.name != "Control_Plane_v2" and current.parent != current:
            current = current.parent
        if current.name == "Control_Plane_v2":
            return current
        return Path.cwd()

    def _load_commands(self):
        """Load command handlers from commands/ module."""
        try:
            from modules.shell.commands import get_all_commands

            self._command_handlers = get_all_commands()
        except ImportError:
            # Fallback to built-in commands
            self._command_handlers = {}

    def _start_session(self):
        """Start a CP session for ledger logging."""
        try:
            from modules.agent_runtime.session import Session
            from modules.agent_runtime.ledger_writer import LedgerWriter

            self._session = Session(tier="ho1", root=self.root)
            self._session.start()
            self._ledger = LedgerWriter(self._session)
        except ImportError:
            # Session not available, continue without ledger
            self._session = None
            self._ledger = None

    def _end_session(self):
        """End CP session."""
        if self._session:
            self._session.end()

    def _log_command(self, command: str, result: str, status: str = "ok"):
        """Log command to ledger."""
        if not self._ledger:
            return

        try:
            from modules.stdlib_evidence import hash_json

            self._ledger.write_turn(
                turn_number=self._turn,
                exec_entry={
                    "command": command,
                    "command_hash": hash_json({"cmd": command}),
                    "result_hash": hash_json({"result": result[:1000]}),
                    "status": status,
                },
                evidence_entry={
                    "declared_reads": self._reads_this_turn,
                    "declared_writes": [],
                    "external_calls": [],
                },
            )
        except ImportError:
            pass
        finally:
            self._reads_this_turn = []

    def run(self):
        """Run the interactive shell."""
        # Start session
        self._start_session()

        # Show header
        subtitle = f"{self.agent.name} v{self.agent.version}"
        if self.debug:
            subtitle += " | DEBUG"
        if self._session:
            subtitle += f" | {self._session.session_id}"
        self.ui.print_header("Control Plane Shell", subtitle)

        # Show startup synopsis
        self._show_startup_synopsis()

        # Show help
        self.ui.print_help()

        # Show initial state in debug mode
        if self.debug:
            self.ui.print_debug_panel(self.agent.get_state())

        # Main loop
        try:
            self._run_loop()
        finally:
            self._end_session()

    def _show_startup_synopsis(self):
        """Show a brief synopsis at startup."""
        history = self.agent.get_history() if hasattr(self.agent, "get_history") else []

        if not history:
            print(
                f"\n  {Colors.DIM}Starting fresh session - no previous context.{Colors.RESET}"
            )
            return

        print(
            f"\n  {Colors.CYAN}╭─ SESSION CONTEXT ────────────────────────────────────╮{Colors.RESET}"
        )
        print(
            f"  {Colors.CYAN}│{Colors.RESET} {Colors.BOLD}Messages in context:{Colors.RESET} {len(history)}"
        )
        print(
            f"  {Colors.CYAN}╰──────────────────────────────────────────────────────╯{Colors.RESET}"
        )
        print()

    def _show_context_window(self):
        """Display the current context window."""
        history = self.agent.get_history() if hasattr(self.agent, "get_history") else []

        mode_icon = "🔄" if self.context_mode == "persistent" else "🔒"
        print(f"\n  ╭─ CONTEXT WINDOW ─────────────────────────────────────╮")
        print(
            f"  │  Mode: {mode_icon} {self.context_mode.upper():12}  Messages: {len(history):3}           │"
        )
        print(f"  ╰────────────────────────────────────────────────────────╯")

        if not history:
            print(f"  {Colors.DIM}(empty){Colors.RESET}")
            return

        total_chars = sum(len(msg.get("content", "")) for msg in history)
        est_tokens = total_chars // 4
        print(f"  {Colors.DIM}~{est_tokens:,} tokens estimated{Colors.RESET}\n")

        for i, msg in enumerate(history):
            role = msg.get("role", "?")
            content = msg.get("content", "")

            if role == "user":
                role_display = f"{Colors.CYAN}USER{Colors.RESET}"
            elif role == "assistant":
                role_display = f"{Colors.GREEN}ASST{Colors.RESET}"
            else:
                role_display = f"{Colors.DIM}{role.upper()[:4]}{Colors.RESET}"

            max_preview = 120
            if len(content) > max_preview:
                preview = content[:max_preview].replace("\n", " ") + "..."
            else:
                preview = content.replace("\n", " ")

            print(f"  {i+1:2}. [{role_display}] {preview}")

        print()

    def _run_loop(self):
        """Main input/output loop."""
        while True:
            try:
                user_input = self.ui.get_input()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith(":"):
                    if self._handle_command(user_input[1:].strip()):
                        continue

                # Display user message
                self.ui.print_user_message(user_input)
                self._turn += 1

                # Show thinking indicator
                self.ui.print_thinking("Processing", "thinking")

                # Clear context if in isolated mode
                if self.context_mode == "isolated" and hasattr(
                    self.agent, "clear_memory"
                ):
                    self.agent.clear_memory()

                # Process through agent
                response = self.agent.process(user_input)

                # Clear thinking
                activity_summary = self.ui.clear_thinking()

                # Show activity summary
                if activity_summary.get("total", 0) > 0.5:
                    self.ui.print_activity_summary(activity_summary)

                # Get signal strip
                signal_strip = response.signals.to_compact_display()

                # Build agent info
                agent_info = {
                    "name": self.agent.name,
                    "model": self.agent.get_config().get("model", "default"),
                }

                # Display response
                self.ui.print_assistant_message(
                    response.text,
                    signal_strip=signal_strip,
                    agent_info=agent_info,
                )

                # Show gate transitions
                if response.gate_transitions:
                    self.ui.print_gate_transition(response.gate_transitions)

                # Debug panel
                if self.debug:
                    self.ui.print_debug_panel(self.agent.get_state())

                # Log to ledger
                self._log_command(
                    f"query: {user_input[:100]}",
                    response.text[:500],
                    "ok" if not response.error else "error",
                )

            except KeyboardInterrupt:
                print()
                self.ui.print_system_message("Interrupted. Goodbye!")
                self._log_command("interrupt", "session ended", "interrupt")
                self.ui.cleanup()
                break
            except Exception as e:
                self.ui.print_error(str(e))
                self._log_command(f"error", str(e), "error")

    def _handle_command(self, cmd: str) -> bool:
        """Handle a shell command.

        Returns True if command was handled, False to pass to agent.
        """
        cmd_lower = cmd.lower()

        # Clear the input line
        print(f"\033[A\033[K", end="")
        self._turn += 1

        # Core commands (always available)
        if cmd_lower in ["q", "quit", "exit"]:
            self.ui.print_system_message("Goodbye!")
            self._log_command(":quit", "session ended", "ok")
            self.ui.cleanup()
            raise KeyboardInterrupt

        if cmd_lower in ["h", "help"]:
            self._print_help()
            self._log_command(":help", "help displayed", "ok")
            return True

        if cmd_lower in ["c", "clear"]:
            self.ui.clear_screen()
            subtitle = f"{self.agent.name}"
            if self.debug:
                subtitle += " | DEBUG"
            self.ui.print_header("Control Plane Shell", subtitle)
            self._log_command(":clear", "screen cleared", "ok")
            return True

        if cmd_lower in ["s", "state"]:
            state = self.agent.get_state()
            self.ui.print_system_message("Current State")
            print(json.dumps(state, indent=2, default=str))
            self._log_command(":state", "state displayed", "ok")
            return True

        if cmd_lower in ["a", "agent"]:
            caps = ", ".join(c.value for c in self.agent.capabilities)
            self.ui.print_system_message(
                f"Agent: {self.agent.name} v{self.agent.version}"
            )
            print(f"  Capabilities: {caps}")
            self._log_command(":agent", "agent info displayed", "ok")
            return True

        # View context window
        if cmd_lower in ["v", "vi", "view"]:
            self._show_context_window()
            self._log_command(":view", "context window displayed", "ok")
            return True

        # Context mode commands
        if cmd_lower in ["ctx", "context"]:
            mode_icon = "🔄" if self.context_mode == "persistent" else "🔒"
            print(f"\n  Context Mode: {mode_icon} {self.context_mode.upper()}")
            print()
            print(
                f"  {Colors.DIM}persistent = full conversation history sent to LLM{Colors.RESET}"
            )
            print(
                f"  {Colors.DIM}isolated   = only current prompt sent to LLM{Colors.RESET}"
            )
            print(f"\n  Use :ctx persistent  or  :ctx isolated  to change")
            self._log_command(":ctx", f"mode: {self.context_mode}", "ok")
            return True

        if cmd_lower in ["ctx persistent", "context persistent"]:
            self.context_mode = "persistent"
            if hasattr(self.agent, "set_ephemeral_mode"):
                self.agent.set_ephemeral_mode(False)
            if hasattr(self.agent, "reload_conversation_history"):
                self.agent.reload_conversation_history()
            self.ui.print_success("Context mode: PERSISTENT")
            self._log_command(":ctx persistent", "mode changed", "ok")
            return True

        if cmd_lower in ["ctx isolated", "context isolated"]:
            self.context_mode = "isolated"
            if hasattr(self.agent, "set_ephemeral_mode"):
                self.agent.set_ephemeral_mode(True)
            if hasattr(self.agent, "clear_memory"):
                self.agent.clear_memory()
            self.ui.print_success("Context mode: ISOLATED")
            self._log_command(":ctx isolated", "mode changed", "ok")
            return True

        # Shell passthrough
        if cmd.startswith("!"):
            shell_cmd = cmd[1:].strip()
            if shell_cmd:
                self._run_shell_command(shell_cmd)
                self._log_command(f":! {shell_cmd}", "shell command executed", "ok")
            else:
                self.ui.print_error("Usage: :! <command>")
            return True

        # Try command handlers
        parts = cmd.split(None, 1)
        cmd_name = parts[0].lower() if parts else ""
        cmd_args = parts[1] if len(parts) > 1 else ""

        if cmd_name in self._command_handlers:
            try:
                result = self._command_handlers[cmd_name](self, cmd_args)
                self._log_command(f":{cmd}", "command executed", "ok")
                return result
            except Exception as e:
                self.ui.print_error(f"Command error: {e}")
                self._log_command(f":{cmd}", str(e), "error")
                return True

        # Check agent-specific commands
        custom_commands = self.agent.get_custom_commands()
        for handler_name, handler in custom_commands.items():
            if cmd_lower == handler_name or cmd_lower.startswith(f"{handler_name} "):
                args = cmd[len(handler_name) :].strip() if " " in cmd else ""
                try:
                    if handler(self, args):
                        self._log_command(f":{cmd}", "custom command", "ok")
                        return True
                except Exception as e:
                    self.ui.print_error(f"Command error: {e}")
                    self._log_command(f":{cmd}", str(e), "error")
                    return True

        # Unknown command
        self.ui.print_error(f"Unknown command: {cmd}")
        self._log_command(f":{cmd}", "unknown command", "error")
        return True

    def _run_shell_command(self, command: str):
        """Run a shell command and display output."""
        import subprocess

        print()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.root),
            )
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(f"\033[31m{result.stderr}\033[0m")
            if result.returncode != 0:
                print(f"\033[2mExit code: {result.returncode}\033[0m")
        except subprocess.TimeoutExpired:
            self.ui.print_error("Command timed out (30s)")
        except Exception as e:
            self.ui.print_error(str(e))

    def _print_help(self):
        """Print help message."""
        self.ui.print_help()

        # Show agent-specific commands
        custom_commands = self.agent.get_custom_commands()
        if custom_commands:
            print(f"\n{Colors.DIM}Agent Commands:{Colors.RESET}")
            for cmd_name in custom_commands:
                print(f"  {Colors.CYAN}:{cmd_name}{Colors.RESET}")
            print()


def create_default_agent(tier: str = "ho1") -> CPAgentInterface:
    """Create a default CP agent.

    Args:
        tier: Operating tier (ho1, ho2, ho3)

    Returns:
        DefaultCPAgent instance
    """
    return DefaultCPAgent(tier=tier)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Control Plane Universal Shell")
    parser.add_argument(
        "--agent",
        "-a",
        type=str,
        default="default",
        help="Agent to use (default)",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug mode",
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="ho1",
        choices=["ho1", "ho2", "ho3"],
        help="Operating tier",
    )

    args = parser.parse_args()

    # Create agent
    agent = create_default_agent(tier=args.tier)

    # Run shell
    shell = UniversalShell(agent, debug=args.debug)
    shell.run()


if __name__ == "__main__":
    main()
