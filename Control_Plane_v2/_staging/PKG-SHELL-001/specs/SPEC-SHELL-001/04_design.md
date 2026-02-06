# Design

## Architecture

### Module Structure

```
modules/shell/
├── __init__.py              # Exports: UniversalShell, CPAgentInterface
├── shell.py                 # Main shell (adapted from shell/main.py)
├── chat_ui.py               # Terminal UI (from cli/chat_ui.py)
├── interfaces.py            # Agent protocol (adapted from interfaces/agent.py)
├── commands/                # Command handlers (modular)
│   ├── __init__.py          # Command registry
│   ├── core.py              # :help, :quit, :clear, :state
│   ├── memory.py            # :memory, :v, :ctx
│   ├── signals.py           # :sig, :trust, :learn
│   ├── governance.py        # :pkg, :ledger, :gate, :wo (NEW)
│   └── notes.py             # :notes, :n+, :nd+
├── capabilities.json        # Capability declaration
└── README.md                # Usage documentation
```

### Component Interactions

```
User Input → UniversalShell.process()
    ↓
Command Router
    ↓
┌───────────────────────────────────┐
│ If command (starts with :)        │
│   → CapabilityEnforcer.check()    │
│   → Command Handler               │
│   → LedgerWriter.write_turn()     │
├───────────────────────────────────┤
│ If query (natural language)       │
│   → Agent.process()               │
│   → Response with SignalBundle    │
│   → LedgerWriter.write_turn()     │
└───────────────────────────────────┘
    ↓
ChatUI.print_*() → Terminal Output
```

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `modules/shell/__init__.py` | Create | Module exports |
| `modules/shell/shell.py` | Create | Main shell adapted from source |
| `modules/shell/chat_ui.py` | Create | Terminal UI from source |
| `modules/shell/interfaces.py` | Create | Agent protocol with CP extensions |
| `modules/shell/commands/__init__.py` | Create | Command registry |
| `modules/shell/commands/core.py` | Create | Core commands |
| `modules/shell/commands/memory.py` | Create | Memory commands |
| `modules/shell/commands/signals.py` | Create | Signal commands |
| `modules/shell/commands/governance.py` | Create | New CP commands |
| `modules/shell/commands/notes.py` | Create | Note commands |
| `modules/shell/capabilities.json` | Create | Capability manifest |
| `modules/shell/README.md` | Create | Usage documentation |
| `scripts/shell.py` | Create | Entry point |
| `tests/test_shell.py` | Create | Shell tests |
| `tests/test_shell_commands.py` | Create | Command tests |
| `registries/frameworks_registry.csv` | Modify | Add FMWK-SHELL-001 |
| `registries/specs_registry.csv` | Modify | Add SPEC-SHELL-001 |

## Key Adaptations

### Session Integration

Original `SessionLogger` writes to `logs/YYYY-MM-DD.log`. Adapted to use `LedgerWriter`:

```python
from modules.agent_runtime.session import Session
from modules.agent_runtime.ledger_writer import LedgerWriter

class UniversalShell:
    def __init__(self, agent, config, debug=False):
        self.session = Session(tier="ho1")
        self.session.start()
        self.ledger = LedgerWriter(self.session)

    def _log_command(self, command: str, result: str):
        self.ledger.write_turn(
            turn_number=self._turn,
            exec_entry={
                "command": command,
                "command_hash": hash_json({"cmd": command}),
                "result_hash": hash_json({"result": result}),
                "status": "ok"
            },
            evidence_entry={
                "declared_reads": self._reads_this_turn,
                "declared_writes": [],
                "external_calls": []
            }
        )
```

### Extended Agent Interface

Add GOVERNANCE capability:

```python
class CPAgentCapability(Enum):
    MEMORY = "memory"
    CONSENT = "consent"
    SIGNALS = "signals"
    TRUST = "trust"
    COMMITMENTS = "commitments"
    FILESYSTEM = "filesystem"
    EMERGENCY = "emergency"
    # NEW for Control Plane
    GOVERNANCE = "governance"
    LEDGER = "ledger"
    PACKAGE_MGT = "package_mgt"
```

### New CP Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `:pkg` | `cmd_pkg_list` | List installed packages |
| `:pkg <id>` | `cmd_pkg_info` | Show package details |
| `:ledger` | `cmd_ledger_show` | Show recent ledger entries |
| `:gate` | `cmd_gate_status` | Show gate status |
| `:wo` | `cmd_wo_list` | List work orders |
| `:compliance` | `cmd_compliance` | Query compliance info |
| `:trace <id>` | `cmd_trace` | Trace artifact lineage |
