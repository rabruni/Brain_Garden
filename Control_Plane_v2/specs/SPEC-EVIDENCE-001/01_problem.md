# Problem Statement

## Problem Description

Agents operating within the Control Plane governance model must produce cryptographic evidence of their actions to support the audit trail and enable replay verification. Currently, there is no standardized way to:

1. Compute deterministic hashes of agent inputs and outputs
2. Build evidence envelopes with consistent structure and required linkage fields
3. Reference artifacts in a way that ties them to sessions, turns, and work orders

Without a standardized evidence library, each agent would need to implement its own hashing and evidence generation, leading to inconsistencies, potential security gaps, and difficulty in verifying the audit trail.

The Control Plane's replay safety invariant (FMWK-100 Section 8.5) requires that any agent turn be reproducible from ledger entries. This requires consistent evidence generation across all modules.

## Impact

**Who is affected:**
- Agent developers must implement evidence generation for every module
- Auditors cannot reliably verify the integrity of agent actions
- The runtime cannot enforce the replay safety invariant without standardized evidence

**Severity:**
- High: Without standardized evidence, the fundamental auditability of the Control Plane is compromised
- Blocking: Higher-tier modules (T1 runtime, T3 agents) cannot be built without T0 evidence utilities

## Non-Goals

- This spec does NOT handle ledger writing (that's the runtime's responsibility)
- This spec does NOT implement capability enforcement
- This spec does NOT provide LLM integration
- This spec does NOT handle secret management

## Constraints

- Must be a pure Python library with no external dependencies beyond the standard library
- Must follow the pipe-first contract (FMWK-100 Section 7.4)
- Must produce deterministic output for identical input
- Must not perform any I/O except via stdin/stdout in CLI mode
