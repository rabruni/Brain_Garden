"""Extensible Handler Registry.

Plugin-based handler registration for the chat interface.
Handlers are registered via decorator and invoked by name.

Example:
    from modules.chat_interface.registry import HandlerRegistry, register

    @register("my_handler", description="Does something", category="custom")
    def handle_my_query(context, query, session):
        return "Result"

    # Later
    result = HandlerRegistry.invoke("my_handler", {}, "query", session)
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any


@dataclass
class HandlerInfo:
    """Metadata about a registered handler."""

    name: str
    handler: Callable
    description: str
    requires_capability: Optional[str] = None
    category: str = "general"
    patterns: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "requires_capability": self.requires_capability,
            "category": self.category,
            "patterns": self.patterns,
        }


class HandlerRegistry:
    """Central registry for chat handlers.

    Handlers are registered via the @register decorator and can be
    invoked by name. The registry tracks metadata including description,
    category, and capability requirements.
    """

    _handlers: Dict[str, HandlerInfo] = {}

    @classmethod
    def register(
        cls,
        name: str,
        description: str = "",
        category: str = "general",
        requires_capability: Optional[str] = None,
        patterns: Optional[List[str]] = None,
    ) -> Callable:
        """Decorator to register a handler.

        Args:
            name: Handler name (used for invocation)
            description: Human-readable description
            category: Handler category (browse, packages, etc.)
            requires_capability: Required capability (admin, etc.)
            patterns: Query patterns this handler matches

        Returns:
            Decorator function
        """
        def decorator(fn: Callable) -> Callable:
            cls._handlers[name] = HandlerInfo(
                name=name,
                handler=fn,
                description=description,
                requires_capability=requires_capability,
                category=category,
                patterns=patterns or [],
            )
            return fn
        return decorator

    @classmethod
    def invoke(
        cls,
        name: str,
        context: Dict[str, Any],
        query: str,
        session: Any,
        capability: Optional[str] = None,
    ) -> str:
        """Invoke a handler by name.

        Args:
            name: Handler name
            context: Query context with extracted args
            query: Original query string
            session: ChatSession instance
            capability: Caller's capability level

        Returns:
            Handler result string

        Raises:
            KeyError: If handler not found
            PermissionError: If capability requirement not met
        """
        if name not in cls._handlers:
            return f"Unknown handler: {name}. Use 'help' to see available commands."

        info = cls._handlers[name]

        # Check capability requirement
        if info.requires_capability:
            if capability != info.requires_capability:
                return (
                    f"Permission denied: '{name}' requires '{info.requires_capability}' capability. "
                    f"Your capability: {capability or 'none'}"
                )

        # Invoke handler
        try:
            return info.handler(context, query, session)
        except Exception as e:
            return f"Handler error ({name}): {e}"

    @classmethod
    def get(cls, name: str) -> Optional[HandlerInfo]:
        """Get handler info by name."""
        return cls._handlers.get(name)

    @classmethod
    def list_handlers(cls) -> Dict[str, HandlerInfo]:
        """List all registered handlers."""
        return cls._handlers.copy()

    @classmethod
    def list_by_category(cls) -> Dict[str, List[HandlerInfo]]:
        """List handlers grouped by category."""
        by_category: Dict[str, List[HandlerInfo]] = {}
        for info in cls._handlers.values():
            if info.category not in by_category:
                by_category[info.category] = []
            by_category[info.category].append(info)
        return by_category

    @classmethod
    def clear(cls) -> None:
        """Clear all handlers (for testing)."""
        cls._handlers.clear()


# Convenience decorator
def register(
    name: str,
    description: str = "",
    category: str = "general",
    requires_capability: Optional[str] = None,
    patterns: Optional[List[str]] = None,
) -> Callable:
    """Convenience decorator for handler registration.

    Example:
        @register("browse_dir", description="List directory", category="browse")
        def handle_browse_dir(context, query, session):
            ...
    """
    return HandlerRegistry.register(
        name=name,
        description=description,
        category=category,
        requires_capability=requires_capability,
        patterns=patterns,
    )
