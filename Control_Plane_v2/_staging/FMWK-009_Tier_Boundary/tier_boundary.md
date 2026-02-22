# FMWK-009: Tier Boundary

## Purpose

Define the governance rules that enforce isolation between the three cognitive tiers: HO1 (Workers), HO2 (Critic), and HO3/HOT (Strategist). Without this framework, tier isolation is aspirational -- any Python code can import any module. FMWK-009 makes "reading up = forbidden, calling through = allowed" a governed, enforceable rule.

This framework adds **tier** as a second dimension to the existing role-based access control defined in `authz.py` (PKG-KERNEL-001). Where `authz.py` checks *what action* a role can perform, FMWK-009 checks *which tier's resources* the caller may access. Both dimensions must be satisfied.

## Scope

- Governs all inter-tier interactions within the Control Plane
- Covers visibility (what each tier can read), syscalls (what each tier can invoke), import restrictions (what code each tier directory may reference), budget enforcement (how token budgets flow down the hierarchy), and tier-tagged ledger entries (how `scope.tier` is set)
- Applies to all agent classes: ADMIN, RESIDENT, and KERNEL (syntactic and semantic)
- References but does NOT modify existing code in PKG-KERNEL-001 or PKG-PHASE2-SCHEMAS-001

## Design Authority

Every rule in this framework traces to `_staging/architecture/KERNEL_PHASE_2_v2.md` (2026-02-14). Section references are given as "v2 Section N: Title" throughout.

---

## 1. Visibility Matrix

**Source**: v2 Section 5: The Visibility / Syscall Model

Lower tiers CANNOT read higher tier state. Lower tiers CAN call higher tier services (syscalls).

| Tier | Sees | Receives From Above | Calls (syscalls) |
|------|------|---------------------|------------------|
| **HO3** | All: HO3m + HO2m + HO1m + Meta ledger | -- | -- |
| **HO2** | HO2m + HO1m | Constraints from HO3 (pushed down) | HO3 services (e.g., policy lookup) |
| **HO1** | Only its work order context | Instructions from HO2 (dispatched) | HOT infrastructure: LLM Gateway, provider, ledger client |

### Enforcement Rules

1. **HO1 code MUST NOT import or read from `HO2/` or `HOT/` modules that expose tier state.** HO1 accesses HOT infrastructure exclusively through enumerated syscalls (Section 2). The syscall serves the request without exposing the internal state of the higher tier.
2. **HO2 code MUST NOT import or read from `HOT/` modules that expose HO3 governance state.** HO2 receives HO3 constraints as pushed-down parameters, not by reading HO3m directly.
3. **HO3 has full read visibility.** HO3 code may read HO3m, HO2m, HO1m, and the Meta Learning Ledger (v2 Section 6: Memory Architecture).
4. **"Receives From Above" is passive.** HO2 does not pull constraints from HO3 -- HO3 pushes them down. HO1 does not pull instructions from HO2 -- HO2 dispatches them as work orders (FMWK-008).

### Ledger Visibility

| Ledger | HO1 Access | HO2 Access | HO3 Access |
|--------|------------|------------|------------|
| **HO1m** (`HO1/ledger/worker.jsonl`) | Own work order entries only | Full read | Full read |
| **HO2m** (`HO2/ledger/workorder.jsonl`) | FORBIDDEN | Full read/write | Full read |
| **HO3m** (`HOT/ledger/governance.jsonl`) | FORBIDDEN | FORBIDDEN (receives pushed-down constraints) | Full read/write |
| **Meta Learning Ledger** (stored in HOT) | FORBIDDEN | FORBIDDEN | KERNEL.semantic (cross-cutting meta agent) |

---

## 2. Syscall Definitions

