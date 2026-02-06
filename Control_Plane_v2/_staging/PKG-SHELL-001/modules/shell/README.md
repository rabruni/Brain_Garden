# Universal Shell for Control Plane

A rich terminal interface for interacting with the Control Plane, featuring vim-style commands, signal visualization, session management, and ledger integration.

## Purpose

The Universal Shell provides operators with a consistent, powerful interface for:

- Querying Control Plane state (packages, ledgers, gates)
- Visualizing system signals (health, stance, trust)
- Managing conversation context
- Executing governed operations with full audit logging

## Two Modes

The shell supports two modes per FMWK-100 §7 pipe-first contract:

1. **Pipe Mode** - JSON stdin/stdout for programmatic use
2. **Interactive Mode** - Terminal UI for human use

---

## Pipe Mode (Programmatic)

For scripts, CI/CD, and programmatic access.

### Basic Usage

```bash
# List packages
echo '{"operation": "pkg_list"}' | python3 -m modules.shell

# Get package info
echo '{"operation": "pkg_info", "package_id": "PKG-BASELINE-HO3-000"}' | python3 -m modules.shell

# Query ledger
echo '{"operation": "ledger_query", "limit": 5}' | python3 -m modules.shell

# Get gate status
echo '{"operation": "gate_status"}' | python3 -m modules.shell

# Get compliance summary
echo '{"operation": "compliance"}' | python3 -m modules.shell

# Get current signals
echo '{"operation": "signal_status"}' | python3 -m modules.shell

# Trace artifact
echo '{"operation": "trace", "artifact_id": "FMWK-100"}' | python3 -m modules.shell
```

### Response Format

All responses follow FMWK-100 §7 envelope format:

```json
{
  "status": "ok",
  "result": {
    "packages": [...]
  },
  "evidence": {
    "timestamp": "2026-02-03T12:00:00.000000+00:00",
    "input_hash": "sha256:abc123...",
    "duration_ms": 42,
    "declared_reads": [{"path": "...", "hash": "..."}]
  }
}
```

### Core Operations

| Operation | Description | Required Params |
|-----------|-------------|-----------------|
| `pkg_list` | List installed packages | - |
| `pkg_info` | Get package details | `package_id` |
| `ledger_query` | Query ledger entries | - (optional: `type`, `limit`) |
| `gate_status` | Get gate status | - (optional: `gate`) |
| `compliance` | Get compliance summary | - |
| `trace` | Trace artifact lineage | `artifact_id` |
| `signal_status` | Get current signals | - |
| `execute_command` | Execute shell command | `command` |

### Package Compliance Operations (Agent Guidance)

These operations provide complete guidance for agents creating packages:

| Operation | Description | Required Params |
|-----------|-------------|-----------------|
| `manifest_requirements` | Get manifest.json field requirements | - |
| `packaging_workflow` | Get step-by-step packaging workflow | - |
| `troubleshoot` | Get troubleshooting guide | - (optional: `error_type`) |
| `example_manifest` | Get example manifest | - (optional: `package_type`) |
| `list_frameworks` | List registered frameworks | - |
| `list_specs` | List registered specs | - (optional: `framework_id`) |
| `spec_info` | Get spec manifest | `spec_id` |
| `governed_roots` | List governed roots | - |
| `explain_path` | Explain path classification | `path` |

### Agent Workflow Example

```bash
# 1. Get the packaging workflow
echo '{"operation": "packaging_workflow"}' | python3 -m modules.shell

# 2. List available frameworks
echo '{"operation": "list_frameworks"}' | python3 -m modules.shell

# 3. List specs for a framework
echo '{"operation": "list_specs", "framework_id": "FMWK-100"}' | python3 -m modules.shell

# 4. Get manifest requirements
echo '{"operation": "manifest_requirements"}' | python3 -m modules.shell

# 5. Get an example manifest
echo '{"operation": "example_manifest", "package_type": "library"}' | python3 -m modules.shell

# 6. If you encounter errors, get troubleshooting help
echo '{"operation": "troubleshoot", "error_type": "G1"}' | python3 -m modules.shell

# 7. Check if a path is writable
echo '{"operation": "explain_path", "path": "lib/my_module.py"}' | python3 -m modules.shell
```

### Exit Codes

- `0`: Success (status: "ok")
- `1`: Error (status: "error")

---

## Interactive Mode (Human)

### Launch Shell

