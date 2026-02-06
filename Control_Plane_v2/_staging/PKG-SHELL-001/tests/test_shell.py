"""Tests for Universal Shell.

Tests shell initialization, session management, and core functionality.

Run with:
    pytest tests/test_shell.py -v
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.shell.interfaces import (
    CPAgentInterface,
    CPAgentCapability,
    CPSignalBundle,
    AgentResponse,
    DefaultCPAgent,
)
from modules.shell.shell import UniversalShell, create_default_agent
from modules.shell.chat_ui import ChatUI, Colors


class TestDefaultCPAgent:
    """Test DefaultCPAgent implementation."""

    def test_init(self):
        """Test agent initialization."""
        agent = DefaultCPAgent(tier="ho1")
        assert agent.name == "cp_default"
        assert agent.version == "1.0.0"
        assert agent._tier == "ho1"
        assert agent._turn == 0

    def test_capabilities(self):
        """Test agent capabilities."""
        agent = DefaultCPAgent()
        caps = agent.capabilities
        assert CPAgentCapability.GOVERNANCE in caps
        assert CPAgentCapability.LEDGER in caps
        assert CPAgentCapability.PACKAGE_MGT in caps

    def test_process(self):
        """Test agent processing."""
        agent = DefaultCPAgent()
        response = agent.process("hello")

        assert isinstance(response, AgentResponse)
        assert "hello" in response.text
        assert response.signals.turn_number == 1
        assert agent._turn == 1

    def test_get_signals(self):
        """Test getting signals."""
        agent = DefaultCPAgent(tier="ho2")
        signals = agent.get_signals()

        assert isinstance(signals, CPSignalBundle)
        assert signals.tier == "ho2"
        assert signals.stance == "neutral"

    def test_get_state(self):
        """Test getting state."""
        agent = DefaultCPAgent()
        state = agent.get_state()

        assert state["name"] == "cp_default"
        assert state["turn"] == 0
        assert "capabilities" in state

    def test_history(self):
        """Test conversation history."""
        agent = DefaultCPAgent()
        agent.process("first")
        agent.process("second")

        history = agent.get_history()
        assert len(history) == 4  # 2 user + 2 assistant
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "first"

    def test_clear_memory(self):
        """Test clearing memory."""
        agent = DefaultCPAgent()
        agent.process("test")
        assert len(agent.get_history()) > 0

        agent.clear_memory()
        assert len(agent.get_history()) == 0


class TestCPSignalBundle:
    """Test CPSignalBundle."""

    def test_defaults(self):
        """Test default values."""
        signals = CPSignalBundle()
        assert signals.stance == "neutral"
        assert signals.altitude == "normal"
        assert signals.turn_number == 0
        assert signals.health == 1.0
        assert signals.tier == "ho1"

    def test_compact_display(self):
        """Test compact display generation."""
        signals = CPSignalBundle(
            stance="engaged",
            altitude="L2",
            turn_number=5,
            health=0.8,
            tier="ho1",
        )
        display = signals.to_compact_display()

        assert "◉" in display  # engaged icon
        assert "L2" in display
        assert "#5" in display
        assert "@ho1" in display

    def test_normalize_health_float(self):
        """Test health normalization with float."""
        signals = CPSignalBundle(health=0.5)
        assert signals._normalize_health() == 0.5

    def test_normalize_health_string(self):
        """Test health normalization with string."""
        signals = CPSignalBundle(health="healthy")
        assert signals._normalize_health() == 1.0

        signals = CPSignalBundle(health="critical")
        assert signals._normalize_health() == 0.1


class TestUniversalShell:
    """Test UniversalShell."""

    @pytest.fixture
    def mock_agent(self):
        """Create mock agent."""
        agent = Mock(spec=CPAgentInterface)
        agent.name = "test_agent"
        agent.version = "1.0.0"
        agent.capabilities = {CPAgentCapability.GOVERNANCE}
        agent.get_state.return_value = {"turn": 0}
        agent.get_signals.return_value = CPSignalBundle()
        agent.get_history.return_value = []
        agent.get_config.return_value = {}
        agent.get_custom_commands.return_value = {}
        agent.process.return_value = AgentResponse(
            text="response", signals=CPSignalBundle()
        )
        return agent

    @pytest.fixture
    def shell(self, mock_agent, tmp_path):
        """Create shell with mock agent."""
        return UniversalShell(mock_agent, debug=False, root=tmp_path)

    def test_init(self, mock_agent, tmp_path):
        """Test shell initialization."""
        shell = UniversalShell(mock_agent, debug=True, root=tmp_path)

        assert shell.agent == mock_agent
        assert shell.debug is True
        assert shell.root == tmp_path
        assert shell.context_mode == "persistent"
        assert shell._turn == 0

    def test_context_modes(self, shell):
        """Test context mode tracking."""
        assert shell.context_mode == "persistent"

        shell.context_mode = "isolated"
        assert shell.context_mode == "isolated"

    def test_command_handlers_loaded(self, shell):
        """Test command handlers are loaded."""
        # Core commands should be available
        assert len(shell._command_handlers) > 0

    def test_get_default_root(self, shell):
        """Test default root detection."""
        root = shell._get_default_root()
        assert isinstance(root, Path)


class TestChatUI:
    """Test ChatUI."""

    @pytest.fixture
    def ui(self, tmp_path):
        """Create UI with temp history file."""
        history_file = tmp_path / ".test_history"
        return ChatUI(history_file=history_file)

    def test_init(self, ui):
        """Test UI initialization."""
        assert ui.terminal_width > 0
        assert ui.max_bubble_width > 0

    def test_visible_len(self, ui):
        """Test visible length calculation."""
        # Plain text
        assert ui._visible_len("hello") == 5

        # With ANSI codes
        colored = f"{Colors.RED}hello{Colors.RESET}"
        assert ui._visible_len(colored) == 5

    def test_wrap_text(self, ui):
        """Test text wrapping."""
        long_text = "This is a very long line that should be wrapped because it exceeds the maximum width."
        lines = ui._wrap_text(long_text)
        assert len(lines) >= 1

    def test_process_markdown_bold(self, ui):
        """Test markdown bold processing."""
        text = "This is **bold** text"
        processed = ui._process_markdown(text)
        assert Colors.BOLD in processed
        assert "bold" in processed

    def test_process_markdown_code(self, ui):
        """Test markdown code processing."""
        text = "This is `code` text"
        processed = ui._process_markdown(text)
        assert Colors.DIM in processed
        assert "code" in processed


class TestCreateDefaultAgent:
    """Test create_default_agent function."""

    def test_create_default(self):
        """Test creating default agent."""
        agent = create_default_agent()
        assert agent.name == "cp_default"
        assert agent._tier == "ho1"

    def test_create_with_tier(self):
        """Test creating agent with specific tier."""
        agent = create_default_agent(tier="ho2")
        assert agent._tier == "ho2"


class TestColorsClass:
    """Test Colors constants."""

    def test_colors_defined(self):
        """Test that color codes are defined."""
        assert Colors.RESET == "\033[0m"
        assert Colors.RED == "\033[31m"
        assert Colors.GREEN == "\033[32m"
        assert Colors.CYAN == "\033[36m"

    def test_styles_defined(self):
        """Test that style codes are defined."""
        assert Colors.BOLD == "\033[1m"
        assert Colors.DIM == "\033[2m"

    def test_backgrounds_defined(self):
        """Test that background codes are defined."""
        assert Colors.BG_BLUE == "\033[44m"
        assert Colors.BG_BRIGHT_BLACK == "\033[100m"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