**Source**: v2 Section 5: The Visibility / Syscall Model; v2 Section 8: Infrastructure Components; v2 Section 10: Architectural Invariants (Invariant #1)

A **syscall** is an enumerated, logged service invocation that a lower tier makes on a higher tier's infrastructure. Syscalls are the ONLY mechanism by which a lower tier may interact with higher-tier resources. Every syscall is recorded in the calling tier's ledger.

### Enumerated Syscalls

| Syscall | Caller | Target | Service Location | Description |
|---------|--------|--------|------------------|-------------|
| `LLM_GATEWAY_CALL` | HO1 | HOT | `HOT/kernel/` (LLM Gateway) | Send a prompt to an LLM provider. Log, send, log, count tokens. No cognitive judgment. All LLM calls MUST flow through this syscall (v2 Section 10: Architectural Invariants, Invariant #1). |
| `LEDGER_WRITE` | HO1, HO2 | HOT | `HOT/kernel/` (Ledger Client) | Append an entry to the caller's tier ledger. The ledger client enforces append-only semantics and hash-chaining. |
| `LEDGER_READ` | HO1, HO2 | HOT | `HOT/kernel/` (Ledger Client) | Read entries from a ledger the caller is permitted to see (per Section 1 visibility matrix). The ledger client validates the caller's tier before returning results. |
| `SCHEMA_VALIDATE` | HO1, HO2 | HOT | `HOT/kernel/` (Schema Validator) | Validate a governed artifact against its JSON Schema. Used for prompt contract validation, work order validation, and ledger entry validation. |
| `BUDGET_CHECK` | HO1, HO2 | HOT | `HOT/kernel/` (Token Budgeter) | Check remaining token budget for a work order or session. Returns the available budget without modifying it. |
| `BUDGET_DEBIT` | HO1 | HOT | `HOT/kernel/` (Token Budgeter) | Debit token usage after an LLM call. Updates the budget tracker for the work order and session. |
| `POLICY_LOOKUP` | HO2 | HOT | `HOT/kernel/` or HO3 cognitive process | Look up a governance policy, principle, or constraint from HO3m. Used during HO2's priority probe (attention retrieval). Returns the policy content without exposing HO3m internals. |

### Syscall Rules

1. **Every syscall MUST be logged** in the calling tier's ledger as a ledger entry with the syscall name, target, and result.
2. **Syscall wrappers MUST validate caller tier** before executing (future runtime enforcement -- see Section 6).
3. **Syscall targets are KERNEL.syntactic services** that live in `HOT/kernel/`. They are deterministic infrastructure, not cognitive processes (v2 Section 4: Agent Classes).
4. **Syscalls MUST NOT expose higher-tier state** to the caller. The service processes the request and returns only the requested result.
5. **No undeclared syscalls.** Any new inter-tier service invocation must be added to this table and governed by FMWK-009.

### Syscall vs. Direct Import

| Mechanism | Allowed? | Example |
|-----------|----------|---------|
| Syscall through wrapper | YES | HO1 calls `llm_gateway.send(prompt)` which internally uses `HOT/kernel/llm_gateway.py` |
| Direct import of HOT module | CONDITIONAL | HO1 may import the syscall wrapper interface. HO1 MUST NOT import modules that expose tier state (e.g., HO3m contents, HO2 session state). |
| Direct read of higher-tier file | FORBIDDEN | HO1 opens and reads `HOT/ledger/governance.jsonl` directly |
| Direct import of HO2 module from HO1 | FORBIDDEN | `from HO2.kernel.ho2_supervisor import session_state` |

---

## 3. Import Restrictions

**Source**: v2 Section 5: The Visibility / Syscall Model; v2 Section 3: Three Things Per Tier

Code lives where it belongs. Directory structure enforces tier membership. The following tables define what each tier's code may import.

### HO1 (`HO1/`) -- Workers

| May Import | May NOT Import |
|------------|----------------|
| Python standard library | `HO2.*` (any HO2 module) |
| `HOT/kernel/` syscall interfaces (LLM Gateway, Ledger Client, Schema Validator, Token Budgeter) | `HOT/ledger/` (direct ledger file access) |
| Shared utility libraries installed to `HO1/` | `HOT/registries/` (governance registries) |
| Prompt contract loaders (own contracts only) | `HOT/config/` policy files (HO3 governance config) |
| | Any module that exposes HO2m or HO3m state |

### HO2 (`HO2/`) -- Critic

| May Import | May NOT Import |
|------------|----------------|
| Python standard library | `HOT/ledger/governance.jsonl` (direct HO3m read) |
| `HOT/kernel/` syscall interfaces (all enumerated syscalls) | `HOT/config/` policy files directly (use POLICY_LOOKUP syscall) |
| `HO1/` ledger entries via LEDGER_READ syscall | Any module that exposes HO3m mutable state |
| Shared utility libraries installed to `HO2/` | |
| Own HO2m ledger (`HO2/ledger/`) | |

### HOT (`HOT/`) -- Strategist / Infrastructure

| May Import | Restrictions |
|------------|-------------|
| Python standard library | No restrictions on downward reads (HO3 sees all) |
| All `HOT/kernel/` modules | KERNEL.syntactic code MUST NOT make cognitive judgments (v2 Section 4: Agent Classes) |
| `HO2/ledger/` entries (read) | |
| `HO1/ledger/` entries (read) | |
| Meta Learning Ledger entries | KERNEL.semantic only (cross-cutting meta agent) |

### Import Restriction Principle

The import restrictions implement a **one-way information flow**: HOT can read down. HO2 can read HO2m and HO1m. HO1 can read only its own work order context. Information flows upward ONLY through syscall return values and ledger writes -- never through direct import of higher-tier modules.

---

## 4. Budget Enforcement Chain

**Source**: v2 Section 10: Architectural Invariants (Invariant #5: "Budgets are enforced, not advisory"); v2 Section 8: Infrastructure Components (Token Budgeter); FMWK-008 Section 7: Budget Model

Token budgets flow top-down through the tier hierarchy. Each tier can only allocate from what it has been given.

### Budget Hierarchy

```
HO3 (Session Ceiling)
  |
  |  Sets total token budget for the session
  |  Configured per agent class (ADMIN, RESIDENT)
  |
  v
HO2 (Per-WO Allocation)
  |
  |  Allocates a subset of session budget to each work order
  |  Tracks remaining session budget after each allocation
  |  Cannot allocate more than the session ceiling
  |
  v
HO1 (Per-Call Debit)
  |
  |  Debits tokens consumed per LLM call via BUDGET_DEBIT syscall
  |  Cannot exceed the WO's token_budget constraint
  |  Reports actual cost in WO cost fields
```

### Enforcement Rules

| Rule | Tier | Enforcement Point | v2 Source |
|------|------|-------------------|-----------|
| Session budget is set before any WO is created | HO3 | Session Host / HO3 cognitive process (when built) | v2 Section 10: Invariant #5 |
| WO token_budget MUST be > 0 and within remaining session budget | HO2 | HO2 Supervisor at WO planning time | FMWK-008 Section 6 |
| HO1 MUST NOT exceed WO token_budget | HO1 | HO1 Executor checks before each LLM call | FMWK-008 Section 6 |
| Budget debit is logged via BUDGET_DEBIT syscall | HO1 | Token Budgeter in `HOT/kernel/` | v2 Section 8: Infrastructure |
| If WO budget exhausted, WO MUST fail with `budget_exhausted` | HO1 | HO1 Executor | FMWK-008 Section 9 |
| If session budget insufficient for new WO, HO2 returns degraded response | HO2 | HO2 Supervisor | FMWK-008 Section 7 |

### Budget Exhaustion Cascade

```
HO1 exhausts WO budget
  --> WO state = failed, reason = budget_exhausted
  --> HO2 receives failure
  --> HO2 checks remaining session budget
      --> If sufficient: HO2 may create a new WO with tighter constraints
      --> If insufficient: HO2 returns degraded response (direct LLM call via Gateway)
  --> Degradation event logged to HO1m (v2 Section 1: Degradation Behavior)
```

### Who Enforces What

| Enforcer | What It Enforces | Where It Lives |
|----------|-----------------|----------------|
| Token Budgeter | Token accounting (check, debit, report) | `HOT/kernel/` (KERNEL.syntactic) |
| HO2 Supervisor | WO budget allocation from session ceiling | `HO2/kernel/` |
| HO1 Executor | Per-call budget compliance | `HO1/kernel/` |
| Session Host | Session ceiling initialization | Top-level session management |

---

## 5. Tier-Tagged Ledger Entries

**Source**: v2 Section 6: Memory Architecture; FMWK-008 Section 5b: Metadata Key Standard

Every ledger entry produced within the Control Plane MUST include a `scope.tier` field indicating which cognitive tier originated the entry. This enables tier-scoped queries, visibility enforcement, and learning loop traversal.

### The `scope.tier` Field

**Schema reference**: `ledger_entry_metadata.schema.json` (PKG-PHASE2-SCHEMAS-001) defines `scope.tier` as:

```json
"scope": {
  "type": "object",
  "properties": {
    "tier": {
      "type": "string",
      "enum": ["hot", "ho2", "ho1"]
    }
  }
}
```

This framework consumes this field as-is. The schema is NOT modified.

### Tier Assignment Rules

| Originating Tier | `scope.tier` Value | Examples |
|------------------|--------------------|----------|
| HO1 (Workers) | `"ho1"` | `WO_EXECUTING`, `LLM_CALL`, `TOOL_CALL`, `WO_COMPLETED`, `WO_FAILED` |
| HO2 (Critic) | `"ho2"` | `WO_PLANNED`, `WO_DISPATCHED`, `WO_CHAIN_COMPLETE`, `WO_QUALITY_GATE` |
| HOT/HO3 (Strategist / Infrastructure) | `"hot"` | Governance decisions, policy updates, gate operations, integrity checks, package events |

### Setting Convention

1. **The cognitive process that creates the ledger entry sets `scope.tier`.** HO1 cognitive process sets `"ho1"`. HO2 cognitive process sets `"ho2"`. HOT infrastructure and HO3 cognitive process set `"hot"`.
2. **Syscall-originated entries**: When HO1 writes to its ledger via the `LEDGER_WRITE` syscall, the entry gets `scope.tier = "ho1"` -- the originating tier, not the target tier where the ledger client code lives.
3. **KERNEL.syntactic entries**: Infrastructure events (gate checks, integrity verification, package operations) produced by KERNEL.syntactic services in `HOT/kernel/` get `scope.tier = "hot"`.

### Relationship to FMWK-008A Metadata Key Standard

FMWK-008 Section 5b defines the metadata key standard for relational fields (`metadata.relational.*`) and provenance fields (`metadata.provenance.*`). FMWK-009 adds the requirement that `metadata.scope.tier` is populated on every entry.

The combination of `scope.tier` and `relational.*` fields enables tier-scoped graph traversal:

| Query Pattern | Fields Used | Use Case |
|---------------|-------------|----------|
| All HO1 events in a WO | `scope.tier = "ho1"` + `provenance.work_order_id` | HO2 operational learning (v2 Section 9) |
| All HO2 governance events for a session | `scope.tier = "ho2"` + `provenance.session_id` | ADMIN audit trail |
| Causal chain across tiers | `relational.parent_event_id` chain | Trace a failure from HO1 through HO2 to HO3 policy |
| Tier-scoped artifact impact | `scope.tier` + `relational.related_artifacts` | Which tier's events touch a given framework |

---

## 6. Enforcement Mechanism

**Source**: v2 Section 5: The Visibility / Syscall Model; v2 Section 3: Three Things Per Tier

Python has no module-level import blocking. A file in `HO1/` can `import` anything from `HOT/` or `HO2/` -- the language does not prevent it. Enforcement must therefore be layered: convention, static analysis, and future runtime validation.

### Layer 1: Path Convention (Active)

Code lives where it belongs. Directory structure enforces tier membership.

| Directory | Tier | Meaning |
|-----------|------|---------|
| `HO1/` | HO1 (Workers) | All HO1 cognitive process code, HO1 ledger, HO1 installed packages |
| `HO2/` | HO2 (Critic) | All HO2 cognitive process code, HO2 ledger, HO2 installed packages |
| `HOT/` | HO3 (Strategist) / Infrastructure | All HO3 governance, KERNEL.syntactic services, KERNEL.semantic agents, HO3 ledger, schemas, registries |

**Rule**: A file's tier is determined by its directory path. There is no ambiguity. Code in `HO1/kernel/ho1_executor.py` belongs to HO1. Code in `HOT/kernel/llm_gateway.py` belongs to HOT. The filesystem IS the tier boundary (v2 Section 3: Three Things Per Tier -- Layout/Directory concept).

**Layout reference**: `HOT/config/layout.json` (PKG-LAYOUT-002) defines the canonical directory structure:

```json
{
  "tiers": { "HOT": "HOT", "HO2": "HO2", "HO1": "HO1" },
  "hot_dirs": { "kernel": "HOT/kernel", "config": "HOT/config", ... },
  "tier_dirs": { "registries": "registries", "installed": "installed", "ledger": "ledger", ... }
}
```

### Layer 2: Gate Check (Active)

`gate_check.py` verifies import statements in staged packages at install time. A package submitted for installation is scanned for upward-crossing imports before it enters the governed tree.

| Check | What It Catches | Example Violation |
|-------|----------------|-------------------|
| HO1 importing HO2 | `from HO2.kernel import ...` in an `HO1/` file | HO1 executor reading HO2 session state |
| HO1 importing HOT state | `from HOT.ledger import ...` in an `HO1/` file | HO1 directly reading governance ledger |
| HO2 importing HOT state | `from HOT.config import policies` in an `HO2/` file | HO2 reading HO3 policy files directly instead of using POLICY_LOOKUP |

**Gate check does NOT block**:
- HO1 importing `HOT/kernel/` syscall interfaces (these are the allowed crossing mechanism)
- HO2 importing `HOT/kernel/` syscall interfaces
- HOT importing from any tier (HO3 has full read visibility)

**Implementation note**: The gate check performs static analysis of `import` and `from ... import` statements. It uses pattern matching on the import path, not AST-based analysis. This matches the system's current maturity level.

### Layer 3: Runtime Assertion (Future)

When the runtime cognitive processes exist (PKG-HO1-EXECUTOR-001 from HANDOFF-14, PKG-HO2-SUPERVISOR-001 from HANDOFF-15), syscall wrappers will validate the caller's tier identity before executing.

```
Caller tier → Syscall wrapper → Tier validation → Service execution
                                     |
                                     v
                              If caller tier not authorized:
                              raise TierViolationError
```

**Deferred until**: HANDOFF-14 (HO1 Executor) and HANDOFF-15 (HO2 Supervisor) build the runtime cognitive processes. Runtime tier validation is added as a wrapper around each syscall entry point.

### Enforcement Summary

| Layer | Status | What It Catches | When |
|-------|--------|-----------------|------|
| Path convention | **Active** | Misplaced code (file in wrong tier directory) | Package authoring time |
| Gate check | **Active** | Upward-crossing imports in staged packages | Package install time |
| Runtime assertion | **Future** | Unauthorized syscall invocations at runtime | Request execution time |

---

## 7. Capability Ceilings

**Source**: v2 Section 4: Agent Classes; v2 Section 12: Design Principles From CS Kernel Theory

Agent classes have fixed capability ceilings. Capabilities are claims-based -- an agent class can only exercise the capabilities assigned to it, regardless of which tier it operates in.

### ADMIN Capabilities

| Capability | Scope | Tier Interaction |
|------------|-------|------------------|
| **CAP_READ_ALL** | Read any tier's ledger, registry, manifest, governed file | ADMIN's HO2 cognitive process may read HO1m, HO2m, HO3m, and Meta ledger |
| **CAP_AUDIT_WRITE** | Write observations, recommendations to HO2m/HO3m | ADMIN writes audit annotations through governed work orders |
| **L-OBSERVE** | Ledger query across all tiers | Uses LEDGER_READ syscall with elevated visibility |
| **L-ANNOTATE** | Add audit annotations to ledger entries | Uses LEDGER_WRITE syscall to append annotation entries |

**ADMIN cannot** (v2 Section 4):
- Modify kernel code
- Modify BUILDER artifacts
- Self-promote permissions
- Interact with RESIDENT agents or their sub-sessions directly
- All writes go through governed work orders (v2 Section 10: Invariant #2)

### RESIDENT Capabilities

| Capability | Scope | Tier Interaction |
|------------|-------|------------------|
| **Own namespace only** | Read/write within own cognitive stack's ledgers and installed packages | RESIDENT's HO2 reads own HO2m + HO1m. RESIDENT's HO1 sees only its WO context. |
| **No cross-stack access** | Cannot read other agent classes' ledgers or state | Enforced by separate cognitive stacks (v2 Section 11: Cognitive Stacks) |

### KERNEL.syntactic Capabilities

| Capability | Scope | Tier Interaction |
|------------|-------|------------------|
| **Infrastructure services** | Provide deterministic services to all tiers via syscalls | Lives in `HOT/kernel/`. Serves requests from any tier without exposing state. |
| **No cognitive judgment** | Binary outcomes only (pass/fail, valid/invalid) | Not an agent -- code that enforces invariants (v2 Section 4) |

### KERNEL.semantic Capabilities

| Capability | Scope | Tier Interaction |
|------------|-------|------------------|
| **Cross-cutting read** | Read all tier ledgers for pattern detection | Cross-cutting meta agent reads HO1m, HO2m, HO3m, Meta ledger |
| **Meta ledger write** | Write graph-indexed patterns to Meta Learning Ledger | Stored in HOT, cross-cutting (v2 Section 6) |

### Capability + Tier = Access Decision

Access is authorized when BOTH dimensions pass:

```
Access granted = role_check(identity, action) AND tier_check(caller_tier, target_tier, syscall)
```

Where:
- `role_check` is the existing `authz.py` from PKG-KERNEL-001 (checks role -> action mapping)
- `tier_check` is the FMWK-009 addition (checks caller tier against visibility matrix and syscall table)

---

## 8. Cross-Tier Communication Patterns

**Source**: v2 Section 5: The Visibility / Syscall Model; v2 Section 12: Design Principles From CS Kernel Theory (IPC)

All inter-tier communication follows one of three patterns. No other communication mechanism is permitted.

### Pattern 1: Syscall (Lower to Higher)

A lower tier invokes a higher tier's infrastructure service through an enumerated syscall.

```
HO1 ---[LLM_GATEWAY_CALL]--> HOT/kernel/llm_gateway
HO1 ---[LEDGER_WRITE]------> HOT/kernel/ledger_client
HO2 ---[POLICY_LOOKUP]-----> HOT/kernel/ or HO3 cognitive process
```

**Rules**:
- Caller MUST use the syscall interface, not direct import
- Callee MUST NOT expose internal state
- Every syscall MUST be logged
- Only syscalls enumerated in Section 2 are permitted

### Pattern 2: Pushed-Down Constraints (Higher to Lower)

A higher tier sends constraints, instructions, or parameters to a lower tier. The lower tier receives these passively -- it does not request them.

```
HO3 ---[push constraints]---> HO2 (session ceiling, policy constraints)
HO2 ---[dispatch WO]--------> HO1 (work order with budget, contract, context)
```

**Rules**:
- Constraints flow downward only
- The receiving tier accepts what it is given -- it does not negotiate
- Work orders are the contractual form of pushed-down instructions (FMWK-008)
- HO2 does not query HO3m directly -- it receives HO3 constraints via the POLICY_LOOKUP syscall or as parameters set at session initialization

### Pattern 3: Result Return (Lower to Higher)

A lower tier returns results to the tier that dispatched work to it. This is the natural return path of a syscall or work order.

```
HO1 ---[WO result]----------> HO2 (output_result, cost, completion status)
HOT ---[syscall response]---> HO1 or HO2 (LLM response, validation result, budget status)
```

**Rules**:
- Results flow upward as return values, not as tier state reads
- HO2 reads HO1's result from the completed work order, not by importing HO1 modules
- All results are recorded in the originating tier's ledger

### Forbidden Patterns

| Pattern | Why Forbidden | v2 Source |
|---------|---------------|-----------|
| HO1 reading HO2m directly | Reading up is forbidden | v2 Section 5 |
| HO1 reading HO3m/governance directly | Reading up is forbidden | v2 Section 5 |
| HO2 reading HO3m directly | HO2 receives constraints via push-down or POLICY_LOOKUP | v2 Section 5 |
| HO1 dispatching a work order | Only HO2 creates WOs (v2 Section 10: Invariant #2) | FMWK-008 Section 1 |
| Direct LLM call bypassing Gateway | All LLM calls flow through LLM Gateway | v2 Section 10: Invariant #1 |
| Undeclared inter-tier import | All crossings must be enumerated syscalls | This framework, Section 2 |

---

## 9. Implementation Mapping

**Source**: v2 Section 8: Infrastructure Components; v2 Section 18: Critical Path

This section maps FMWK-009's rules to the packages that enforce them.

### Active Packages (enforce today)

| Package | What It Enforces | FMWK-009 Section |
|---------|-----------------|------------------|
| **PKG-KERNEL-001** | Role-based access via `authz.py`. Defines roles: admin, maintainer, auditor, reader. FMWK-009 adds tier as second dimension. | Section 7 |
| **PKG-LAYOUT-002** | Tier directory structure via `layout.json`. Defines `HOT/`, `HO2/`, `HO1/` as canonical tier paths. | Section 6, Layer 1 |
| **PKG-PHASE2-SCHEMAS-001** | `scope.tier` field in `ledger_entry_metadata.schema.json`. Enum: `hot`, `ho2`, `ho1`. | Section 5 |
| **PKG-TOKEN-BUDGETER-001** | Token budget tracking per work order. Provides BUDGET_CHECK and BUDGET_DEBIT syscall implementations. | Section 4 |

### Future Packages (enforce at runtime)

| Package | What It Will Enforce | FMWK-009 Section | Handoff |
|---------|---------------------|------------------|---------|
| **PKG-WORK-ORDER-001** | WO schema validation, lifecycle state machine, tier-tagged ledger writes | Sections 2, 4, 5 | HANDOFF-13 |
| **PKG-HO1-EXECUTOR-001** | HO1 syscall compliance, budget debit, import restrictions at runtime | Sections 2, 3, 4, 6 (Layer 3) | HANDOFF-14 |
| **PKG-HO2-SUPERVISOR-001** | HO2 WO creation, budget allocation, visibility enforcement | Sections 1, 2, 4, 8 | HANDOFF-15 |
| **PKG-GATE-CHECK-EXT** (or update to existing gate check) | Static import analysis at package install time | Section 6, Layer 2 | TBD |

### Syscall Implementation Mapping

| Syscall | Implementing Module | Package |
|---------|-------------------|---------|
| `LLM_GATEWAY_CALL` | `HOT/kernel/llm_gateway.py` | PKG-PROMPT-ROUTER-001 (existing, renamed) |
| `LEDGER_WRITE` | `HOT/kernel/ledger_client.py` | PKG-KERNEL-001 |
| `LEDGER_READ` | `HOT/kernel/ledger_client.py` | PKG-KERNEL-001 |
| `SCHEMA_VALIDATE` | `HOT/kernel/schema_validator.py` | PKG-PHASE2-SCHEMAS-001 or future |
| `BUDGET_CHECK` | `HOT/kernel/token_budgeter.py` | PKG-TOKEN-BUDGETER-001 |
| `BUDGET_DEBIT` | `HOT/kernel/token_budgeter.py` | PKG-TOKEN-BUDGETER-001 |
| `POLICY_LOOKUP` | `HOT/kernel/` (TBD) | Future -- HO3 cognitive process |

---

## 10. Future Extensions

### 10.1 Custom Import Hook

A Python import hook (`sys.meta_path` finder) that intercepts `import` statements at runtime and rejects upward-crossing imports. This would make Layer 3 enforcement automatic rather than wrapper-based.

**Why deferred**: Over-engineering for the current codebase maturity. The gate check at install time catches most violations. A custom import hook adds runtime overhead and debugging complexity.

**When to add**: When the cognitive processes (HANDOFF-14, HANDOFF-15) are running in production and import violations become a real risk (not just a theoretical one).

### 10.2 Runtime Caller Validation

Syscall wrappers that inspect the call stack or accept a caller identity token to validate that the invoking code belongs to an authorized tier.

**Why deferred**: Requires the runtime cognitive processes to exist. Cannot validate caller tier identity without a running HO1 Executor and HO2 Supervisor.

**When to add**: HANDOFF-14 (HO1 Executor) and HANDOFF-15 (HO2 Supervisor) should include caller tier identity as a parameter on every syscall invocation.

### 10.3 Tier-Scoped Audit Reports

ADMIN capability to generate tier-scoped audit reports: "Show me all HO1 events that crossed tier boundaries" or "Which HO2 events referenced HO3 policies." Uses `scope.tier` + `relational.*` metadata fields for filtering.

**When to add**: After ADMIN's cognitive stack is operational and PKG-WORK-ORDER-001 produces real tier-tagged ledger entries.

### 10.4 Dynamic Tier Promotion/Demotion

A mechanism for temporarily elevating a tier's visibility (e.g., ADMIN granting HO2 temporary read access to HO3m for a specific session). Requires an explicit promotion event, time-bounded scope, and full audit trail.

**Why deferred**: No use case exists today. The static visibility matrix is sufficient for current agent classes. Adding dynamic promotion introduces complexity and potential security gaps.

---

## Conformance

- **Design authority**: `_staging/architecture/KERNEL_PHASE_2_v2.md` (2026-02-14)
- **Existing code referenced** (not modified):
  - `PKG-KERNEL-001/HOT/kernel/authz.py` -- role-based access (4 roles: admin, maintainer, auditor, reader)
  - `PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` -- `scope.tier` enum: `hot`, `ho2`, `ho1`
  - `PKG-LAYOUT-002/HOT/config/layout.json` -- tier directory structure
- **Metadata key standard**: Adopts FMWK-008 Section 5b for all relational and provenance metadata fields
- **Related frameworks**:
  - FMWK-008 (Work Order Protocol) -- WO schema, lifecycle, budget model, metadata key standard
  - FMWK-010 (Cognitive Stack) -- shared code / isolated state rules consume FMWK-009 tier boundaries
  - FMWK-011 (Prompt Contracts) -- prompt contracts cross tier boundaries via LLM_GATEWAY_CALL syscall
- **Governing specs** (expected): SPEC-TIER-001 (tier boundary validation)

## Status

- Version: 1.0.0
- State: draft
- Owner: ray
- Created: 2026-02-14
- Updated: 2026-02-14
