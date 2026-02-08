# Design

## Architecture

```
modules/stdlib_evidence/
├── __init__.py        # Public API: hash_json, hash_file, build_evidence, build_reference
├── hasher.py          # SHA256 hashing utilities
├── envelope.py        # Evidence envelope builder with linkage fields
├── reference.py       # Artifact reference builder
└── __main__.py        # CLI entrypoint (pipe-first)
```

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `modules/stdlib_evidence/__init__.py` | CREATE | Public API exports |
| `modules/stdlib_evidence/hasher.py` | CREATE | SHA256 hashing utilities |
| `modules/stdlib_evidence/envelope.py` | CREATE | Evidence envelope builder |
| `modules/stdlib_evidence/reference.py` | CREATE | Artifact reference builder |
| `modules/stdlib_evidence/__main__.py` | CREATE | CLI entrypoint |
| `schemas/stdlib_evidence_request.json` | CREATE | Input schema |
| `schemas/stdlib_evidence_response.json` | CREATE | Output schema |
| `tests/test_stdlib_evidence.py` | CREATE | Unit tests |
| `tests/test_stdlib_evidence_pipe.py` | CREATE | Pipe-first integration tests |

## Dependencies

### Internal Dependencies
- None (T0 has no dependencies on higher tiers)

### External Dependencies
- Python 3.9+ standard library only
- `hashlib` for SHA256
- `json` for serialization
- `sys` for stdin/stdout

## API Design

### hasher.py

```python
def hash_json(obj: dict) -> str:
    """Compute deterministic SHA256 hash of JSON object.

    Args:
        obj: JSON-serializable dictionary

    Returns:
        Hash string in format "sha256:<64_hex_chars>"
    """

def hash_file(path: Path) -> str:
    """Compute SHA256 hash of file contents.

    Args:
        path: Path to file

    Returns:
        Hash string in format "sha256:<64_hex_chars>"

    Raises:
        FileNotFoundError: If file doesn't exist
    """

def hash_string(s: str) -> str:
    """Compute SHA256 hash of string.

    Args:
        s: Input string

    Returns:
        Hash string in format "sha256:<64_hex_chars>"
    """
```

### envelope.py

```python
def build_evidence(
    session_id: str,
    turn_number: int,
    input_hash: str,
    output_hash: str,
    work_order_id: str = None,
    declared_reads: list = None,
    declared_writes: list = None,
    external_calls: list = None,
    duration_ms: int = None,
    **kwargs
) -> dict:
    """Build evidence envelope with required linkage fields.

    Args:
        session_id: Required session identifier
        turn_number: Required turn number within session
        input_hash: Hash of input
        output_hash: Hash of output
        work_order_id: Optional work order reference
        declared_reads: Optional list of read file records
        declared_writes: Optional list of write file records
        external_calls: Optional list of external call records
        duration_ms: Optional execution duration

    Returns:
        Evidence envelope dictionary
    """
```

### reference.py

```python
def build_reference(artifact_id: str, hash: str, **kwargs) -> dict:
    """Build artifact reference for ledger entries.

    Args:
        artifact_id: Identifier of the artifact
        hash: Hash of the artifact

    Returns:
        Reference dictionary with artifact_id, hash, timestamp
    """
```

## CLI Request/Response Schema

### Request Schema
```json
{
  "operation": "build_evidence",
  "session_id": "SES-abc123",
  "turn_number": 1,
  "input": {"query": "..."},
  "output": {"result": "..."},
  "work_order_id": "WO-xyz789"
}
```

### Response Schema
```json
{
  "status": "ok",
  "result": {
    "input_hash": "sha256:...",
    "output_hash": "sha256:...",
    "evidence": {
      "session_id": "SES-abc123",
      "turn_number": 1,
      "work_order_id": "WO-xyz789",
      "input_hash": "sha256:...",
      "output_hash": "sha256:...",
      "timestamp": "2026-02-03T12:00:00Z"
    }
  },
  "evidence": {
    "session_id": "SES-abc123",
    "turn_number": 1,
    "input_hash": "sha256:...",
    "output_hash": "sha256:...",
    "timestamp": "2026-02-03T12:00:00Z"
  }
}
```
