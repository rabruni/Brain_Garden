# Rollout Plan

## Approach

Direct install via pkgutil. The shell is a new module with no migration requirements.

## Installation Steps

```bash
# 1. Create framework (if not exists)
# Framework FMWK-SHELL-001 already created

# 2. Register spec
python3 scripts/pkgutil.py register-spec SPEC-SHELL-001 \
  --framework FMWK-SHELL-001

# 3. Module files are created in modules/shell/

# 4. Run preflight
python3 scripts/pkgutil.py preflight PKG-SHELL-001 \
  --src modules/shell

# 5. Run tests
pytest tests/test_shell.py tests/test_shell_commands.py -v

# 6. Verify gates
python3 scripts/gate_check.py --all

# 7. Test the shell
python3 scripts/shell.py --debug
```

## Rollback Plan

If issues arise:
1. Remove `modules/shell/` directory
2. Remove `scripts/shell.py`
3. Remove test files
4. Revert registry entries

```bash
rm -rf modules/shell/
rm scripts/shell.py
rm tests/test_shell*.py
# Revert CSV edits
```

## Verification

```bash
# Launch shell
python3 scripts/shell.py --debug

# Test commands
:h              # Should show help
:s              # Should show JSON state
:pkg            # Should list packages
:ledger         # Should show ledger entries
:gate           # Should show gate status
:q              # Should exit cleanly

# Verify ledger logging
cat planes/ho1/sessions/SES-*/ledger/exec.jsonl | jq .

# Run full test suite
pytest tests/test_shell*.py -v
```
