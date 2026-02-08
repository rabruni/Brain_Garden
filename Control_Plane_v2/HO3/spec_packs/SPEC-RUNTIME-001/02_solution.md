# Proposed Solution

## Overview

Create a T1 (runtime tier) module `modules/agent_runtime/` that provides:

1. **AgentRunner**: Load agent package, execute turns with capability enforcement
2. **CapabilityEnforcer**: Check and enforce read/write/execute permissions
3. **Session**: Generate session IDs, manage session lifecycle
4. **TurnSandbox**: OS-level write isolation for each turn
5. **PromptBuilder**: Assemble prompt headers from ledger state
6. **Memory**: Ledger replay with HO2 checkpoint acceleration
7. **LedgerWriter**: Write to both L-EXEC and L-EVIDENCE

## Architecture

```
modules/agent_runtime/
├── __init__.py         # Public API: AgentRunner, Session, etc.
├── runner.py           # AgentRunner.execute_turn()
├── capability.py       # CapabilityEnforcer.check(), .enforce()
├── session.py          # Session ID generation, context manager
├── sandbox.py          # TurnSandbox: OS-level write isolation
├── prompt_builder.py   # PromptBuilder.build()
├── memory.py           # AdminMemory.reconstruct_context()
├── ledger_writer.py    # Writes to both exec.jsonl and evidence.jsonl
└── README.md
```

## Key Design Decisions

### 1. Fail-Closed Write Surface

Every turn must declare its outputs upfront. After execution, the sandbox compares realized writes to declared outputs. Any mismatch raises CapabilityViolation:

```python
with TurnSandbox(session_id, declared_outputs) as sandbox:
    result = execute_turn(request)
    realized_writes, valid = sandbox.verify_writes()
    if not valid:
        raise CapabilityViolation("Undeclared write detected")
```

### 2. Dual Ledger Writing

Every turn writes to BOTH ledgers per the plan's Correction #10:
- `planes/<tier>/sessions/<sid>/ledger/exec.jsonl` - What happened
- `planes/<tier>/sessions/<sid>/ledger/evidence.jsonl` - Evidence with hashes

### 3. Session-Scoped Sandbox

Writable paths are limited to session scope:
- `tmp/<session_id>/**` - Temporary workspace
- `output/<session_id>/**` - Generated outputs

Everything else is read-only. The sandbox sets TMPDIR/TEMP/TMP environment variables to redirect subprocess temp files.

### 4. Capability Declaration in Manifest

Capabilities come from the agent's package manifest:
```json
{
  "capabilities": {
    "read": ["ledger/*.jsonl", "registries/*.csv"],
    "execute": ["scripts/trace.py --explain"],
    "write": ["planes/ho1/sessions/<session_id>/ledger/exec.jsonl"],
    "forbidden": ["lib/*", "scripts/package_install.py"]
  }
}
```

### 5. Context from Ledgers

Context is reconstructed from ledgers, not stored state:
1. Find latest HO2 checkpoint (if available)
2. Replay HO1 entries since checkpoint
3. Merge into current context

## Alternatives Considered

### Alternative 1: No sandbox, rely on capability checks only

**Rejected because:** Capability checks happen at invocation time, but subprocess writes can bypass them. OS-level sandboxing catches all writes.

### Alternative 2: Separate runtime per agent

**Rejected because:** Code duplication, inconsistent enforcement, harder to audit.

### Alternative 3: Docker-based isolation

**Rejected because:** Heavyweight, adds operational complexity, not necessary for file isolation.

## Risks

1. **Sandbox escapes**: Sophisticated code might bypass sandbox. Mitigation: Use OS-level mechanisms (chroot, namespace) in production.

2. **Performance overhead**: Sandbox setup adds latency. Mitigation: Session directories are reused across turns.

3. **Missing writes**: Agent forgets to declare an output. Mitigation: Clear documentation, runtime validation with helpful error messages.

4. **Ledger race conditions**: Multiple concurrent sessions writing. Mitigation: Session-scoped ledger files avoid conflicts.
