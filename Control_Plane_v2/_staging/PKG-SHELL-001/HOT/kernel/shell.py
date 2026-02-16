"""Human-facing command shell for the Control Plane.

Parses user input into cognitive turns or admin commands.
Delegates all cognitive processing to SessionHostV2.
Presentation layer only -- no cognitive logic.

Usage:
    shell = Shell(session_host_v2, agent_config)
    shell.run()
"""

from __future__ import annotations

from typing import Any, Callable


class Shell:
    """REPL command shell. Presentation layer only.

    Receives all dependencies via constructor injection.
    Does NOT load config. Does NOT make LLM calls.
    """

    def __init__(
        self,
        session_host_v2,
        agent_config,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self._host = session_host_v2
        self._agent_config = agent_config
        self._input_fn = input_fn
        self._output_fn = output_fn
        self._running = False
        self._session_id: str | None = None
        self._commands: dict[str, Callable] = {
            "/exit": self._handle_exit,
            "/help": self._handle_help,
            "/show frameworks": self._handle_show_frameworks,
        }

    def run(self) -> None:
        """Start the REPL loop."""
        self._session_id = self._host.start_session(self._agent_config)
        self._output_fn(f"Session started: {self._session_id}")
        self._running = True
        try:
            while self._running:
                try:
                    raw = self._input_fn("admin> ")
                except (EOFError, KeyboardInterrupt):
                    break
                text = raw.strip()
                if not text:
                    continue
                if text.startswith("/"):
                    self._dispatch_command(text)
                else:
                    self._dispatch_turn(text)
        finally:
            self._host.end_session()
            self._output_fn("Session ended.")

    def _dispatch_command(self, text: str) -> None:
        """Route a /command to its handler."""
        handler = self._commands.get(text.lower())
        if handler is None:
            for cmd, h in sorted(self._commands.items(), key=lambda x: -len(x[0])):
                if text.lower().startswith(cmd):
                    handler = h
                    break
        if handler is not None:
            handler()
        else:
            self._handle_unknown(text)

    def _dispatch_turn(self, text: str) -> None:
        """Send cognitive input to SessionHostV2."""
        result = self._host.process_turn(text)
        self._format_result(result)

    def _format_result(self, result) -> None:
        """Format a TurnResult for display."""
        self._output_fn(f"assistant: {result.response}")

    def _handle_exit(self) -> None:
        self._running = False

    def _handle_help(self) -> None:
        lines = [
            "Available commands:",
            "  /help              -- Show this help text",
            "  /show frameworks   -- List active frameworks",
            "  /exit              -- End session and exit",
            "",
            "All other input is sent as a cognitive turn.",
        ]
        self._output_fn("\n".join(lines))

    def _handle_show_frameworks(self) -> None:
        self._output_fn("Not yet implemented.")

    def _handle_unknown(self, text: str) -> None:
        self._output_fn(f"Unknown command: {text}. Type /help for available commands.")
