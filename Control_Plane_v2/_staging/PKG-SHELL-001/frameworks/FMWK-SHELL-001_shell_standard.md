# FMWK-SHELL-001: Shell/CLI Development Standard

**Version:** 1.1.0
**Status:** active
**Purpose:** Standards for developing interactive terminal shells in the Control Plane

---

## 1. Overview

This framework defines standards for building terminal-based shells that interact with the Control Plane. It ensures consistent:
- **Pipe-first contract** (per FMWK-100 §7)
- Command syntax and dispatch
- Signal visualization
- Session management
- Ledger integration
- Capability enforcement

Shell modules MUST support TWO modes:
1. **Pipe mode** - JSON stdin/stdout for programmatic use
2. **Interactive mode** - Terminal UI for human use

Shells MUST comply with this framework. Non-compliant shells cannot pass gates.

---

## 2. Pipe-First Contract (per FMWK-100 §7)

Shell modules MUST implement the pipe-first contract for programmatic access.

### 2.1 Entry Point

```bash
echo '{"operation": "pkg_list"}' | python3 -m modules.shell
```

### 2.2 Request Format

```json
{
  "operation": "<operation_name>",
  "<param1>": "<value1>",
  "<param2>": "<value2>"
}
```

### 2.3 Response Envelope

All responses MUST follow this format:

```json
{
  "status": "ok|error",
  "result": { /* operation-specific result */ },
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": { /* optional context */ }
  },
  "evidence": {
    "timestamp": "ISO8601 UTC timestamp",
    "input_hash": "sha256:...",
    "output_hash": "sha256:...",
    "duration_ms": 123,
    "declared_reads": [{"path": "...", "hash": "..."}],
    "declared_writes": []
  }
}
```

### 2.4 Supported Operations

**Core Operations:**

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

**Package Compliance Operations (Agent Guidance):**

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

### 2.5 Exit Codes

- `0`: Success (status: "ok")
- `1`: Error (status: "error")

### 2.6 Error Codes

| Code | Meaning |
|------|---------|
| `INVALID_JSON` | Request is not valid JSON |
| `EMPTY_INPUT` | No input provided |
| `INVALID_REQUEST` | Request is not a JSON object |
| `UNKNOWN_OPERATION` | Operation not recognized |
| `MISSING_FIELD` | Required field missing |
| `HANDLER_ERROR` | Operation handler failed |

---

## 3. Invariants (I-SHELL-*)

### 3.1 Logging Invariants

- **I-SHELL-1**: All shell commands MUST be logged to ledger (L-EXEC).
- **I-SHELL-2**: Command execution MUST include command_hash and result_hash.
- **I-SHELL-3**: Session state MUST be persisted to session directory.

### 3.2 Security Invariants

- **I-SHELL-4**: Capability enforcement MUST occur before command execution.
- **I-SHELL-5**: Forbidden operations MUST be blocked with clear error message.
- **I-SHELL-6**: Agent interface protocol (CPAgentInterface) MUST be followed.

### 3.3 Session Invariants

- **I-SHELL-7**: Session MUST create session directory on start.
- **I-SHELL-8**: Session MUST write end event on normal termination.
- **I-SHELL-9**: Context mode (persistent/isolated) MUST be explicit.

### 3.4 Write Invariants

- **I-SHELL-10**: MUST NOT write directly to PRISTINE paths.
- **I-SHELL-11**: MUST NOT make LLM calls without governed prompts.
- **I-SHELL-12**: MUST NOT execute scripts outside declared execute patterns.

---

## 4. Command Syntax Standard (Interactive Mode)

### 4.1 Vim-Style Command Prefix

All shell commands MUST use the `:` prefix (vim-style):

```
:command [args]
```

### 4.2 Required Commands

| Command | Short | Description |
|---------|-------|-------------|
| `:help` | `:h` | Show help |
| `:quit` | `:q` | Exit shell |
| `:clear` | `:c` | Clear screen |
| `:state` | `:s` | Show JSON state |
| `:agent` | `:a` | Show agent info |

### 4.3 Optional Commands by Capability

| Capability | Commands |
|------------|----------|
| MEMORY | `:memory`, `:m` |
| SIGNALS | `:sig`, `:signals` |
| TRUST | `:trust`, `:t`, `:learn`, `:l` |
| NOTES | `:notes`, `:n`, `:n+`, `:nd+` |
| GOVERNANCE | `:pkg`, `:ledger`, `:gate`, `:wo` |

### 4.4 Shell Passthrough

Shells SHOULD support `:!` for shell command passthrough:

```
:! ls -la
:! git status
```

---

## 5. Signal Display Standard

### 5.1 Compact Signal Strip

Signal strips MUST use this format:

```
<stance> · <altitude> · <health_bar> · <turn> | <context_info>
```

Example:
```
engaged · L2 · [████░] · t5 | ctx:1.2k/200k (0.6%)
```

### 5.2 Signal Icons

| Signal | Icons |
|--------|-------|
| Stance | ● (grounded), ◉ (engaged), ◈ (committed), ◇ (protective) |
| Altitude | L1-L4 or ▽ (surface), ◇ (normal), △ (deep) |
| Trust | ● (high), ◐ (medium), ○ (low) |
| Learning | ◉ (active), · (idle) |
| Progress | ↑ (up), → (flat), ↓ (down) |

### 5.3 Health Bar

```
[█████]  1.0 (healthy)
[████░]  0.8 (good)
[███░░]  0.6 (moderate)
[██░░░]  0.4 (degraded)
[█░░░░]  0.2 (poor)
```

---

## 6. Session Lifecycle Standard

### 6.1 Session Start

