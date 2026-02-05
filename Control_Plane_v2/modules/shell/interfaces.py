"""Agent Interface - Standard contract for pluggable agents in Control Plane.

Any agent that wants to work with the Universal Shell must implement
the CPAgentInterface protocol. This allows:

1. Same UI for any agent
2. Hot-swappable agents at runtime
3. Consistent signal/state visualization
4. Unified command handling
5. Control Plane integration

Adapted from _locked_system_flattened/interfaces/agent.py with CP extensions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Set


class CPAgentCapability(Enum):
    """Capabilities an agent may support."""

    # Standard capabilities (from original)
    MEMORY = "memory"  # Can remember across sessions
    CONSENT = "consent"  # Has consent management
    SIGNALS = "signals"  # Tracks behavioral signals
    TRUST = "trust"  # Has trust/learning system
    COMMITMENTS = "commitments"  # Can make commitments
    FILESYSTEM = "filesystem"  # Has filesystem access
    EMERGENCY = "emergency"  # Has emergency stop

    # Control Plane capabilities (NEW)
    GOVERNANCE = "governance"  # Can query CP state
    LEDGER = "ledger"  # Can read/write ledger
    PACKAGE_MGT = "package_mgt"  # Can query packages


@dataclass
class CPSignalBundle:
    """Standardized signal data for UI display.

    Agents expose their internal signals through this bundle,
    allowing the shell to visualize state consistently.

    Extended from original SignalBundle with Control Plane fields.
    """

    # Core signals (all agents should provide)
    stance: str = "neutral"  # Current behavioral stance
    altitude: str = "normal"  # Processing depth
    turn_number: int = 0  # Conversation turn

    # Quality signals (optional)
    health: float = 1.0  # Quality health 0-1
    drift: float = 0.0  # Drift from baseline 0-1

    # Trust signals (optional)
    trust_level: Optional[float] = None
    learning_active: bool = False

    # State metadata (optional)
    active_frame: Optional[str] = None
    gate_transitions: list = field(default_factory=list)

    # Control Plane signals (NEW)
    tier: str = "ho1"  # Current tier
    role: Optional[str] = None  # Current role
    active_wo: Optional[str] = None  # Active work order
    ledger_synced: bool = True  # Ledger sync status
    gate_state: str = "open"  # Gate state

    # Custom signals (agent-specific)
    custom: dict = field(default_factory=dict)

    def _normalize_health(self) -> float:
        """Convert health to float (0.0-1.0), handling string descriptors."""
        if self.health is None:
            return 1.0
        if isinstance(self.health, (int, float)):
            return float(self.health)
        # Handle string descriptors
        health_map = {
            "healthy": 1.0,
            "good": 0.8,
            "moderate": 0.6,
            "degraded": 0.4,
            "poor": 0.2,
            "critical": 0.1,
        }
        if isinstance(self.health, str):
            return health_map.get(self.health.lower(), 0.5)
        return 1.0

    def to_compact_display(self) -> str:
        """Generate compact signal strip for UI."""
        parts = []

        # Stance indicator
        stance_icons = {
            "grounded": "●",
            "engaged": "◉",
            "committed": "◈",
            "protective": "◇",
            "neutral": "○",
            "sense": "◐",
            "sensemaking": "◐",
        }
        parts.append(stance_icons.get(self.stance.lower(), "○"))

        # Altitude
        alt_icons = {
            "surface": "L1",
            "normal": "L2",
            "deep": "L3",
            "reflective": "L4",
            "L1": "L1",
            "L2": "L2",
            "L3": "L3",
            "L4": "L4",
        }
        parts.append(alt_icons.get(self.altitude, "L2"))

        # Health bar (normalize in case it's a string)
        health_float = self._normalize_health()
        health_bar = "█" * int(health_float * 5) + "░" * (5 - int(health_float * 5))
        parts.append(f"[{health_bar}]")

        # Turn
        parts.append(f"#{self.turn_number}")

        # Trust if available
        if self.trust_level is not None:
            parts.append(f"T:{self.trust_level:.1f}")

        # Tier (CP specific)
        parts.append(f"@{self.tier}")

        return " · ".join(parts)


@dataclass
class AgentResponse:
    """Standardized response from agent processing.

    Every agent returns this structure, allowing the shell
    to handle responses consistently.
    """

    # Core response
    text: str  # The actual response text
    signals: CPSignalBundle  # Current signal state

    # Processing metadata
    processed: bool = True  # Was input actually processed?
    error: Optional[str] = None  # Error message if any

    # Side effects
    gate_transitions: list = field(default_factory=list)
    notes_captured: list = field(default_factory=list)
    proposals_pending: list = field(default_factory=list)

    # Agent-specific data
    metadata: dict = field(default_factory=dict)


class CPAgentInterface(ABC):
    """Abstract interface that all Control Plane agents must implement.

    This is the contract between agents and the Universal Shell.
    Implement this to plug any agent into the shell.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Agent version string."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> Set[CPAgentCapability]:
        """Set of capabilities this agent supports."""
        pass

    @abstractmethod
    def process(self, user_input: str) -> AgentResponse:
        """Process user input and return response.

        This is the main entry point. The shell calls this
        for every user message.

        Args:
            user_input: The user's message

        Returns:
            AgentResponse with text and signals
        """
        pass

    @abstractmethod
    def get_signals(self) -> CPSignalBundle:
        """Get current signal state without processing.

        Used by shell for state display commands.
        """
        pass

    @abstractmethod
    def get_state(self) -> dict:
        """Get full internal state as dict.

        Used for debugging and state inspection.
        """
        pass

    # Optional capability methods - override if supported

    def needs_consent(self) -> bool:
        """Check if agent needs consent configuration."""
        return False

    def grant_consent(self, *args, **kwargs) -> None:
        """Grant consent with specified options."""
        pass

    def get_consent_summary(self) -> dict:
        """Get current consent configuration."""
        return {"status": "not_supported"}

    def revoke_consent(self) -> None:
        """Revoke all consent."""
        pass

    def create_commitment(self, frame: str) -> bool:
        """Create a commitment in the given frame."""
        return False

    def trigger_emergency(self, reason: str) -> bool:
        """Trigger emergency stop."""
        return False

    def recover_from_emergency(self) -> tuple:
        """Recover from emergency state.

        Returns:
            Tuple of (success: bool, message: str)
        """
        return False, "Not supported"

    def clear_conversation(self) -> None:
        """Clear conversation history."""
        pass

    def clear_memory(self) -> None:
        """Clear in-memory context (preserve disk)."""
        pass

    def reload_conversation_history(self) -> None:
        """Reload conversation history from disk."""
        pass

    def set_ephemeral_mode(self, enabled: bool) -> None:
        """Set ephemeral mode (pause disk saves)."""
        pass

    def get_notes(self, note_type: str = None, n: int = 10) -> list:
        """Get formatted notes.

        Returns:
            List of note dicts with content, type, timestamp
        """
        return []

    def add_note(self, content: str, note_type: str = "personal") -> dict:
        """Add a note manually.

        Args:
            content: The note text
            note_type: "personal" or "developer"

        Returns:
            dict with success, message keys
        """
        return {"success": False, "message": "Notes not supported"}

    def get_trust_panel(self) -> str:
        """Get trust system display."""
        return "Trust not supported"

    def get_learning_panel(self) -> str:
        """Get learning system display."""
        return "Learning not supported"

    def get_signals_panel(self) -> str:
        """Get detailed signals display."""
        return "Signals not supported"

    def get_history(self) -> list:
        """Get conversation history.

        Returns:
            List of message dicts with role, content
        """
        return []

    def get_signal_display(self, compact: bool = True) -> str:
        """Get signal display string.

        Args:
            compact: If True, return compact strip format

        Returns:
            Formatted signal string
        """
        signals = self.get_signals()
        return signals.to_compact_display()

    def get_config(self) -> dict:
        """Get agent configuration.

        Returns:
            Config dict with model, settings, etc.
        """
        return {}

    def get_custom_commands(self) -> dict:
        """Return agent-specific commands.

        Returns dict of command_name -> handler_function.
        Handler receives (shell, args) and returns bool (handled).
        """
        return {}


