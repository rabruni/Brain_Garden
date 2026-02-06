"""Extensible Chat Interface for Control Plane.

Provides a conversational interface to Control Plane functionality with:
- Extensible handler registry (plugin pattern)
- Session ledger integration (full audit trail)
- Improved classification with fuzzy matching
- Full transparency (read any file/directory)
- Package management operations

Example usage:

    # Programmatic API
    from modules.chat_interface import ChatInterface, chat_turn

    interface = ChatInterface(tier="ho1")
    result = chat_turn(interface, "what is in modules?")
    print(result["response"])

    # Pipe mode (from command line)
    echo '{"query": "list packages"}' | python3 -m modules.chat_interface

    # Interactive mode
    python3 -m modules.chat_interface --interactive
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from modules.chat_interface.session import ChatSession, create_session
from modules.chat_interface.classifier import (
    classify_query,
    get_handler_name,
    QueryClassification,
    QueryType,
)
from modules.chat_interface.registry import HandlerRegistry

# Import handlers to register them
from modules.chat_interface import handlers  # noqa: F401


@dataclass
class ChatInterface:
    """Main chat interface.

    Attributes:
        tier: Tier name (ho1, ho2, ho3)
        session: Associated ChatSession
        capability: Current capability level
    """

    tier: str = "ho1"
    capability: Optional[str] = None
    session: ChatSession = field(default=None, repr=False)

    def __post_init__(self):
        """Initialize session if not provided."""
        if self.session is None:
            self.session = create_session(self.tier)

    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self.session.session_id


def chat_turn(
    interface: ChatInterface,
    query: str,
    capability: Optional[str] = None,
) -> Dict[str, Any]:
    """Process a single chat turn.

    Args:
        interface: ChatInterface instance
        query: User query string
        capability: Override capability for this turn

    Returns:
        Dictionary with:
        - response: Handler result
        - session_id: Session identifier
        - turn_number: Turn number in session
        - classification: Query classification details
        - handler: Handler that processed the query
        - duration_ms: Processing time
    """
    start_time = time.time()

    # Use provided capability or interface default
    cap = capability or interface.capability

    # Classify query
    classification = classify_query(query)

    # Get handler name
    handler_name = get_handler_name(classification.type)

    # Invoke handler
    response = HandlerRegistry.invoke(
        name=handler_name,
        context=classification.extracted_args,
        query=query,
        session=interface.session,
        capability=cap,
    )

    # Calculate duration
    duration_ms = int((time.time() - start_time) * 1000)

    # Log turn to session ledger
    interface.session.log_turn(
        query=query,
        result=response,
        handler=handler_name,
        duration_ms=duration_ms,
        classification=classification.to_dict(),
    )

    return {
        "response": response,
        "session_id": interface.session_id,
        "turn_number": interface.session.turn_count,
        "classification": classification.to_dict(),
        "handler": handler_name,
        "duration_ms": duration_ms,
    }


def quick_query(query: str, tier: str = "ho1") -> str:
    """Execute a single query and return the response.

    Convenience function for one-off queries.

    Args:
        query: User query string
        tier: Tier name

    Returns:
        Response string
    """
    interface = ChatInterface(tier=tier)
    result = chat_turn(interface, query)
    return result["response"]


__all__ = [
    "ChatInterface",
    "ChatSession",
    "chat_turn",
    "quick_query",
    "create_session",
    "classify_query",
    "QueryClassification",
    "QueryType",
    "HandlerRegistry",
]

__version__ = "1.0.0"
