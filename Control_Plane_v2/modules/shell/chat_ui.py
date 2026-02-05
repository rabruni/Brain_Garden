"""Chat UI - Terminal interface with prompt_toolkit.

Features:
- Arrow keys and line editing
- Command history (up/down arrows)
- Proper multi-line paste support
- Clean chat bubble display
- Color-coded messages
- Compact metadata display

Adapted from _locked_system_flattened/cli/chat_ui.py for Control Plane.
"""

import os
import time
import textwrap
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from prompt_toolkit import prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style
    from prompt_toolkit.key_binding import KeyBindings

    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


class Colors:
    """ANSI color codes."""

    # Reset
    RESET = "\033[0m"

    # Regular colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_WHITE = "\033[47m"
    BG_BRIGHT_BLACK = "\033[100m"

    # Styles
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"


class ChatUI:
    """Terminal chat interface."""

    def __init__(
        self, history_file: Optional[Path] = None, terminal_width: int = None
    ):
        """Initialize chat UI.

        Args:
            history_file: Path to history file for command history
            terminal_width: Optional fixed terminal width
        """
        self.history_file = history_file or Path.home() / ".cp_shell_history"
        self.terminal_width = terminal_width or self._get_terminal_width()
        self.max_bubble_width = max(80, self.terminal_width - 6)

        # Activity tracking for status indicator
        self._activity_start: Optional[float] = None
        self._activity_type: str = "thinking"
        self._activity_durations: dict = {}
        self._last_activity_switch: Optional[float] = None

        # Setup prompt_toolkit if available
        if PROMPT_TOOLKIT_AVAILABLE:
            self.history = FileHistory(str(self.history_file))
            self.prompt_style = Style.from_dict(
                {
                    "prompt": "#5555ff bold",
                }
            )
            self.key_bindings = KeyBindings()

            @self.key_bindings.add("escape")
            def _(event):
                """Handle escape key - raise interrupt."""
                event.app.exit(exception=KeyboardInterrupt())

        else:
            self.history = None
            self.prompt_style = None
            self.key_bindings = None

    def _get_terminal_width(self) -> int:
        """Get terminal width, default to 80 if can't determine."""
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 80

    def save_history(self):
        """Save command history - handled automatically by FileHistory."""
        pass

    def cleanup(self):
        """Clean up terminal state on exit."""
        pass

    def clear_screen(self):
        """Clear terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def print_header(self, title: str = "Control Plane Shell", subtitle: str = None):
        """Print chat header."""
        width = self.terminal_width

        print()
        print(f"{Colors.BOLD}{Colors.CYAN}{'─' * width}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.WHITE}  {title}{Colors.RESET}")
        if subtitle:
            print(f"{Colors.DIM}  {subtitle}{Colors.RESET}")
        print(f"{Colors.CYAN}{'─' * width}{Colors.RESET}")
        print()

    def print_help(self):
        """Print help text."""
        help_text = f"""
{Colors.DIM}Commands (vim-style, prefix with {Colors.CYAN}:{Colors.DIM}):{Colors.RESET}
  {Colors.CYAN}:h{Colors.RESET}  {Colors.DIM}:help{Colors.RESET}         Show help
  {Colors.CYAN}:s{Colors.RESET}  {Colors.DIM}:state{Colors.RESET}        Show current state (JSON)
  {Colors.CYAN}:a{Colors.RESET}  {Colors.DIM}:agent{Colors.RESET}        Show agent info
  {Colors.CYAN}:c{Colors.RESET}  {Colors.DIM}:clear{Colors.RESET}        Clear the screen
  {Colors.CYAN}:q{Colors.RESET}  {Colors.DIM}:quit{Colors.RESET}         Quit

{Colors.DIM}Context:{Colors.RESET}
  {Colors.CYAN}:v{Colors.RESET}  {Colors.DIM}:view{Colors.RESET}         View context window
  {Colors.CYAN}:ctx{Colors.RESET}              Show context mode
  {Colors.CYAN}:ctx persistent{Colors.RESET}   Keep conversation history
  {Colors.CYAN}:ctx isolated{Colors.RESET}     Fresh context each turn

{Colors.DIM}Control Plane:{Colors.RESET}
  {Colors.CYAN}:pkg{Colors.RESET}              List installed packages
  {Colors.CYAN}:pkg <id>{Colors.RESET}         Show package details
  {Colors.CYAN}:ledger{Colors.RESET}           Show recent ledger entries
  {Colors.CYAN}:gate{Colors.RESET}             Show gate status
  {Colors.CYAN}:compliance{Colors.RESET}       Show compliance info