1. Generate session ID: `SES-<YYYYMMDD>-<random8>`
2. Create session directory: `planes/<tier>/sessions/<session_id>/`
3. Initialize ledger files: `ledger/exec.jsonl`, `ledger/evidence.jsonl`
4. Log session start event

### 6.2 Session Processing

For each turn:
1. Increment turn counter
2. Check capability before command execution
3. Execute command
4. Log to L-EXEC with command_hash and result_hash
5. Log evidence with declared_reads, declared_writes

### 6.3 Session End

1. Log session end event
2. Write final ledger entries
3. Clean up temporary files

---

## 7. Agent Interface Protocol

### 7.1 CPAgentInterface

Shells MUST use agents implementing `CPAgentInterface`:

```python
class CPAgentInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> set[CPAgentCapability]: ...

    @abstractmethod
    def process(self, user_input: str) -> AgentResponse: ...

    @abstractmethod
    def get_signals(self) -> CPSignalBundle: ...

    @abstractmethod
    def get_state(self) -> dict: ...
```

### 7.2 CPAgentCapability

Standard capabilities:
- `MEMORY` - Session memory
- `CONSENT` - Consent management
- `SIGNALS` - Signal tracking
- `TRUST` - Trust system
- `COMMITMENTS` - Commitment management
- `FILESYSTEM` - File access
- `EMERGENCY` - Emergency stop
- `GOVERNANCE` - Control Plane queries (NEW)
- `LEDGER` - Ledger read/write (NEW)
- `PACKAGE_MGT` - Package queries (NEW)

### 7.3 CPSignalBundle

Extended signal bundle for Control Plane:

```python
@dataclass
class CPSignalBundle(SignalBundle):
    tier: str = "ho1"
    role: Optional[str] = None
    active_wo: Optional[str] = None
    ledger_synced: bool = True
    gate_state: str = "open"
```

---

## 8. Error Handling Standard

### 8.1 Fail-Closed

On error, shells MUST:
1. Log error to ledger
2. Display clear error message
3. Provide recovery hints where possible
4. NOT leave partial state

### 8.2 Error Display

```
✗ Error message here
  Hint: Recovery suggestion
```

### 8.3 Capability Violation

When capability is denied:

```
✗ Capability denied: read on lib/secret.py
  Hint: This path is forbidden by package manifest
```

---

## 9. Context Mode Standard

### 9.1 Modes

| Mode | Description |
|------|-------------|
| `persistent` | Full conversation history sent to LLM |
| `isolated` | Only current prompt sent, history preserved on disk |

### 9.2 Mode Switching

```
:ctx           Show current mode
:ctx persistent  Switch to persistent mode
:ctx isolated    Switch to isolated mode
```

---

## 10. Integration Requirements

### 10.1 Required Integrations

| Component | Usage |
|-----------|-------|
| Session | Session lifecycle management |
| LedgerWriter | Dual ledger writes (L-EXEC, L-EVIDENCE) |
| CapabilityEnforcer | Read/write/execute enforcement |
| CPInspector | Control Plane queries |

### 10.2 Optional Integrations

| Component | Usage |
|-----------|-------|
| Router | Query classification |
| AdminAgent | Health checks |
| StdlibLLM | LLM-assisted commands |

---

## 11. File Structure

### 11.1 Shell Module Layout

```
modules/shell/
├── __init__.py          # Exports: UniversalShell, CPAgentInterface
├── __main__.py          # Pipe-first entry point (NEW - FMWK-100 §7)
├── operations.py        # Operation handlers for pipe mode (NEW)
├── shell.py             # Main shell class (interactive mode)
├── chat_ui.py           # Terminal UI
├── interfaces.py        # Agent protocol
├── commands/            # Command handlers (interactive mode)
│   ├── __init__.py
│   ├── core.py          # :help, :quit, :clear, :state
│   ├── memory.py        # :memory, :v, :ctx
│   ├── signals.py       # :sig, :trust, :learn
│   ├── governance.py    # :pkg, :ledger, :gate, :wo
│   └── notes.py         # :notes, :n+, :nd+
├── capabilities.json    # Capability manifest
└── README.md            # Usage documentation
```

---

## 12. Testing Requirements

### 12.1 Required Tests - Interactive Mode

- Shell initialization with session
- Command dispatch (routing)
- Core commands (:h, :q, :s, :c)
- Capability enforcement
- Ledger logging

### 12.2 Required Tests - Pipe Mode (NEW)

- Response envelope format (status, result, evidence)
- All operations return valid responses
- Error handling (invalid JSON, unknown operation, missing fields)
- Evidence emission (timestamp, declared_reads)
- Exit codes (0 for ok, 1 for error)

### 12.3 Test Commands

```bash
# Run all shell tests
pytest tests/test_shell.py tests/test_shell_commands.py tests/test_shell_pipe.py -v

# Run pipe-first tests only
pytest tests/test_shell_pipe.py -v

# Interactive mode tests only
pytest tests/test_shell.py tests/test_shell_commands.py -v
```

---

## 13. Compliance Declaration

Shells declare framework compliance in package manifest:

```json
{
  "spec_id": "SPEC-SHELL-001",
  "frameworks": ["FMWK-SHELL-001", "FMWK-100"]
}
```

---

## Metadata

```yaml
framework_id: FMWK-SHELL-001
name: Shell/CLI Development Standard
version: 1.1.0
status: active
created: 2026-02-03
updated: 2026-02-04
category: Interface
dependencies: [FMWK-100, FMWK-000]
provides: [terminal_interface, command_dispatch, session_management, pipe_interface]
ci_gate: required
```
