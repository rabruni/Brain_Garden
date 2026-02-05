# FMWK-CHAT-001: Chat Interface Governance Framework

## Metadata

- **Framework ID**: FMWK-CHAT-001
- **Title**: Chat Interface Governance
- **Version**: 1.0.0
- **Status**: active
- **Plane**: ho3
- **Created**: 2026-02-04

## Overview

This framework governs the implementation and operation of extensible chat interfaces
within the Control Plane. It ensures transparency, auditability, and proper governance
of all chat-based interactions with the system.

The chat interface provides:
1. **Full transparency** into Control Plane operations and code
2. **Extensible handler registry** for plugin-based command handling
3. **Session ledger integration** for complete audit trails
4. **Package management** operations through conversational interface

## Invariants

### I-CHAT-1: Session Identity

Every chat session MUST generate a unique session identifier following the pattern:
`SES-CHAT-YYYYMMDD-xxxxxxxx` where `xxxxxxxx` is a random hex string.

**Rationale**: Unique session IDs enable correlation of all operations within a session
and support audit trail requirements.

### I-CHAT-2: Turn Logging

All queries MUST log to a session-specific L-EXEC ledger with:
- `query_hash`: SHA256 hash of the input query
- `result_hash`: SHA256 hash of the response
- `handler`: Name of the handler that processed the query
- `duration_ms`: Processing time in milliseconds
- `declared_reads`: List of files read with their hashes (for transparency)

**Rationale**: Complete logging enables post-hoc auditing and debugging.

### I-CHAT-3: Read Transparency

Read operations MUST be ALLOWED for all PRISTINE and DERIVED paths without
capability requirements. The chat interface provides full transparency into:
- All source code files
- All configuration files
- All registry files
- All ledger files
- All documentation

**Rationale**: Transparency is a core value. Agents and users should be able to
inspect any part of the system they interact with.

### I-CHAT-4: Write Capability Requirements

Write operations MUST REQUIRE explicit capability grants:
- `admin` capability for package install/uninstall
- `admin` capability for registry modifications
- `admin` capability for ledger writes outside session scope

**Rationale**: Write operations can affect system state and must be governed.

### I-CHAT-5: Handler Registry Extensibility

The handler registry MUST be extensible without modifying core code:
- Handlers are registered via decorator pattern
- Handler metadata includes: name, description, category, required_capability
- New handlers can be added by placing modules in the handlers/ directory

**Rationale**: Extensibility enables the system to grow without architectural changes.

### I-CHAT-6: Fail-Safe Fallback

Unrecognized queries MUST fall back to a help/explain handler:
- No query should result in an error due to classification failure
- Unknown patterns trigger helpful guidance about available commands
- Error messages include suggestions for valid queries

**Rationale**: Graceful degradation improves user experience and prevents confusion.

### I-CHAT-7: Package Install Authorization

Package install and uninstall operations MUST REQUIRE `admin` capability:
- Preflight validation runs automatically before install
- Install failures log to L-PACKAGE ledger
- Successful installs log package manifest hash

**Rationale**: Package operations modify the system and require authorization.

### I-CHAT-8: Preflight Gate

Package install MUST pass preflight validation before execution:
- G0A: Package declaration consistency
- G1: Dependency chain validation
- OWN: Ownership conflict detection
- G5: Signature policy (if enabled)

**Rationale**: Preflight gates prevent invalid packages from being installed.

### I-CHAT-9: Uninstall Logging

Package uninstall MUST log to L-PACKAGE ledger with:
- `event_type`: PACKAGE_UNINSTALLED
- `package_id`: The uninstalled package
- `files_removed`: Count of files removed
- `timestamp`: When uninstall occurred

**Rationale**: Uninstall operations are significant events requiring audit trail.

## Query Type Categories

### Browse Operations (No capability required)

| Query Type | Handler | Description |
|------------|---------|-------------|
| BROWSE_CODE | browse.read_file | Read any file in the codebase |
| BROWSE_DIR | browse.list_dir | List contents of any directory |
| SEARCH_CODE | search.grep | Search for patterns in code |

### Package Operations (Mixed capabilities)

| Query Type | Handler | Capability |
|------------|---------|------------|
| PACKAGE_LIST | packages.list_all | none |
| PACKAGE_INSPECT | packages.inspect | none |
| PACKAGE_PREFLIGHT | packages.preflight | admin |
| PACKAGE_INSTALL | packages.install | admin |
| PACKAGE_UNINSTALL | packages.uninstall | admin |
| PACKAGE_STAGE | packages.stage | admin |

### System Operations (No capability required)

| Query Type | Handler | Description |
|------------|---------|-------------|
| LEDGER_QUERY | ledger.query | Query ledger entries |
| HELP | help.show | Show available commands |

## Session Ledger Structure

Session ledgers are stored at:
```
planes/{tier}/sessions/{session_id}/ledger/chat.jsonl
```

Each turn produces an entry:
```json
{
  "event_type": "CHAT_TURN",
  "submission_id": "{session_id}-T{turn_number:03d}",
  "decision": "EXECUTED",
  "reason": "Query processed successfully",
  "metadata": {
    "turn_number": 1,
    "query_hash": "sha256:...",
    "result_hash": "sha256:...",
    "handler": "browse.read_file",
    "duration_ms": 45,
    "declared_reads": [
      {"path": "lib/auth.py", "hash": "sha256:..."}
    ]
  }
}
```

## Compliance

Implementations of this framework MUST:

1. Generate unique session IDs per I-CHAT-1
2. Log all turns per I-CHAT-2
3. Allow unrestricted reads per I-CHAT-3
4. Require capabilities for writes per I-CHAT-4
5. Support handler registration per I-CHAT-5
6. Handle unknown queries gracefully per I-CHAT-6
7. Gate package operations per I-CHAT-7, I-CHAT-8, I-CHAT-9

## Related Artifacts

- **SPEC-CHAT-001**: Implementation specification
- **FMWK-100**: Agent Development Standard (parent)
- **FMWK-200**: Ledger Protocol Standard
- **FMWK-107**: Package Management Standard
