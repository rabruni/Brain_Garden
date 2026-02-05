# Testing

## Test Command

```bash
$ pytest tests/test_shell.py tests/test_shell_commands.py -v
```

## Test Cases

### Shell Lifecycle Tests (test_shell.py)

| Test | Description |
|------|-------------|
| `test_shell_init` | Shell initializes with session |
| `test_shell_session_created` | Session directory exists after init |
| `test_shell_quit` | :q exits cleanly |
| `test_shell_quit_writes_ledger` | Session end event in ledger |
| `test_shell_keyboard_interrupt` | Ctrl+C handled gracefully |

### Command Tests (test_shell_commands.py)

| Test | Description |
|------|-------------|
| `test_cmd_help` | :h shows help text |
| `test_cmd_state` | :s shows JSON state |
| `test_cmd_clear` | :c clears screen (mock) |
| `test_cmd_agent` | :a shows agent info |
| `test_cmd_unknown` | Unknown command shows error |

### CP Command Tests

| Test | Description |
|------|-------------|
| `test_pkg_list` | :pkg lists packages |
| `test_pkg_info` | :pkg PKG-XXX shows details |
| `test_ledger_show` | :ledger shows entries |
| `test_ledger_filter` | :ledger governance filters |
| `test_gate_status` | :gate shows status |
| `test_compliance` | :compliance shows info |

### Context Mode Tests

| Test | Description |
|------|-------------|
| `test_ctx_show` | :ctx shows current mode |
| `test_ctx_persistent` | :ctx persistent switches mode |
| `test_ctx_isolated` | :ctx isolated clears context |

### Ledger Tests

| Test | Description |
|------|-------------|
| `test_command_logged` | Commands logged to L-EXEC |
| `test_command_hash` | Command hash in entry |
| `test_evidence_reads` | Declared reads in evidence |

### Capability Tests

| Test | Description |
|------|-------------|
| `test_capability_allowed` | Allowed ops succeed |
| `test_capability_forbidden` | Forbidden ops blocked |
| `test_capability_violation_logged` | Violations logged |

## Verification Checklist

- [ ] Shell launches without error
- [ ] All core commands respond
- [ ] CP commands return valid data
- [ ] Context modes switch correctly
- [ ] Signal strip displays
- [ ] Ledger entries created
- [ ] Capability violations blocked
- [ ] Tests pass with exit code 0
