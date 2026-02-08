# Testing

## Test Command

```bash
$ pytest tests/test_agent_runtime.py tests/test_sandbox_failclosed.py -v
```

## Test Cases

### Unit Tests (test_agent_runtime.py)

#### TC-RT-001: Capability Check Allow
```python
def test_capability_check_allow():
    """Allowed read paths return True."""
    enforcer = CapabilityEnforcer({
        "read": ["ledger/*.jsonl", "registries/*.csv"],
        "write": [],
        "execute": [],
        "forbidden": []
    })
    assert enforcer.check("read", "ledger/governance.jsonl") == True
```

#### TC-RT-002: Capability Check Deny
```python
def test_capability_check_deny():
    """Disallowed read paths return False."""
    enforcer = CapabilityEnforcer({
        "read": ["ledger/*.jsonl"],
        "write": [],
        "execute": [],
        "forbidden": []
    })
    assert enforcer.check("read", "lib/secret.py") == False
```

#### TC-RT-003: Capability Enforce Raises
```python
def test_capability_enforce_raises():
    """Denied operation raises CapabilityViolation."""
    enforcer = CapabilityEnforcer({"read": [], "write": [], "execute": [], "forbidden": []})
    with pytest.raises(CapabilityViolation):
        enforcer.enforce("read", "any/path.txt")
```

#### TC-RT-004: Forbidden Pattern Blocks
```python
def test_forbidden_pattern_blocks():
    """Forbidden patterns block even matching capabilities."""
    enforcer = CapabilityEnforcer({
        "read": ["**/*"],  # Would allow everything
        "write": [],
        "execute": [],
        "forbidden": ["lib/*"]  # But lib/ is forbidden
    })
    assert enforcer.is_forbidden("lib/secret.py") == True
    with pytest.raises(CapabilityViolation):
        enforcer.enforce("read", "lib/secret.py")
```

#### TC-RT-005: Session ID Format
```python
def test_session_id_format():
    """Session ID has correct format."""
    session = Session(tier="ho1")
    assert session.session_id.startswith("SES-")
    parts = session.session_id.split("-")
    assert len(parts) == 3  # SES-timestamp-random
```

#### TC-RT-006: Session Creates Ledger Directory
```python
def test_session_creates_ledger_directory(tmp_path):
    """Session creates ledger directory on entry."""
    with Session(tier="ho1", root=tmp_path) as session:
        ledger_path = session.ledger_path
        assert ledger_path.exists()
        assert (ledger_path / "exec.jsonl").exists()
        assert (ledger_path / "evidence.jsonl").exists()
```

#### TC-RT-007: Turn Request Validation
```python
def test_turn_request_requires_declared_outputs():
    """Turn request without declared_outputs raises error."""
    runner = AgentRunner("PKG-TEST-001")
    request = TurnRequest(
        session_id="SES-test",
        turn_number=1,
        query={"test": True},
        declared_inputs=[],
        declared_outputs=None  # Missing!
    )
    with pytest.raises(ValueError, match="declared_outputs"):
        runner.execute_turn(request, lambda r: TurnResult("ok", {}, {}))
```

### Sandbox Tests (test_sandbox_failclosed.py)

#### TC-SB-001: Undeclared Write Blocked
```python
def test_undeclared_write_blocked(tmp_path):
    """Turn that writes undeclared file MUST fail."""
    with Session(tier="ho1", root=tmp_path) as session:
        sandbox = TurnSandbox(session.session_id, declared_outputs=[])
        with sandbox:
            # Write an undeclared file
            (sandbox.sandbox_root / "sneaky.txt").write_text("bad")
        realized, valid = sandbox.verify_writes()
        assert valid == False
        assert len(realized) == 1  # One undeclared write
```

#### TC-SB-002: System Tmp Blocked
```python
def test_system_tmp_blocked(tmp_path, monkeypatch):
    """Writes to /tmp (not session-scoped) MUST fail."""
    original_tmpdir = os.environ.get("TMPDIR")
    with Session(tier="ho1", root=tmp_path) as session:
        sandbox = TurnSandbox(session.session_id, declared_outputs=[])
        with sandbox:
            # TMPDIR should be redirected
            assert os.environ["TMPDIR"].startswith(str(tmp_path))
```

#### TC-SB-003: Declared Write Succeeds
```python
def test_declared_write_succeeds(tmp_path):
    """Turn that writes only declared outputs MUST succeed."""
    with Session(tier="ho1", root=tmp_path) as session:
        declared = [{"path": f"output/{session.session_id}/result.json", "role": "result"}]
        sandbox = TurnSandbox(session.session_id, declared_outputs=declared, root=tmp_path)
        with sandbox:
            out_path = sandbox.output_root / "result.json"
            out_path.write_text('{"status": "ok"}')
        realized, valid = sandbox.verify_writes()
        assert valid == True
```

#### TC-SB-004: Pycache Blocked
```python
def test_pycache_blocked(tmp_path):
    """__pycache__ writes MUST be blocked via PYTHONDONTWRITEBYTECODE."""
    with Session(tier="ho1", root=tmp_path) as session:
        sandbox = TurnSandbox(session.session_id, declared_outputs=[])
        with sandbox:
            assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
```

#### TC-SB-005: Both Ledgers Written
```python
def test_both_ledgers_written(tmp_path):
    """Both exec.jsonl and evidence.jsonl MUST be written per turn."""
    runner = AgentRunner("PKG-TEST-001", tier="ho1", root=tmp_path)
    request = TurnRequest(
        session_id="SES-test",
        turn_number=1,
        query={},
        declared_inputs=[],
        declared_outputs=[]
    )
    runner.execute_turn(request, lambda r: TurnResult("ok", {}, {}))

    session_path = tmp_path / "planes" / "ho1" / "sessions" / "SES-test" / "ledger"
    assert (session_path / "exec.jsonl").exists()
    assert (session_path / "evidence.jsonl").exists()
```

#### TC-SB-006: Evidence Has Required Fields
```python
def test_evidence_has_required_fields(tmp_path):
    """Evidence entry MUST have session_id, turn_number, work_order_id."""
    runner = AgentRunner("PKG-TEST-001", tier="ho1", root=tmp_path)
    request = TurnRequest(
        session_id="SES-test",
        turn_number=1,
        query={},
        declared_inputs=[],
        declared_outputs=[],
        work_order_id="WO-123"
    )
    runner.execute_turn(request, lambda r: TurnResult("ok", {}, {}))

    evidence_path = tmp_path / "planes" / "ho1" / "sessions" / "SES-test" / "ledger" / "evidence.jsonl"
    with open(evidence_path) as f:
        entry = json.loads(f.readline())
    assert entry["session_id"] == "SES-test"
    assert entry["turn_number"] == 1
    assert entry["work_order_id"] == "WO-123"
```

#### TC-SB-007: Missing Declared Write Fails
```python
def test_missing_declared_write_fails(tmp_path):
    """Turn that doesn't write declared output MUST fail."""
    with Session(tier="ho1", root=tmp_path) as session:
        declared = [{"path": f"output/{session.session_id}/result.json", "role": "result"}]
        sandbox = TurnSandbox(session.session_id, declared_outputs=declared, root=tmp_path)
        with sandbox:
            pass  # Don't write the declared output
        realized, valid = sandbox.verify_writes()
        assert valid == False  # Missing declared write
```

## Verification Checklist

- [ ] All test cases pass
- [ ] Capability enforcement covers all operations
- [ ] Sandbox blocks all undeclared writes
- [ ] Both ledgers written per turn
- [ ] Evidence includes required linkage fields
- [ ] Session isolation verified
- [ ] Code coverage > 90%
