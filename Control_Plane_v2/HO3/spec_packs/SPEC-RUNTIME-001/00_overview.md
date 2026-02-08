# SPEC-RUNTIME-001: Agent Runtime Module

## Summary

The Agent Runtime Module (PKG-T1-RUNTIME-001) provides the execution framework for agents operating within the Control Plane governance model. It handles capability enforcement, session management, sandbox isolation, ledger writing, and context assembly. This is a Tier 1 (T1) runtime module that agents depend upon for governed execution.

## Scope

### In Scope
- Agent package loading and capability extraction
- Session ID generation and management
- Turn execution in sandboxed environment
- Capability enforcement (read/write/execute permissions)
- Write surface validation (declared_outputs == realized_writes)
- L-EXEC and L-EVIDENCE ledger writing
- Prompt header construction with declared context
- Context reconstruction from ledgers with HO2 checkpoint acceleration

### Out of Scope
- LLM integration (handled by agents)
- Specific agent implementations
- Work order creation/approval
- Network capability gating (deferred to Phase 2)
- Cache management (Phase 2)

## Success Criteria

1. Turns execute within session-scoped sandbox (tmp/<session_id>/, output/<session_id>/)
2. Undeclared writes are detected and blocked (fail-closed)
3. Both L-EXEC and L-EVIDENCE entries written per turn
4. Evidence entries include session_id, turn_number, work_order_id
5. CapabilityViolation raised on forbidden operation attempts
6. Context reconstruction from ledgers works correctly
7. All tests pass with > 90% coverage

## Frameworks

This module complies with:
- FMWK-100: Agent Development Standard (Section 7, Section 8)
- FMWK-000: Control Plane Governance Framework
- FMWK-002: Ledger Protocol Standard
