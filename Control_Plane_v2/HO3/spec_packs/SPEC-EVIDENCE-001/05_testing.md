# Testing

## Test Command

```bash
$ pytest tests/test_stdlib_evidence.py tests/test_stdlib_evidence_pipe.py -v
```

## Test Cases

### Unit Tests (test_stdlib_evidence.py)

#### TC-EV-001: Deterministic JSON Hashing
```python
def test_hash_json_deterministic():
    """Same input produces same hash regardless of key order."""
    obj1 = {"a": 1, "b": 2, "c": [3, 4]}
    obj2 = {"c": [3, 4], "b": 2, "a": 1}
    assert hash_json(obj1) == hash_json(obj2)
```

#### TC-EV-002: Hash Format
```python
def test_hash_format():
    """Hash output has correct format."""
    result = hash_json({"test": "data"})
    assert result.startswith("sha256:")
    assert len(result) == 71  # "sha256:" + 64 hex chars
```

#### TC-EV-003: Empty Object Hash
```python
def test_hash_empty_object():
    """Empty object hashes consistently."""
    assert hash_json({}) == hash_json({})
```

#### TC-EV-004: File Hashing
```python
def test_hash_file(tmp_path):
    """File hash matches expected value."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")
    result = hash_file(test_file)
    assert result.startswith("sha256:")
```

#### TC-EV-005: Evidence Envelope Required Fields
```python
def test_build_evidence_required_fields():
    """Evidence envelope contains all required fields."""
    evidence = build_evidence(
        session_id="SES-123",
        turn_number=1,
        input_hash="sha256:abc",
        output_hash="sha256:def"
    )
    assert evidence["session_id"] == "SES-123"
    assert evidence["turn_number"] == 1
    assert "timestamp" in evidence
    assert evidence["input_hash"] == "sha256:abc"
    assert evidence["output_hash"] == "sha256:def"
```

#### TC-EV-006: Evidence Envelope Optional Fields
```python
def test_build_evidence_optional_fields():
    """Evidence envelope includes optional fields when provided."""
    evidence = build_evidence(
        session_id="SES-123",
        turn_number=1,
        input_hash="sha256:abc",
        output_hash="sha256:def",
        work_order_id="WO-456",
        declared_reads=[{"path": "test.json", "hash": "sha256:xyz"}],
        declared_writes=[],
        external_calls=[],
        duration_ms=100
    )
    assert evidence["work_order_id"] == "WO-456"
    assert evidence["declared_reads"] == [{"path": "test.json", "hash": "sha256:xyz"}]
    assert evidence["duration_ms"] == 100
```

#### TC-EV-007: Build Reference
```python
def test_build_reference():
    """Artifact reference has correct structure."""
    ref = build_reference("ART-001", "sha256:abc")
    assert ref["artifact_id"] == "ART-001"
    assert ref["hash"] == "sha256:abc"
    assert "timestamp" in ref
```

### Pipe Tests (test_stdlib_evidence_pipe.py)

#### TC-EV-008: CLI Success Response
```python
def test_cli_success(tmp_path):
    """CLI returns success envelope for valid input."""
    input_json = json.dumps({
        "operation": "build_evidence",
        "session_id": "SES-123",
        "turn_number": 1,
        "input": {"query": "test"},
        "output": {"result": "ok"}
    })
    result = subprocess.run(
        ["python3", "-m", "modules.stdlib_evidence"],
        input=input_json,
        capture_output=True,
        text=True,
        cwd=CONTROL_PLANE_ROOT
    )
    assert result.returncode == 0
    response = json.loads(result.stdout)
    assert response["status"] == "ok"
    assert "evidence" in response
```

#### TC-EV-009: CLI Error Response
```python
def test_cli_invalid_json():
    """CLI returns error envelope for invalid JSON."""
    result = subprocess.run(
        ["python3", "-m", "modules.stdlib_evidence"],
        input="not valid json",
        capture_output=True,
        text=True,
        cwd=CONTROL_PLANE_ROOT
    )
    assert result.returncode == 1
    response = json.loads(result.stdout)
    assert response["status"] == "error"
    assert response["error"]["code"] == "INVALID_JSON"
```

#### TC-EV-010: CLI No Side Effects
```python
def test_cli_no_side_effects(tmp_path):
    """CLI creates no files."""
    before_files = set(tmp_path.rglob("*"))
    subprocess.run(
        ["python3", "-m", "modules.stdlib_evidence"],
        input='{"operation": "build_evidence", "session_id": "SES-1", "turn_number": 1, "input": {}, "output": {}}',
        capture_output=True,
        text=True,
        cwd=tmp_path
    )
    after_files = set(tmp_path.rglob("*"))
    assert before_files == after_files
```

## Verification Checklist

- [ ] All test cases pass
- [ ] Hash determinism verified across multiple runs
- [ ] CLI follows pipe-first contract
- [ ] No filesystem side effects
- [ ] Error handling returns proper envelope
- [ ] Required linkage fields present in all evidence
- [ ] Code coverage > 90%
