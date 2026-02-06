# SPEC-CHAT-001: Chat Interface Implementation

## Overview

This specification defines the implementation of an extensible, transparent chat
interface for the Control Plane. The chat interface provides a conversational
way to interact with all Control Plane functionality.

## Scope

- **Module**: `modules/chat_interface/`
- **Framework**: FMWK-CHAT-001 (Chat Interface Governance)
- **Tier**: HO1 (First Order - Agent Runtime)

## Key Features

1. **Extensible Handler Registry**: Plugin pattern for adding new commands
2. **Session Ledger Integration**: Full audit trail of all interactions
3. **Full Transparency**: Read access to all code and configuration
4. **Package Management**: Install, uninstall, inspect packages via chat
5. **Fuzzy Query Matching**: Natural language variations supported

## Module Structure

```
modules/chat_interface/
├── __init__.py           # Public API: ChatInterface, chat_turn
├── __main__.py           # Pipe CLI + interactive mode
├── session.py            # Session management with ledger integration
├── registry.py           # Extensible handler registry
├── classifier.py         # Improved classification with fuzzy matching
└── handlers/
    ├── __init__.py       # Handler registration
    ├── packages.py       # Package lifecycle operations
    ├── browse.py         # File and directory browsing
    ├── search.py         # Code search
    ├── ledger.py         # Ledger queries
    └── help.py           # Help and command listing
```

## Dependencies

- `lib/ledger_client.py`: Session ledger writes
- `lib/merkle.py`: File hashing for evidence
- `modules/stdlib_evidence/`: Evidence envelope building
- `scripts/pkgutil.py`: Package operations

## Interfaces

### Pipe Interface

```bash
echo '{"query": "list packages"}' | python3 -m modules.chat_interface
```

### Interactive Mode

```bash
python3 -m modules.chat_interface --interactive
```

### Programmatic API

```python
from modules.chat_interface import ChatInterface, chat_turn

interface = ChatInterface(tier="ho1")
result = chat_turn(interface, "what is in modules?")
```
