# Requirements

## Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-001 | Interactive REPL with prompt_toolkit | P0 | Shell accepts input with readline editing, history |
| FR-002 | Vim-style command dispatch | P0 | Commands prefixed with `:` route to handlers |
| FR-003 | Agent hot-swapping at runtime | P1 | `:agent <name>` switches active agent |
| FR-004 | Context window management | P0 | `:ctx persistent` and `:ctx isolated` modes work |
| FR-005 | Signal visualization | P0 | Signal strip displays stance, health, trust |
| FR-006 | Session logging to ledger | P0 | All commands logged to L-EXEC with hashes |
| FR-007 | Capability enforcement | P0 | Forbidden paths blocked before execution |
| FR-008 | CP commands (:pkg, :ledger, :gate) | P0 | Package, ledger, gate queries work |
| FR-009 | Debug mode with state inspection | P1 | `--debug` shows state after each turn |
| FR-010 | Shell passthrough (:! command) | P2 | `:! ls -la` runs shell commands |

## Non-Functional Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| NFR-001 | Startup time < 2s | P1 | Shell ready in under 2 seconds |
| NFR-002 | Command response < 500ms | P1 | Most commands respond in 500ms |
| NFR-003 | Terminal width adaptive | P1 | UI adapts to terminal width |
| NFR-004 | Graceful interrupt handling | P0 | Ctrl+C cleanly exits with ledger write |
| NFR-005 | Color-coded output | P1 | Errors red, success green, info dim |

## Dependencies

### Internal
- `modules/agent_runtime/session.py` - Session lifecycle
- `modules/agent_runtime/ledger_writer.py` - Ledger writes
- `modules/agent_runtime/capability.py` - Capability enforcement
- `lib/agent_helpers.py` - CPInspector
- `modules/stdlib_evidence/` - Hash generation

### External
- `prompt_toolkit>=3.0.0` - Terminal UI
- `pyyaml>=6.0` - Configuration
