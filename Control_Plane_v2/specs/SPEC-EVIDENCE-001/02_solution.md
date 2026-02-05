# Proposed Solution

## Overview

Create a T0 (trust baseline) standard library package `modules/stdlib_evidence/` that provides:

1. **Hasher module** (`hasher.py`): Deterministic SHA256 hashing utilities
2. **Envelope module** (`envelope.py`): Evidence envelope construction with required fields
3. **Reference module** (`reference.py`): Artifact reference building
4. **CLI entrypoint** (`__main__.py`): Pipe-first interface

## Architecture

```
modules/stdlib_evidence/
├── __init__.py        # Public API exports
├── hasher.py          # SHA256 hashing utilities
├── envelope.py        # Evidence envelope builder
├── reference.py       # Artifact reference builder
└── __main__.py        # CLI entrypoint
```

## Key Design Decisions

### 1. Deterministic Hashing

All JSON is serialized with `sort_keys=True` and `ensure_ascii=False` before hashing to guarantee reproducibility:

```python
def hash_json(obj: dict) -> str:
    json_str = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return f"sha256:{hashlib.sha256(json_str.encode('utf-8')).hexdigest()}"
```

### 2. Required Linkage Fields

Every evidence envelope MUST include session_id and turn_number for ledger linkage (per FMWK-100 Section 7.7):

```python
def build_evidence(
    session_id: str,      # REQUIRED
    turn_number: int,     # REQUIRED
    input_hash: str,
    output_hash: str,
    work_order_id: str = None,  # Required if under work order
    **kwargs
) -> dict:
```

### 3. Pipe-First Contract

The CLI reads JSON from stdin and writes JSON to stdout with the standard response envelope:

```bash
echo '{"session_id":"SES-123","turn_number":1,"input":{},"output":{}}' | python3 -m modules.stdlib_evidence
```

## Alternatives Considered

### Alternative 1: Inline evidence generation in each module

**Rejected because:** Would lead to inconsistencies and code duplication across all modules.

### Alternative 2: Evidence generation in the runtime only

**Rejected because:** Modules need to emit evidence metadata for their own operations (e.g., external call logging). Having utilities available allows consistent evidence even for module-internal operations.

## Risks

1. **Hash algorithm changes**: If SHA256 is compromised, we'd need to migrate. Mitigation: Include algorithm prefix in hash strings (`sha256:...`).

2. **JSON serialization edge cases**: Different Python versions might serialize edge cases differently. Mitigation: Use explicit sort_keys and avoid floats where possible.

3. **Missing required fields**: Modules might forget to include session_id/turn_number. Mitigation: Runtime validation before ledger write, clear documentation, type hints.
