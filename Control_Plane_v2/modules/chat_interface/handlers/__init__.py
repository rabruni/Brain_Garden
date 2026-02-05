"""Chat Interface Handlers.

This package contains all handler implementations for the chat interface.
Handlers are auto-registered via the @register decorator when imported.

Import this module to register all handlers:
    from modules.chat_interface import handlers  # Registers all

Or import specific modules:
    from modules.chat_interface.handlers import browse, packages
"""

# Import all handler modules to trigger registration
from modules.chat_interface.handlers import browse
from modules.chat_interface.handlers import packages
from modules.chat_interface.handlers import search
from modules.chat_interface.handlers import ledger
from modules.chat_interface.handlers import help

__all__ = ["browse", "packages", "search", "ledger", "help"]
