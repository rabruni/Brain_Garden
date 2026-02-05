# Problem Statement

## Current State

The Control Plane has powerful package management, ledger, and governance systems,
but interacting with them requires:

1. **Direct script execution**: Users must know specific scripts and arguments
2. **No unified interface**: Different operations use different entry points
3. **Limited discoverability**: Users cannot easily explore available functionality
4. **No audit trail for queries**: Read operations are not logged

## Specific Issues

### Issue 1: Directory Browsing Fails

Current router fails on natural language directory queries:

```
User: what is in the modules directory?
System: Directory not found: the
```

The classifier extracts "the" instead of "modules" due to rigid pattern matching.

### Issue 2: No Package Management via Chat

Users cannot:
- List available packages
- Inspect package contents
- Install or uninstall packages
- Run preflight validation

### Issue 3: No Session Continuity

Each query is independent with no:
- Session tracking
- Turn numbering
- Accumulated context
- Evidence chain

### Issue 4: Not Extensible

Adding new commands requires:
- Modifying classifier patterns
- Adding handler functions
- Wiring everything together manually

## Requirements

1. Fix directory browsing to extract correct path from natural language
2. Add package management handlers
3. Implement session ledger integration
4. Create extensible handler registry
5. Support fuzzy query matching