class DefaultCPAgent(CPAgentInterface):
    """Default Control Plane agent for basic shell functionality.

    This agent provides minimal functionality for testing and
    development without requiring a full agent implementation.
    """

    def __init__(self, tier: str = "ho1"):
        """Initialize default agent.

        Args:
            tier: Operating tier (ho1, ho2, ho3)
        """
        self._tier = tier
        self._turn = 0
        self._history = []

    @property
    def name(self) -> str:
        return "cp_default"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> Set[CPAgentCapability]:
        return {
            CPAgentCapability.GOVERNANCE,
            CPAgentCapability.LEDGER,
            CPAgentCapability.PACKAGE_MGT,
        }

    def process(self, user_input: str) -> AgentResponse:
        """Process user input."""
        self._turn += 1
        self._history.append({"role": "user", "content": user_input})

        # Default echo response
        response_text = f"Received: {user_input}"
        self._history.append({"role": "assistant", "content": response_text})

        return AgentResponse(
            text=response_text,
            signals=self.get_signals(),
        )

    def get_signals(self) -> CPSignalBundle:
        """Get current signals."""
        return CPSignalBundle(
            stance="neutral",
            altitude="normal",
            turn_number=self._turn,
            health=1.0,
            tier=self._tier,
        )

    def get_state(self) -> dict:
        """Get full state."""
        return {
            "name": self.name,
            "version": self.version,
            "tier": self._tier,
            "turn": self._turn,
            "history_length": len(self._history),
            "capabilities": [c.value for c in self.capabilities],
        }

    def get_history(self) -> list:
        """Get conversation history."""
        return self._history.copy()

    def clear_memory(self) -> None:
        """Clear in-memory history."""
        self._history = []
