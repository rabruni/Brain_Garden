"""Tests for Shell -- human-facing command shell."""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import Any

import pytest

# Add package kernel to path
_pkg = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_pkg / "HOT" / "kernel"))

from shell import Shell


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------

@dataclass
class MockAgentConfig:
    agent_id: str = "ADMIN"
    agent_class: str = "ADMIN"
    framework_id: str = "FMWK-107"
    tier: str = "HOT"
    system_prompt: str = "You are an admin."
    attention: dict = field(default_factory=dict)
    tools: list = field(default_factory=list)
    budget: dict = field(default_factory=dict)
    permissions: dict = field(default_factory=dict)


class MockTurnResult:
    def __init__(self, response="Echo response"):
        self.response = response


class MockSessionHostV2:
    def __init__(self):
        self.started = False
        self.ended = False
        self.turns = []

    def start_session(self, agent_config=None):
        self.started = True
        return "SES-MOCK-001"

    def end_session(self):
        self.ended = True

    def process_turn(self, message):
        self.turns.append(message)
        return MockTurnResult(response=f"Echo: {message}")


def make_input_fn(lines):
    """Create an input_fn that returns lines in sequence, then raises EOFError."""
    it = iter(lines)
    def input_fn(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError()
    return input_fn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCognitiveTurn:
    def test_cognitive_turn_dispatched(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["hello"]), output_fn=output.append)
        shell.run()
        assert "hello" in host.turns

    def test_output_formatting(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["hello"]), output_fn=output.append)
        shell.run()
        assert any("assistant:" in line and "Echo: hello" in line for line in output)


class TestCommandParsing:
    def test_admin_command_parsed(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["/help"]), output_fn=output.append)
        shell.run()
        assert len(host.turns) == 0  # /help should NOT go to process_turn
        assert any("Available commands" in line or "/help" in line for line in output)

    def test_help_command(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["/help"]), output_fn=output.append)
        shell.run()
        help_output = "\n".join(output)
        assert "/help" in help_output
        assert "/exit" in help_output

    def test_exit_command(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["/exit"]), output_fn=output.append)
        shell.run()
        assert host.ended

    def test_unknown_command(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["/foo"]), output_fn=output.append)
        shell.run()
        assert any("Unknown command" in line for line in output)


class TestSessionLifecycle:
    def test_session_starts_on_run(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn([]), output_fn=output.append)
        shell.run()
        assert host.started

    def test_session_ends_on_exit(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["/exit"]), output_fn=output.append)
        shell.run()
        assert host.ended


class TestEdgeCases:
    def test_empty_input_handled(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["", "  ", "hello"]), output_fn=output.append)
        shell.run()
        assert host.turns == ["hello"]  # Only "hello", not empty strings

    def test_config_not_loaded(self):
        """Shell has no config-loading code; receives dependencies only via __init__."""
        import ast
        shell_path = Path(__file__).resolve().parents[2] / "HOT" / "kernel" / "shell.py"
        tree = ast.parse(shell_path.read_text())
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        for imp in imports:
            if isinstance(imp, ast.ImportFrom) and imp.module:
                assert "main" not in imp.module, "Shell must not import from main.py"
                assert "load_config" not in imp.module, "Shell must not load config"

    def test_io_injection(self):
        host = MockSessionHostV2()
        captured = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn(["hello"]), output_fn=captured.append)
        shell.run()
        assert len(captured) > 0  # output_fn was called

    def test_eof_ends_loop(self):
        host = MockSessionHostV2()
        output = []
        shell = Shell(host, MockAgentConfig(), input_fn=make_input_fn([]), output_fn=output.append)
        shell.run()
        assert host.ended
        assert any("Session ended" in line for line in output)

    def test_keyboard_interrupt_ends_loop(self):
        host = MockSessionHostV2()
        output = []
        call_count = 0
        def interrupt_input(prompt=""):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KeyboardInterrupt()
            raise EOFError()
        shell = Shell(host, MockAgentConfig(), input_fn=interrupt_input, output_fn=output.append)
        shell.run()
        assert host.ended
