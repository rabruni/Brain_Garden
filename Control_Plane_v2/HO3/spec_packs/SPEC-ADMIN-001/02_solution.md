# Proposed Solution

## Overview

Create a T3 (agent tier) package `modules/admin_agent/` that:

1. **Wraps trace.py**: Uses the existing kernel-native trace capability for low-level operations
2. **Adds reasoning layer**: Formats trace output for human consumption
3. **Operates within governance**: Uses AgentRunner for capability enforcement and ledger writing
4. **Demonstrates agent pattern**: Shows how agents can be both governed artifacts and system operators

## Architecture

```
modules/admin_agent/
├── __init__.py         # Public API
├── agent.py            # AdminAgent class, wraps trace.py
├── capabilities.json   # Declared capabilities (read-only)
└── README.md
```

## Key Design Decisions

### 1. Wrapper Pattern

The Admin Agent wraps `trace.py` rather than reimplementing its logic:

```python
def explain(self, artifact_id: str) -> str:
    raw = subprocess.check_output([
        "python3", "scripts/trace.py",
        "--explain", artifact_id, "--json"
    ])
    return self._format_for_human(json.loads(raw))
```

Benefits:
- Reuses proven kernel code
- trace.py remains the single source of truth
- Easier maintenance

### 2. Read-Only Capabilities

The Admin Agent declares read-only capabilities:

```json
{
  "capabilities": {
    "read": ["ledger/*.jsonl", "registries/*.csv", "installed/*", ...],
    "execute": ["scripts/trace.py --explain", "scripts/trace.py --installed", ...],
    "write": ["planes/ho1/sessions/<session_id>/ledger/exec.jsonl"],
    "forbidden": ["lib/*", "scripts/package_install.py", ...]
  }
}
```

The only writes are to the session ledger (L-EXEC), which is required by FMWK-100.

### 3. Simple Query Classification

Queries are classified into categories and routed to appropriate handlers:

```python
if is_explain_query(query):
    return self._handle_explain(query)
elif is_list_query(query):
    return self._handle_list(query)
elif is_status_query(query):
    return self._handle_status(query)
else:
    return self._handle_general(query)
```

### 4. Evidence Emission

Every turn emits evidence with required linkage fields:

```python
evidence = {
    "session_id": session_id,
    "turn_number": turn_number,
    "query_hash": hash_json(query),
    "result_hash": hash_json(result),
    "declared_reads": [],  # trace.py reads are internal
    "declared_writes": [],  # Read-only agent
    "external_calls": []   # No LLM calls in Phase 1
}
```

## Alternatives Considered

### Alternative 1: Direct registry access

**Rejected because:** Would duplicate trace.py logic and create maintenance burden.

### Alternative 2: Full LLM integration

**Rejected because:** Phase 1 focuses on demonstrating governance, not LLM capabilities. LLM integration deferred to Phase 2.

### Alternative 3: Separate package outside modules/

**Rejected because:** Correction #9 requires all packages in modules/, not new top-level roots.

## Risks

1. **trace.py changes**: If trace.py API changes, Admin Agent needs updates. Mitigation: trace.py uses stable CLI interface.

2. **Output formatting**: Human-readable formatting is subjective. Mitigation: Start simple, iterate based on feedback.

3. **Query misclassification**: Queries might be routed to wrong handler. Mitigation: Default to general handler, accept partial matches.
