# SPEC-ADMIN-001: Admin Agent

## Summary

The Admin Agent (PKG-T3-ADMIN-001) is the first governed agent that operates inside the Control Plane's governance model. It provides human-friendly explanations of the Control Plane system by wrapping the kernel-native `trace.py` script and adding an LLM reasoning layer. The Admin Agent demonstrates that agents can be both artifacts OF the system and operators WITHIN it.

## Scope

### In Scope
- Explain any artifact (framework, spec, package, file)
- List installed packages with status
- Show system health via integrity checks
- Trace gate failures to root cause
- Describe governed roots and path classes
- Reconstruct recent context from ledgers
- Operate in read-only mode (no PRISTINE writes)
- Log all queries to L-EXEC

### Out of Scope
- Package installation or modification
- Work order creation or approval
- Cross-tier writes
- LLM API key management (uses env vars)
- Network capability gating (uses trace.py's local operations)

## Success Criteria

1. Admin Agent can explain any valid artifact ID
2. All queries logged to L-EXEC with session_id and turn_number
3. Evidence entries include required linkage fields
4. No writes to PRISTINE paths (verified by sandbox)
5. Agent successfully wraps trace.py for all operations
6. Human-readable output improves on raw trace.py JSON
7. All tests pass with > 90% coverage

## Frameworks

This module complies with:
- FMWK-100: Agent Development Standard (Section 7, Section 8)
- FMWK-000: Control Plane Governance Framework
