# Testing

## Test Command

```bash
$ pytest tests/test_admin_agent.py -v
```

## Test Cases

### Unit Tests (test_admin_agent.py)

#### TC-ADM-001: Explain Framework
```python
def test_explain_framework():
    """Admin Agent can explain a framework."""
    agent = AdminAgent()
    result = agent.explain("FMWK-000")
    assert "governance" in result.lower() or "framework" in result.lower()
    assert "FMWK-000" in result
```

#### TC-ADM-002: Explain Spec
```python
def test_explain_spec():
    """Admin Agent can explain a spec."""
    agent = AdminAgent()
    result = agent.explain("SPEC-CORE-001")
    assert "SPEC-CORE-001" in result
```

#### TC-ADM-003: Explain Package
```python
def test_explain_package():
    """Admin Agent can explain a package."""
    agent = AdminAgent()
    result = agent.explain("PKG-KERNEL-001")
    assert "PKG-KERNEL-001" in result
```

#### TC-ADM-004: Explain File
```python
def test_explain_file():
    """Admin Agent can explain a file."""
    agent = AdminAgent()
    result = agent.explain("lib/merkle.py")
    assert "merkle" in result.lower()
```

#### TC-ADM-005: List Installed
```python
def test_list_installed():
    """Admin Agent can list installed packages."""
    agent = AdminAgent()
    result = agent.list_installed()
    assert "PKG-" in result or "No packages" in result
```

#### TC-ADM-006: Check Health
```python
def test_check_health():
    """Admin Agent can check system health."""
    agent = AdminAgent()
    result = agent.check_health()
    assert "PASS" in result or "FAIL" in result or "health" in result.lower()
```

#### TC-ADM-007: Unknown Artifact
```python
def test_unknown_artifact():
    """Admin Agent handles unknown artifacts gracefully."""
    agent = AdminAgent()
    result = agent.explain("NONEXISTENT-999")
    assert "not found" in result.lower() or "unknown" in result.lower()
```

### Integration Tests

#### TC-ADM-008: Turn Logs to L-EXEC
```python
def test_turn_logs_to_lexec(tmp_path):
    """Admin turn creates L-EXEC entry."""
    result = admin_turn(
        "explain FMWK-000",
        session_id="SES-test",
        turn_number=1,
        root=tmp_path
    )
    exec_path = tmp_path / "planes" / "ho1" / "sessions" / "SES-test" / "ledger" / "exec.jsonl"
    assert exec_path.exists()
    with open(exec_path) as f:
        entry = json.loads(f.readline())
    assert entry["session_id"] == "SES-test"
    assert entry["turn_number"] == 1
```

#### TC-ADM-009: Turn Logs to L-EVIDENCE
```python
def test_turn_logs_to_levidence(tmp_path):
    """Admin turn creates L-EVIDENCE entry."""
    result = admin_turn(
        "list packages",
        session_id="SES-test",
        turn_number=1,
        root=tmp_path
    )
    evidence_path = tmp_path / "planes" / "ho1" / "sessions" / "SES-test" / "ledger" / "evidence.jsonl"
    assert evidence_path.exists()
    with open(evidence_path) as f:
        entry = json.loads(f.readline())
    assert "session_id" in entry
    assert "turn_number" in entry
```

#### TC-ADM-010: Read-Only Enforcement
```python
def test_read_only_enforcement(tmp_path):
    """Admin Agent cannot write to PRISTINE paths."""
    agent = AdminAgent(root=tmp_path)
    # Verify capabilities are read-only
    from modules.agent_runtime import CapabilityEnforcer
    import json
    caps_path = Path(__file__).parent.parent / "modules" / "admin_agent" / "capabilities.json"
    with open(caps_path) as f:
        caps = json.load(f)["capabilities"]
    enforcer = CapabilityEnforcer(caps)
    # Should not be able to write to lib/
    assert enforcer.is_forbidden("lib/anything.py")
```

## Verification Checklist

- [ ] All test cases pass
- [ ] Admin Agent explains frameworks, specs, packages, files
- [ ] List installed packages works
- [ ] Health check works
- [ ] Unknown artifacts handled gracefully
- [ ] L-EXEC entries created for all turns
- [ ] L-EVIDENCE entries include required fields
- [ ] No PRISTINE writes (sandbox passes with empty outputs)
- [ ] Code coverage > 90%