```bash
# Basic launch
python scripts/shell.py

# With debug mode
python scripts/shell.py --debug

# Specific tier
python scripts/shell.py --tier ho2
```

### Core Commands

| Command | Short | Description |
|---------|-------|-------------|
| `:help` | `:h` | Show help |
| `:quit` | `:q` | Exit shell |
| `:clear` | `:c` | Clear screen |
| `:state` | `:s` | Show JSON state |
| `:agent` | `:a` | Show agent info |

### Control Plane Commands

| Command | Description |
|---------|-------------|
| `:pkg` | List installed packages |
| `:pkg <id>` | Show package details |
| `:ledger` | Show recent ledger entries |
| `:ledger session` | Show session ledger |
| `:gate` | Show gate status |
| `:compliance` | Show compliance info |
| `:trace <id>` | Trace artifact lineage |

### Context Commands

| Command | Description |
|---------|-------------|
| `:v` | View context window |
| `:ctx` | Show context mode |
| `:ctx persistent` | Keep conversation history |
| `:ctx isolated` | Fresh context each turn |

### Signal Commands

| Command | Description |
|---------|-------------|
| `:sig` | Show detailed signals |
| `:trust` | Show trust panel |
| `:learn` | Show learning panel |

### Shell Passthrough

```bash
:! ls -la          # Run shell command
:! git status      # Check git status
```

## Dependencies

### Internal

- `modules/agent_runtime/session.py` - Session lifecycle
- `modules/agent_runtime/ledger_writer.py` - Audit logging
- `modules/agent_runtime/capability.py` - Capability enforcement
- `lib/agent_helpers.py` - CPInspector
- `modules/stdlib_evidence/` - Hash generation

### External

- `prompt_toolkit>=3.0.0` - Terminal UI (optional, fallback to basic input)

## Module Structure

```
modules/shell/
├── __init__.py          # Module exports
├── __main__.py          # Pipe-first entry point (FMWK-100 §7)
├── operations.py        # Operation handlers for pipe mode
├── shell.py             # Main shell class (interactive mode)
├── chat_ui.py           # Terminal UI
├── interfaces.py        # Agent protocol
├── commands/            # Command handlers (interactive mode)
│   ├── __init__.py      # Command registry
│   ├── core.py          # Core commands
│   ├── memory.py        # Memory commands
│   ├── signals.py       # Signal commands
│   ├── governance.py    # CP commands
│   └── notes.py         # Note commands
├── capabilities.json    # Capability manifest
└── README.md            # This file
```

## Examples

### Query Packages

```
You: :pkg
── Installed Packages ──

  Package ID                     Version    Assets   Type
  ------------------------------ ---------- -------- ------------
  PKG-BASELINE-HO3-000           1.0.0      42       baseline

You: :pkg PKG-BASELINE-HO3-000
── Package: PKG-BASELINE-HO3-000 ──

  Package ID: PKG-BASELINE-HO3-000
  Version:    1.0.0
  Spec:       SPEC-CORE-001
  Plane:      ho3
  Type:       baseline

  Assets (42 files):
    [library] lib/authz.py
    [library] lib/merkle.py
    ...
```

### View Ledger

```
You: :ledger
── Ledger Entries ──

  Ledger: governance-20260203-120000.jsonl

  [2026-02-03T12:00:00] GATE_PASSED: PASS
  [2026-02-03T12:01:00] PACKAGE_INSTALLED: CREATE
```

### Check Signals

```
You: :sig
── Signal Status ──

  Core Signals
  ├─ Stance:    neutral
  ├─ Altitude:  normal
  ├─ Turn:      #5
  └─ Health:    1.0

  Control Plane
  ├─ Tier:      ho1
  ├─ Role:      none
  ├─ Work Order: none
  ├─ Ledger:    synced
  └─ Gate:      open

  Compact: ○ · L2 · [█████] · #5 · @ho1
```

## Testing

```bash
# Run all shell tests
pytest tests/test_shell.py tests/test_shell_commands.py tests/test_shell_pipe.py -v

# Pipe mode tests only
pytest tests/test_shell_pipe.py -v

# Interactive mode tests only
pytest tests/test_shell.py tests/test_shell_commands.py -v
```

## Compliance

This module complies with:

- **FMWK-SHELL-001**: Shell/CLI Development Standard (v1.1.0)
- **FMWK-100**: Agent Development Standard (pipe-first contract §7)

All commands are logged to the session ledger for audit purposes.
