# Design

## Architecture

```
modules/agent_runtime/
├── __init__.py         # Public API exports
├── runner.py           # AgentRunner: load package, execute turns
├── capability.py       # CapabilityEnforcer: permission checking
├── session.py          # Session: ID generation, lifecycle
├── sandbox.py          # TurnSandbox: write isolation
├── prompt_builder.py   # PromptBuilder: context assembly
├── memory.py           # Memory: ledger replay, checkpoints
├── ledger_writer.py    # LedgerWriter: dual ledger writing
├── exceptions.py       # Custom exceptions
└── README.md
```

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `modules/agent_runtime/__init__.py` | CREATE | Public API exports |
| `modules/agent_runtime/runner.py` | CREATE | AgentRunner class |
| `modules/agent_runtime/capability.py` | CREATE | CapabilityEnforcer class |
| `modules/agent_runtime/session.py` | CREATE | Session management |
| `modules/agent_runtime/sandbox.py` | CREATE | TurnSandbox context manager |
| `modules/agent_runtime/prompt_builder.py` | CREATE | Prompt header construction |
| `modules/agent_runtime/memory.py` | CREATE | Ledger replay utilities |
| `modules/agent_runtime/ledger_writer.py` | CREATE | Dual ledger writer |
| `modules/agent_runtime/exceptions.py` | CREATE | CapabilityViolation, etc. |
| `modules/agent_runtime/README.md` | CREATE | Module documentation |
| `tests/test_agent_runtime.py` | CREATE | Unit tests |
| `tests/test_sandbox_failclosed.py` | CREATE | Sandbox enforcement tests |

## Dependencies

### Internal Dependencies
- `lib/ledger_client.py` - Ledger writing
- `lib/merkle.py` - Hash computation
- `modules/stdlib_evidence/` - Evidence envelope building

### External Dependencies
- Python 3.9+ standard library
- pathlib, json, os, uuid, fnmatch

## API Design

### runner.py

```python
class AgentRunner:
    """Execute agent turns with capability enforcement."""

    def __init__(self, package_id: str, tier: str = "ho1"):
        """Load agent package and capabilities."""

    def execute_turn(
        self,
        request: TurnRequest,
        handler: Callable[[TurnRequest], TurnResult]
    ) -> TurnResult:
        """Execute a single turn with full governance enforcement."""

    def _load_package(self, package_id: str) -> dict:
        """Load package manifest from installed directory."""

@dataclass
class TurnRequest:
    session_id: str
    turn_number: int
    query: Any
    declared_inputs: List[DeclaredInput]
    declared_outputs: List[DeclaredOutput]
    work_order_id: Optional[str] = None

@dataclass
class TurnResult:
    status: str  # "ok" | "error"
    result: Any
    evidence: dict
    error: Optional[dict] = None
```

### capability.py

```python
class CapabilityEnforcer:
    """Enforce read/write/execute capabilities."""

    def __init__(self, capabilities: dict):
        """Initialize with capabilities from manifest."""

    def check(self, operation: str, path: str) -> bool:
        """Check if operation is allowed on path."""

    def enforce(self, operation: str, path: str) -> None:
        """Enforce capability, raise CapabilityViolation if denied."""

    def is_forbidden(self, path: str) -> bool:
        """Check if path matches forbidden patterns."""
```

### session.py

```python
class Session:
    """Manage agent session lifecycle."""

    def __init__(self, tier: str = "ho1", work_order_id: str = None):
        """Create new session."""

    @property
    def session_id(self) -> str:
        """Get session ID (e.g., SES-20260203-abc123)."""

    @property
    def ledger_path(self) -> Path:
        """Get path to session ledger directory."""

    def __enter__(self) -> "Session":
        """Start session, create directories."""

    def __exit__(self, *args) -> None:
        """End session, finalize ledgers."""
```

### sandbox.py

```python
class TurnSandbox:
    """Execute a turn in a write-restricted sandbox."""

    def __init__(self, session_id: str, declared_outputs: List[dict]):
        """Initialize sandbox for session."""

    def __enter__(self) -> "TurnSandbox":
        """Enter sandbox: create dirs, set env vars."""

    def __exit__(self, *args) -> None:
        """Exit sandbox: restore env vars."""

    def verify_writes(self) -> Tuple[List[dict], bool]:
        """Enumerate realized writes and compare to declared."""
```

### ledger_writer.py

```python
class LedgerWriter:
    """Write to both L-EXEC and L-EVIDENCE ledgers."""

    def __init__(self, session: Session):
        """Initialize for session."""

    def write_turn(
        self,
        turn_number: int,
        exec_entry: dict,
        evidence_entry: dict
    ) -> None:
        """Write entries to both ledgers."""
```

## Session Ledger Structure

```
planes/ho1/sessions/SES-20260203-abc123/
├── ledger/
│   ├── exec.jsonl       # L-EXEC: what happened
│   └── evidence.jsonl   # L-EVIDENCE: hashes, reads, writes
```

## Sandbox Environment

```
TMPDIR = tmp/SES-20260203-abc123/
TEMP = tmp/SES-20260203-abc123/
TMP = tmp/SES-20260203-abc123/
PYTHONDONTWRITEBYTECODE = 1
```

## Turn Execution Flow

```
1. Validate request (declared_outputs present)
2. Check capabilities (read patterns, write patterns)
3. Enter sandbox (set env, create dirs)
4. Execute handler
5. Verify writes (realized == declared)
6. Write L-EXEC entry
7. Write L-EVIDENCE entry
8. Exit sandbox (restore env)
9. Return result
```
