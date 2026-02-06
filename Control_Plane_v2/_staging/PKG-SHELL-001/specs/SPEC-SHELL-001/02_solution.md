# Proposed Solution

## Solution Overview

Port the Universal Shell from `_locked_system_flattened` to the Control Plane as a governed module. The shell will be adapted to integrate with Control Plane infrastructure:

1. **Session Management**: Use `modules/agent_runtime/session.py` for session lifecycle
2. **Ledger Integration**: Use `LedgerWriter` for dual ledger writes (L-EXEC, L-EVIDENCE)
3. **Capability Enforcement**: Use `CapabilityEnforcer` to restrict operator actions
4. **CP Inspection**: Use `CPInspector` for package/ledger queries
5. **New Commands**: Add governance commands (:pkg, :ledger, :gate, :wo, :compliance, :trace)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PKG-SHELL-001                                │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ shell.py     │  │ chat_ui.py   │  │ interfaces.py        │   │
│  │ UniversalShell│  │ ChatUI       │  │ CPAgentInterface     │   │
│  │ + CP commands │  │ (adapted)    │  │ + GOVERNANCE cap     │   │
│  └──────┬───────┘  └──────────────┘  └──────────────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              CONTROL PLANE INTEGRATION                    │   │
│  │                                                           │   │
│  │  Session (agent_runtime)  │  LedgerWriter  │  Router      │   │
│  │  CapabilityEnforcer       │  CPInspector   │  AdminAgent  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Alternatives Considered

### 1. Do Nothing
Keep using separate scripts. Rejected because it doesn't solve the unified interface problem.

### 2. Build New Shell from Scratch
Create entirely new shell. Rejected because the existing Universal Shell is feature-complete and well-tested.

### 3. Use Existing CLI Framework (Click/Typer)
Wrap scripts in Click commands. Rejected because it doesn't provide REPL experience or signal visualization.

## Risks

### R1: Prompt Toolkit Dependency
**Risk**: prompt_toolkit may not be installed.
**Mitigation**: Add to requirements.txt, graceful fallback to basic input.

### R2: Performance with Large Ledgers
**Risk**: Ledger queries may be slow.
**Mitigation**: Use pagination, limit default results.

### R3: Capability Creep
**Risk**: Shell may attempt privileged operations.
**Mitigation**: Strict capability manifest, capability enforcement before every command.
