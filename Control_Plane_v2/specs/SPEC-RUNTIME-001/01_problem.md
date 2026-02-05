# Problem Statement

## Problem Description

Agents operating within the Control Plane need a consistent execution framework that enforces governance rules. Without a shared runtime:

1. **Capability enforcement is inconsistent**: Each agent would implement its own permission checking, leading to security gaps and divergent behavior.

2. **Audit trail is incomplete**: Without standardized ledger writing, there's no guarantee that agent actions are properly recorded for replay and verification.

3. **Session isolation is missing**: Agents could write anywhere in the filesystem, contaminating each other's state and breaking replay safety.

4. **Context reconstruction varies**: Each agent would implement its own ledger traversal logic, leading to inconsistent views of system state.

The Control Plane's governance model (FMWK-000) requires that all agent actions be:
- Capability-gated (agents can only do what they're declared to do)
- Auditable (all actions logged to L-EXEC and L-EVIDENCE)
- Isolated (writes contained to session-scoped paths)
- Replayable (execution can be reproduced from ledger entries)

A shared runtime module ensures these invariants are enforced consistently across all agents.

## Impact

**Who is affected:**
- Agent developers need a reliable execution framework
- Auditors need consistent ledger entries to verify agent behavior
- The governance system cannot enforce its invariants without runtime support
- Higher-tier agents (T3) cannot be built without T1 runtime

**Severity:**
- Critical: Without a runtime, agents cannot be safely deployed
- Blocking: T3 agent packages (like Admin Agent) depend on this

## Non-Goals

- This spec does NOT implement specific agents
- This spec does NOT handle LLM API calls (agents do that)
- This spec does NOT manage work order approval workflows
- This spec does NOT implement cross-tier writes
- This spec does NOT provide network capability gating (Phase 2)

## Constraints

- Must integrate with existing ledger_client.py
- Must follow tier semantics: HO3=law, HO2=authorization, HO1=execution
- Must support session paths: planes/<tier>/sessions/<sid>/ledger/
- Must enforce fail-closed write surface validation
