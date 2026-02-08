# Design

## Architecture

```
modules/admin_agent/
├── __init__.py         # Public API: AdminAgent, admin_turn
├── agent.py            # AdminAgent class with query handlers
├── capabilities.json   # Declared read-only capabilities
└── README.md
```

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `modules/admin_agent/__init__.py` | CREATE | Public API exports |
| `modules/admin_agent/agent.py` | CREATE | AdminAgent class |
| `modules/admin_agent/capabilities.json` | CREATE | Capability declarations |
| `modules/admin_agent/README.md` | CREATE | Module documentation |
| `tests/test_admin_agent.py` | CREATE | Unit tests |

## Dependencies

### Internal Dependencies
- `modules/agent_runtime/` (T1 runtime)
- `modules/stdlib_evidence/` (T0 evidence)
- `scripts/trace.py` (kernel explainer)

### External Dependencies
- Python 3.9+ standard library
- subprocess for trace.py invocation

## API Design

### agent.py

```python
class AdminAgent:
    """Read-only agent for explaining the Control Plane."""

    def __init__(self, root: Path = None):
        """Initialize Admin Agent."""

    def explain(self, artifact_id: str) -> str:
        """Explain any artifact (framework, spec, package, file)."""

    def list_installed(self) -> str:
        """List installed packages with details."""

    def check_health(self) -> str:
        """Check system health and return status."""

    def get_context(self) -> dict:
        """Get agent context for prompt headers."""


def admin_turn(
    user_query: str,
    session_id: str = None,
    turn_number: int = 1,
) -> str:
    """Execute one admin agent turn (stateless)."""
```

## Capabilities Declaration

```json
{
  "capabilities": {
    "read": [
      "ledger/*.jsonl",
      "planes/*/ledger/*.jsonl",
      "planes/*/sessions/*/ledger/*.jsonl",
      "registries/*.csv",
      "installed/*/manifest.json",
      "installed/*/receipt.json",
      "config/*.json",
      "frameworks/*.md",
      "specs/*/manifest.yaml"
    ],
    "execute": [
      "scripts/trace.py --explain",
      "scripts/trace.py --installed",
      "scripts/trace.py --inventory",
      "scripts/trace.py --verify",
      "scripts/integrity_check.py --json"
    ],
    "write": [
      "planes/ho1/sessions/<session_id>/ledger/exec.jsonl",
      "planes/ho1/sessions/<session_id>/ledger/evidence.jsonl"
    ],
    "forbidden": [
      "lib/*",
      "scripts/package_install.py",
      "scripts/package_pack.py",
      "scripts/wo_approve.py"
    ]
  }
}
```

## Query Classification

| Pattern | Handler | trace.py Command |
|---------|---------|------------------|
| "explain X" / "what is X" | _handle_explain | --explain X |
| "list packages" / "installed" | _handle_list | --installed |
| "health" / "status" / "verify" | _handle_status | --verify |
| "inventory" | _handle_inventory | --inventory |
| Other | _handle_general | --explain (best guess) |

## Turn Execution Flow

```
1. Receive user query
2. Generate/use session_id
3. Classify query
4. Enter sandbox (empty declared_outputs for read-only)
5. Invoke trace.py via subprocess
6. Format output for human consumption
7. Verify no writes occurred (sandbox.verify_writes)
8. Write L-EXEC entry
9. Write L-EVIDENCE entry
10. Return formatted result
```
