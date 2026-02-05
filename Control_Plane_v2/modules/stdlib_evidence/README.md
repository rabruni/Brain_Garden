# Evidence Emission Standard Library

Foundational utilities for generating cryptographic evidence, computing hashes, and building evidence envelopes that link agent execution to the Control Plane's audit trail.

## Purpose

This is a Tier 0 (T0) trust baseline library that provides:
- Deterministic SHA256 hashing of JSON objects and files
- Evidence envelope construction with required linkage fields
- Artifact reference building for ledger entries
- Pipe-first CLI interface for standalone invocation

All higher-tier modules depend on this library for evidence generation.

## Usage

### Python API

```python
from modules.stdlib_evidence import hash_json, hash_file, build_evidence, build_reference

# Hash a JSON object (deterministic - key order doesn't matter)
data = {"query": "explain FMWK-000", "options": {"verbose": True}}
h = hash_json(data)  # sha256:...

# Hash a file
h = hash_file("path/to/file.py")  # sha256:...

# Build evidence envelope
evidence = build_evidence(
    session_id="SES-abc123",
    turn_number=1,
    input_hash=hash_json({"query": "..."}),
    output_hash=hash_json({"result": "..."}),
    work_order_id="WO-xyz789",  # Optional
    declared_reads=[{"path": "config.json", "hash": "sha256:..."}],
    declared_writes=[],
    external_calls=[{"request_id": "REQ-001", "provider": "anthropic", "model": "claude-opus-4-5-20251101", "cached": False}],
    duration_ms=150
)

# Build artifact reference
ref = build_reference(
    artifact_id="PKG-KERNEL-001",
    hash="sha256:...",
    artifact_type="package"
)
```

### CLI (Pipe-First)

```bash
# Build evidence envelope
echo '{
  "operation": "build_evidence",
  "session_id": "SES-abc123",
  "turn_number": 1,
  "input": {"query": "explain FMWK-000"},
  "output": {"result": "FMWK-000 is..."}
}' | python3 -m modules.stdlib_evidence

# Hash data
echo '{
  "operation": "hash",
  "data": {"key": "value"}
}' | python3 -m modules.stdlib_evidence

# Build reference
echo '{
  "operation": "reference",
  "artifact_id": "PKG-KERNEL-001",
  "hash": "sha256:abc123"
}' | python3 -m modules.stdlib_evidence
```

## Dependencies

- Python 3.9+ standard library only (hashlib, json, sys)
- No external dependencies

## Examples

### Computing Deterministic Hashes

```python
from modules.stdlib_evidence import hash_json

# Key order doesn't affect hash
assert hash_json({"b": 2, "a": 1}) == hash_json({"a": 1, "b": 2})

# Nested structures work
data = {"config": {"nested": {"deep": True}}, "items": [1, 2, 3]}
h = hash_json(data)
```

### Building Evidence for Agent Turns

```python
from modules.stdlib_evidence import hash_json, build_evidence

# Input and output from an agent turn
input_data = {"query": "What is FMWK-000?"}
output_data = {"result": "FMWK-000 is the root governance framework..."}

evidence = build_evidence(
    session_id="SES-" + uuid.uuid4().hex[:8],
    turn_number=1,
    input_hash=hash_json(input_data),
    output_hash=hash_json(output_data)
)

# Evidence is ready for ledger writing
print(evidence["session_id"])   # SES-abc123
print(evidence["turn_number"])  # 1
print(evidence["timestamp"])    # 2026-02-03T12:00:00+00:00
```

## Specification

See `specs/SPEC-EVIDENCE-001/` for the full specification including:
- Problem statement (01_problem.md)
- Design rationale (02_solution.md)
- Requirements (03_requirements.md)
- Test plan (05_testing.md)
