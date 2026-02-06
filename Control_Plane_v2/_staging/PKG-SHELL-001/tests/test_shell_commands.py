"""Tests for shell commands.

Tests command handlers in modules/shell/commands/.

Run with:
    pytest tests/test_shell_commands.py -v
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.shell.interfaces import (
    CPAgentInterface,
    CPAgentCapability,
    CPSignalBundle,
    AgentResponse,
    DefaultCPAgent,
)
from modules.shell.shell import UniversalShell
from modules.shell.chat_ui import ChatUI


class MockShell:
    """Mock shell for testing commands."""

    def __init__(self, tmp_path):
        self.agent = DefaultCPAgent(tier="ho1")
        self.root = tmp_path
        self.debug = False
        self.context_mode = "persistent"
        self._turn = 0
        self._reads_this_turn = []
        self._session = None
        self._ledger = None

        # Mock UI
        self.ui = Mock(spec=ChatUI)
        self.ui.print_system_message = Mock()
        self.ui.print_success = Mock()
        self.ui.print_error = Mock()


class TestCoreCommands:
    """Test core command handlers."""

    @pytest.fixture
    def shell(self, tmp_path):
        """Create mock shell."""
        return MockShell(tmp_path)

    def test_cmd_debug(self, shell):
        """Test :debug command."""
        from modules.shell.commands.core import cmd_debug

        # Enable debug
        shell.debug = False
        result = cmd_debug(shell, "")
        assert shell.debug is True
        shell.ui.print_success.assert_called()

        # Disable debug
        result = cmd_debug(shell, "")
        assert shell.debug is False

    def test_cmd_version(self, shell):
        """Test :version command."""
        from modules.shell.commands.core import cmd_version

        result = cmd_version(shell, "")
        assert result is True
        shell.ui.print_system_message.assert_called_with("Version Info")


class TestMemoryCommands:
    """Test memory command handlers."""

    @pytest.fixture
    def shell(self, tmp_path):
        """Create mock shell."""
        return MockShell(tmp_path)

    def test_cmd_memory_status(self, shell):
        """Test :memory command (status)."""
        from modules.shell.commands.memory import cmd_memory

        result = cmd_memory(shell, "")
        assert result is True
        shell.ui.print_system_message.assert_called_with("Memory Status")

    def test_cmd_memory_clear(self, shell):
        """Test :memory clear command."""
        from modules.shell.commands.memory import cmd_memory

        # Add some history first
        shell.agent.process("test")
        assert len(shell.agent.get_history()) > 0

        # Clear via command
        result = cmd_memory(shell, "clear")
        assert result is True


class TestSignalCommands:
    """Test signal command handlers."""

    @pytest.fixture
    def shell(self, tmp_path):
        """Create mock shell."""
        return MockShell(tmp_path)

    def test_cmd_signals(self, shell):
        """Test :sig command."""
        from modules.shell.commands.signals import cmd_signals

        result = cmd_signals(shell, "")
        assert result is True
        shell.ui.print_system_message.assert_called_with("Signal Status")

    def test_cmd_trust_not_supported(self, shell):
        """Test :trust command without capability."""
        from modules.shell.commands.signals import cmd_trust

        result = cmd_trust(shell, "")
        assert result is True
        shell.ui.print_error.assert_called()


class TestNoteCommands:
    """Test note command handlers."""

    @pytest.fixture
    def shell(self, tmp_path):
        """Create mock shell."""
        return MockShell(tmp_path)

    def test_cmd_notes_empty(self, shell):
        """Test :notes command with no notes."""
        from modules.shell.commands.notes import cmd_notes

        result = cmd_notes(shell, "")
        assert result is True

    def test_cmd_add_note_empty(self, shell):
        """Test :n+ command with no text."""
        from modules.shell.commands.notes import cmd_add_note

        result = cmd_add_note(shell, "")
        assert result is True
        shell.ui.print_error.assert_called()


class TestGovernanceCommands:
    """Test governance command handlers."""

    @pytest.fixture
    def shell(self, tmp_path):
        """Create mock shell with test data."""
        shell = MockShell(tmp_path)

        # Create test directories
        (tmp_path / "installed").mkdir(parents=True, exist_ok=True)
        (tmp_path / "ledger").mkdir(parents=True, exist_ok=True)

        return shell

    def test_cmd_pkg_list_empty(self, shell):
        """Test :pkg command with no packages."""
        from modules.shell.commands.governance import cmd_pkg

        result = cmd_pkg(shell, "")
        assert result is True
        shell.ui.print_system_message.assert_called_with("Installed Packages")

    def test_cmd_pkg_not_found(self, shell):
        """Test :pkg <id> with non-existent package."""
        from modules.shell.commands.governance import cmd_pkg

        result = cmd_pkg(shell, "PKG-NONEXISTENT")
        assert result is True
        shell.ui.print_error.assert_called()

    def test_cmd_pkg_with_manifest(self, shell):
        """Test :pkg <id> with valid manifest."""
        from modules.shell.commands.governance import cmd_pkg

        # Create test package
        pkg_dir = shell.root / "installed" / "PKG-TEST-001"
        pkg_dir.mkdir(parents=True)

        manifest = {
            "package_id": "PKG-TEST-001",
            "version": "1.0.0",
            "spec_id": "SPEC-TEST-001",
            "plane_id": "ho3",
            "assets": [{"path": "test.py", "classification": "library"}],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))

        result = cmd_pkg(shell, "PKG-TEST-001")
        assert result is True
        shell.ui.print_system_message.assert_called()

    def test_cmd_ledger_no_files(self, shell):
        """Test :ledger command with no ledger files."""
        from modules.shell.commands.governance import cmd_ledger

        result = cmd_ledger(shell, "")
        assert result is True
        shell.ui.print_system_message.assert_called_with("Ledger Entries")

    def test_cmd_ledger_with_entries(self, shell):
        """Test :ledger command with entries."""
        from modules.shell.commands.governance import cmd_ledger

        # Create test ledger
        ledger_file = shell.root / "ledger" / "governance-20260203-120000.jsonl"
        ledger_file.parent.mkdir(parents=True, exist_ok=True)

        entries = [
            {
                "event_type": "GATE_PASSED",
                "timestamp": "2026-02-03T12:00:00Z",
                "decision": "PASS",
            },
            {
                "event_type": "GATE_FAILED",
                "timestamp": "2026-02-03T12:01:00Z",
                "decision": "FAIL",
            },
        ]
        with open(ledger_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        result = cmd_ledger(shell, "")
        assert result is True

    def test_cmd_gate(self, shell):
        """Test :gate command."""
        from modules.shell.commands.governance import cmd_gate

        result = cmd_gate(shell, "")
        assert result is True
        shell.ui.print_system_message.assert_called_with("Gate Status")

    def test_cmd_wo_no_ledger(self, shell):
        """Test :wo command with no work order ledger."""
        from modules.shell.commands.governance import cmd_wo

        result = cmd_wo(shell, "")
        assert result is True
        shell.ui.print_system_message.assert_called_with("Work Orders")

    def test_cmd_compliance(self, shell):
        """Test :compliance command."""
        from modules.shell.commands.governance import cmd_compliance

        # This will fail without CPInspector, but should handle gracefully
        result = cmd_compliance(shell, "")
        assert result is True

    def test_cmd_trace_no_args(self, shell):
        """Test :trace command without arguments."""
        from modules.shell.commands.governance import cmd_trace

        result = cmd_trace(shell, "")
        assert result is True
        shell.ui.print_error.assert_called()


class TestCommandRegistry:
    """Test command registry."""

    def test_get_all_commands(self):
        """Test getting all commands."""
        from modules.shell.commands import get_all_commands

        commands = get_all_commands()
        assert isinstance(commands, dict)
        assert len(commands) > 0

        # Check some expected commands
        assert "pkg" in commands
        assert "ledger" in commands
        assert "gate" in commands
        assert "debug" in commands
        assert "memory" in commands
        assert "sig" in commands
        assert "notes" in commands

    def test_command_handlers_callable(self):
        """Test that all handlers are callable."""
        from modules.shell.commands import get_all_commands

        commands = get_all_commands()
        for name, handler in commands.items():
            assert callable(handler), f"Handler for {name} is not callable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
