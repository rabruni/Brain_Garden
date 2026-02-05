# Agent Runtime Module

Execution framework for agents operating within the Control Plane governance model. Handles capability enforcement, session management, sandbox isolation, ledger writing, and context assembly.

## Purpose

This is a Tier 1 (T1) runtime module that provides:
- **AgentRunner**: Load agent packages and execute turns with capability enforcement
- **CapabilityEnforcer**: Check and enforce read/write/execute permissions
- **Session**: Generate session IDs, manage session lifecycle
- **TurnSandbox**: OS-level write isolation for each turn
- **LedgerWriter**: Write to both L-EXEC and L-EVIDENCE ledgers
- **PromptBuilder**: Assemble prompt headers from ledger state
- **AgentMemory**: Ledger replay with checkpoint acceleration

All T3 agents depend on this runtime for governed execution.

## Usage

### Basic Turn Execution

```python
from modules.agent_runtime import AgentRunner, TurnRequest, TurnResult

# Create runner for a specific agent package
runner = AgentRunner("PKG-ADMIN-001", tier="ho1")

# Define handler for processing turns
def my_handler(request: TurnRequest) -> TurnResult:
    # Agent logic here
    answer = process_query(request.query)
    return TurnResult(
        status="ok",
        result={"answer": answer},
        evidence={}
    )

# Create turn request
request = TurnRequest(
    session_id="SES-20260203-abc123",
    turn_number=1,
    query={"question": "What is FMWK-000?"},
    declared_inputs=[],
    declared_outputs=[]  # Empty for read-only turns
)

# Execute turn
result = runner.execute_turn(request, my_handler)
print(result.status)  # "ok" or "error"
```

### Capability Enforcement

```python
from modules.agent_runtime import CapabilityEnforcer, CapabilityViolation

capabilities = {
    "read": ["ledger/*.jsonl", "registries/*.csv"],
    "write": ["planes/ho1/sessions/*/ledger/exec.jsonl"],
    "execute": ["scripts/trace.py --explain"],
    "forbidden": ["lib/*", "scripts/package_install.py"]
}

enforcer = CapabilityEnforcer(capabilities)

# Check if operation is allowed
if enforcer.check("read", "ledger/governance.jsonl"):
    print("Read allowed")

# Enforce (raises CapabilityViolation if denied)
try:
    enforcer.enforce("write", "lib/secret.py")
except CapabilityViolation as e:
    print(f"Denied: {e}")
```

### Session Management

```python
from modules.agent_runtime import Session

with Session(tier="ho1") as session:
    print(f"Session ID: {session.session_id}")
    print(f"Ledger path: {session.ledger_path}")

    # Both ledgers are created automatically
    assert session.exec_ledger_path.exists()
    assert session.evidence_ledger_path.exists()
```

### Sandbox Isolation

```python
from modules.agent_runtime import TurnSandbox

declared_outputs = [
    {"path": "output/SES-123/result.json", "role": "result"}
]

with TurnSandbox("SES-123", declared_outputs) as sandbox:
    # Write only to declared paths
    (sandbox.output_root / "result.json").write_text('{"status": "ok"}')

# Verify writes match declarations
realized, valid = sandbox.verify_writes()
assert valid  # True if writes match
```

## Dependencies

- Python 3.9+ standard library
- `modules/stdlib_evidence/` (T0 evidence library)
- `lib/ledger_client.py` (kernel ledger support)

## Architecture

```
TurnRequest → AgentRunner.execute_turn(request, handler)
                   │
                   ├── Validate request (declared_outputs present)
                   ├── Check capabilities (CapabilityEnforcer)
                   ├── Create session (Session)
                   ├── Enter sandbox (TurnSandbox)
                   │      │
                   │      └── Execute handler
                   │
                   ├── Verify writes (sandbox.verify_writes())
                   ├── Write L-EXEC (LedgerWriter)
                   ├── Write L-EVIDENCE (LedgerWriter)
                   └── Return TurnResult
```

## Session Ledger Structure

```
planes/ho1/sessions/SES-20260203-abc123/
├── ledger/
│   ├── exec.jsonl       # L-EXEC: what happened
│   └── evidence.jsonl   # L-EVIDENCE: hashes, reads, writes
```

## Specification

See `specs/SPEC-RUNTIME-001/` for the full specification including:
- Problem statement (01_problem.md)
- Design rationale (02_solution.md)
- Requirements FR-RT-001 through FR-RT-018 (03_requirements.md)
- Test plan (05_testing.md)
