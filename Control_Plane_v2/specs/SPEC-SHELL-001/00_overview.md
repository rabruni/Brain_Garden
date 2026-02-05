# SPEC-SHELL-001: Universal Shell for Control Plane

## Summary

Port the Universal Shell from `_locked_system_flattened` to Control_Plane_v2 as a governed, installable module. The shell provides a rich terminal interface for interacting with the Control Plane, featuring vim-style commands, signal visualization, session management, and ledger integration.

## Scope

### In Scope
- Interactive REPL with prompt_toolkit
- Vim-style command dispatch (40+ commands)
- Agent hot-swapping at runtime
- Context window management (persistent/isolated)
- Signal visualization (stance, health, trust)
- Session logging to ledger
- Capability enforcement
- CP-specific commands (:pkg, :ledger, :gate)

### Out of Scope
- GUI interface
- Web-based shell
- Remote session management
- Multi-user sessions

## Success Criteria

1. Shell launches: `python3 scripts/shell.py`
2. Core commands work: `:h`, `:q`, `:s`, `:c`
3. CP commands work: `:pkg`, `:ledger`, `:gate`
4. Context modes work: `:ctx persistent`, `:ctx isolated`
5. Ledger logging works (commands in L-EXEC)
6. Capability enforcement blocks forbidden operations
7. All tests pass: `pytest tests/test_shell*.py -v`
8. All gates pass

## Frameworks

This module complies with:
- FMWK-SHELL-001: Shell/CLI Development Standard
- FMWK-100: Agent Development Standard