{Colors.DIM}Shell:{Colors.RESET}
  {Colors.CYAN}:! <cmd>{Colors.RESET}          Run shell command (e.g., :! ls -la)

{Colors.DIM}Keys:{Colors.RESET}
  Escape         Interrupt and quit
  ↑/↓            Browse command history
  ←/→            Move cursor in line
"""
        print(help_text)

    def print_user_message(self, message: str):
        """Print user message (left-aligned)."""
        # Move cursor up to overwrite the input line(s)
        prompt_len = 5
        message_display_len = len(message) + prompt_len
        wrapped_lines = (message_display_len // self.terminal_width) + 1
        input_lines = max(message.count("\n") + 1, wrapped_lines)

        for _ in range(input_lines):
            print(f"\033[A\033[K", end="")

        lines = self._wrap_text(message, bg_color=Colors.BG_BRIGHT_BLACK)
        max_line_len = max(self._visible_len(line) for line in lines) if lines else 0
        bubble_width = min(max_line_len + 4, self.max_bubble_width)

        print()
        for line in lines:
            visible_len = self._visible_len(line)
            pad_needed = bubble_width - 4 - visible_len
            padded_line = line + (" " * max(0, pad_needed))
            bubble = f"  {padded_line}  "
            print(
                f"  {Colors.BG_BRIGHT_BLACK}{Colors.WHITE}{bubble}{Colors.RESET}"
            )

        timestamp = datetime.now().strftime("%H:%M")
        print(f"  {Colors.DIM}{timestamp}{Colors.RESET}")

    def print_assistant_message(
        self,
        message: str,
        metadata: dict = None,
        signal_strip: str = None,
        mode_line: str = None,
        agent_info: dict = None,
    ):
        """Print assistant message (right-aligned, blue bubble)."""
        lines = self._wrap_text(message, bg_color=Colors.BG_BLUE)
        max_line_len = max(self._visible_len(line) for line in lines) if lines else 0
        bubble_width = min(max_line_len + 4, self.terminal_width - 4)
        padding = max(0, self.terminal_width - bubble_width - 2)

        print()

        # Agent header line
        if agent_info:
            agent_name = agent_info.get("name", "Agent")
            model = agent_info.get("model", "unknown")
            if "/" in model:
                model = model.split("/")[-1]
            if len(model) > 30:
                model = model[:27] + "..."
            header = f"{agent_name} ({model})"
            header_padding = max(0, self.terminal_width - len(header) - 2)
            print(f"{' ' * header_padding}{Colors.DIM}{header}{Colors.RESET}")

        for line in lines:
            visible_len = self._visible_len(line)
            pad_needed = bubble_width - 4 - visible_len
            padded_line = line + (" " * max(0, pad_needed))
            bubble = f"  {padded_line}  "
            print(
                f"{' ' * padding}{Colors.BG_BLUE}{Colors.WHITE}{bubble}{Colors.RESET}"
            )

        # Signal strip
        if signal_strip:
            strip_visible_len = self._visible_len(signal_strip)
            strip_padding = max(0, self.terminal_width - strip_visible_len - 2)
            print(f"{' ' * strip_padding}{signal_strip}")

        # Mode line
        if mode_line:
            mode_display = f"{Colors.DIM}Mode: {mode_line}{Colors.RESET}"
            mode_visible_len = 6 + len(mode_line)
            mode_padding = max(0, self.terminal_width - mode_visible_len - 2)
            print(f"{' ' * mode_padding}{mode_display}")
        else:
            timestamp = datetime.now().strftime("%H:%M")
            ts_padding = max(0, self.terminal_width - 7)
            print(f"{' ' * ts_padding}{Colors.DIM}{timestamp}{Colors.RESET}")

    def print_system_message(self, message: str):
        """Print system message (centered, dim)."""
        print()
        print(f"{Colors.DIM}  ── {message} ──{Colors.RESET}")

    def print_gate_transition(self, transitions: list):
        """Print gate transition notification."""
        if transitions:
            for t in transitions:
                print(f"  {Colors.YELLOW}⚡ {t}{Colors.RESET}")

    def print_error(self, message: str):
        """Print error message."""
        print(f"\n  {Colors.RED}✗ {message}{Colors.RESET}")

    def print_success(self, message: str):
        """Print success message."""
        print(f"\n  {Colors.GREEN}✓ {message}{Colors.RESET}")

    def print_thinking(self, message: str = "Thinking", activity: str = None):
        """Print thinking/waiting indicator."""
        now = time.time()
        activity = activity or "thinking"

        if self._activity_start is None:
            self._activity_start = now
            self._last_activity_switch = now
            self._activity_durations = {}

        if self._activity_type != activity and self._last_activity_switch:
            prev_duration = now - self._last_activity_switch
            self._activity_durations[self._activity_type] = (
                self._activity_durations.get(self._activity_type, 0) + prev_duration
            )
            self._last_activity_switch = now

        icons = {
            "thinking": "⋯",
            "reading": "📖",
            "writing": "✏️",
            "tool": "🔧",
            "api": "◐",
            "scanning": "🔍",
        }
        icon = icons.get(activity, "⋯")

        elapsed = now - self._activity_start
        if elapsed < 1:
            time_str = ""
        elif elapsed < 60:
            time_str = f" ({elapsed:.0f}s)"
        else:
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            time_str = f" ({mins}m {secs}s)"

        print(
            f"\r  {Colors.DIM}{icon} {message}{time_str}...{Colors.RESET}    ",
            end="",
            flush=True,
        )
        self._activity_type = activity

    def update_thinking(self, message: str, activity: str = None):
        """Update the thinking indicator."""
        self.print_thinking(message, activity)

    def clear_thinking(self) -> dict:
        """Clear the thinking indicator and return activity summary."""
        if self._last_activity_switch:
            final_duration = time.time() - self._last_activity_switch
            self._activity_durations[self._activity_type] = (
                self._activity_durations.get(self._activity_type, 0) + final_duration
            )

        durations = self._activity_durations.copy()
        total = time.time() - self._activity_start if self._activity_start else 0

        self._activity_start = None
        self._activity_type = "thinking"
        self._last_activity_switch = None

        print(f"\r{' ' * 60}\r", end="", flush=True)

        return {"activities": durations, "total": total}

    def print_activity_summary(self, summary: dict):
        """Print activity duration summary."""
        activities = summary.get("activities", {})
        total = summary.get("total", 0)

        all_activities = [
            ("api", "◐", "api"),
            ("reading", "📖", "read"),
            ("scanning", "🔍", "scan"),
            ("thinking", "⋯", "think"),
            ("tool", "🔧", "tool"),
            ("writing", "✏️", "write"),
        ]

        parts = []
        for key, icon, label in all_activities:
            secs = activities.get(key, 0.0)
            parts.append(f"{icon}{label}:{secs:.1f}s")

        standard_keys = {a[0] for a in all_activities}
        for key, secs in activities.items():
            if key not in standard_keys:
                parts.append(f"·{key}:{secs:.1f}s")

        summary_str = "  ".join(parts)
        total_str = f"{total:.1f}s"

        print(f"  {Colors.DIM}{summary_str}  | {total_str}{Colors.RESET}")

    def print_notes(self, notes: list, title: str = "Notes"):
        """Print notes in a readable format."""
        width = self.terminal_width

        print()
        print(f"{Colors.DIM}{'─' * width}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}  {title}{Colors.RESET}")
        print(f"{Colors.DIM}{'─' * width}{Colors.RESET}")

        if not notes:
            print(f"  {Colors.DIM}No notes found{Colors.RESET}")
            print(f"{Colors.DIM}{'─' * width}{Colors.RESET}")
            return

        for note in notes:
            timestamp = note.get("timestamp", "Unknown time")
            content = note.get("content", "")
            note_type = note.get("type", "unknown")

            if note_type == "developer":
                type_badge = f"{Colors.YELLOW}DEV{Colors.RESET}"
            else:
                type_badge = f"{Colors.MAGENTA}PERSONAL{Colors.RESET}"

            print()
            print(f"  {type_badge} {Colors.DIM}{timestamp}{Colors.RESET}")

            content_lines = content.split("\n")
            for line in content_lines[:5]:
                if len(line) > width - 6:
                    line = line[: width - 9] + "..."
                print(f"  {Colors.WHITE}{line}{Colors.RESET}")

            if len(content_lines) > 5:
                print(
                    f"  {Colors.DIM}... ({len(content_lines) - 5} more lines){Colors.RESET}"
                )

        print()
        print(f"{Colors.DIM}{'─' * width}{Colors.RESET}")

    def print_debug_panel(self, state: dict):
        """Print debug panel showing full system state."""
        width = self.terminal_width

        print()
        print(f"{Colors.DIM}{'─' * width}{Colors.RESET}")
        print(f"{Colors.YELLOW}{Colors.BOLD}  DEBUG STATE{Colors.RESET}")
        print(f"{Colors.DIM}{'─' * width}{Colors.RESET}")

        # Turn counter
        turn = state.get("turn", 0)
        print(f"  {Colors.DIM}Turn:{Colors.RESET} {Colors.WHITE}{turn}{Colors.RESET}")
        print()

        # Tier
        tier = state.get("tier", "unknown")
        print(f"  {Colors.BOLD}TIER{Colors.RESET}")
        print(f"  {Colors.DIM}└─{Colors.RESET} {Colors.CYAN}{tier}{Colors.RESET}")
        print()

        # Capabilities
        caps = state.get("capabilities", [])
        print(f"  {Colors.BOLD}CAPABILITIES{Colors.RESET}")
        if caps:
            for cap in caps:
                print(
                    f"  {Colors.DIM}├─{Colors.RESET} {Colors.GREEN}{cap}{Colors.RESET}"
                )
        else:
            print(f"  {Colors.DIM}└─ none{Colors.RESET}")

        print(f"{Colors.DIM}{'─' * width}{Colors.RESET}")

    def get_input(self, prompt_text: str = "You") -> str:
        """Get user input."""
        try:
            if PROMPT_TOOLKIT_AVAILABLE:
                user_input = prompt(
                    f"\n{prompt_text}: ",
                    history=self.history,
                    style=self.prompt_style,
                    key_bindings=self.key_bindings,
                    multiline=False,
                    enable_open_in_editor=False,
                )
                return user_input.strip()
            else:
                return input(f"\n{prompt_text}: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"

    def _wrap_text(self, text: str, bg_color: str = None) -> list:
        """Wrap text to fit in bubble."""
        text = text.replace("\r\n", "\n")
        has_table = bool(re.search(r"[┌┬┐├┼┤└┴┘│─]", text))
        has_code_block = "```" in text
        is_structured = has_table or has_code_block

        paragraphs = re.split(r"\n\s*\n", text)

        all_lines = []
        for i, para in enumerate(paragraphs):
            lines = para.split("\n")
            for line in lines:
                if line.strip():
                    if is_structured or re.search(r"[┌┬┐├┼┤└┴┘│─]", line):
                        all_lines.append(line)
                    elif re.match(r"^[-*•]\s|^\d+\.\s", line.strip()):
                        wrapped = textwrap.wrap(
                            line,
                            width=self.max_bubble_width - 4,
                            break_long_words=False,
                            break_on_hyphens=False,
                            subsequent_indent="  ",
                        )
                        all_lines.extend(wrapped if wrapped else [line])
                    else:
                        wrapped = textwrap.wrap(
                            line,
                            width=self.max_bubble_width - 4,
                            break_long_words=False,
                            break_on_hyphens=False,
                        )
                        all_lines.extend(wrapped if wrapped else [line])
                else:
                    all_lines.append("")

            if i < len(paragraphs) - 1:
                all_lines.append("")

        all_lines = [
            self._process_markdown(line, bg_color=bg_color) for line in all_lines
        ]

        while all_lines and all_lines[-1] == "":
            all_lines.pop()

        return all_lines if all_lines else [""]

    def _visible_len(self, text: str) -> int:
        """Get visible length of text (excluding ANSI codes)."""
        ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
        return len(ansi_escape.sub("", text))

    def _process_markdown(self, text: str, bg_color: str = None) -> str:
        """Convert markdown to terminal formatting."""
        if bg_color:
            restore = f"{Colors.RESET}{bg_color}{Colors.WHITE}"
        else:
            restore = f"{Colors.RESET}{Colors.WHITE}"

        # Bold
        text = re.sub(r"\*\*(.+?)\*\*", f"{Colors.BOLD}\\1{restore}", text)
        text = re.sub(r"__(.+?)__", f"{Colors.BOLD}\\1{restore}", text)

        # Italic
        text = re.sub(
            r"(?<!\*)\*([^*]+?)\*(?!\*)", f"{Colors.ITALIC}\\1{restore}", text
        )

        # Code
        text = re.sub(r"`([^`]+?)`", f"{Colors.DIM}\\1{restore}", text)

        # Headers
        text = re.sub(
            r"^#+\s*(.+)$", f"{Colors.BOLD}\\1{restore}", text, flags=re.MULTILINE
        )

        # Bullets
        text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

        return text


def create_chat_ui(history_file: Optional[Path] = None) -> ChatUI:
    """Create and return a ChatUI instance."""
    return ChatUI(history_file)
