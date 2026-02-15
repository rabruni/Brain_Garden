# FMWK-008: Work Order Protocol — Cognitive Dispatch

## Purpose

Define the work order as the atomic unit of cognitive dispatch between HO2 (deliberative/supervisory) and HO1 (reactive/execution). A work order is a structured, bounded, one-shot instruction that HO2 creates and HO1 executes.

## Scope

- Governs all work orders dispatched within a cognitive stack (ADMIN or RESIDENT)
- Covers creation, validation, lifecycle, execution, and ledger recording
- Extends the existing `work_order.schema.json` with cognitive dispatch types
- Applies to both ADMIN's cognitive stack and future RESIDENT stacks

## Relationship to Existing Schema

The existing `HOT/schemas/work_order.schema.json` (from PKG-FRAMEWORK-WIRING-001) defines work orders for syntactic operations — code changes, spec deltas, registry changes. This framework adds **cognitive dispatch work orders**: the instructions that HO2 sends to HO1 during a user interaction.

Both schemas share common fields (`wo_id`, `session_id`, `budget`, `authorization`). Cognitive dispatch WOs add `tier_target`, `wo_type`, `input_context`, `output_result`, and `parent_wo_id`.

---

## 1. Work Order Identity

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `wo_id` | string | YES | Unique within session. Format: `WO-{session_id}-{seq:03d}` (e.g., `WO-SES-A1B2C3D4-001`) |
| `session_id` | string | YES | Session this WO belongs to. Format: `SES-{8 alphanum}` |
| `parent_wo_id` | string | NO | Parent WO if this is a sub-WO (chained dispatch) |
| `created_at` | string | YES | ISO8601 UTC timestamp |
| `created_by` | string | YES | Agent ID that created this WO (always an HO2 agent) |

### ID Generation

- `wo_id` is deterministic: session_id + monotonic sequence number
- Sequence resets per session, never per boot
- HO2 is the ONLY tier that creates work orders — HO1 receives and executes them

---

## 2. Work Order Types

| Type | Tier Target | Kitchener Step | Description | LLM Call? |
|------|-------------|----------------|-------------|-----------|
| `classify` | HO1 | Step 3: Execution (L1) | Classify user intent, input type, or content | YES |
| `tool_call` | HO1 | Step 3: Execution (L1) | Execute a registered tool (read file, query ledger, gate check) | NO |
| `synthesize` | HO1 | Step 3: Execution (L1) | Combine, format, or summarize prior WO results | YES |
| `execute` | HO1 | Step 3: Execution (L1) | General-purpose LLM call with full context | YES |

### Kitchener Step Mapping

All four WO types target HO1 and execute during **Step 3: Execution** of the canonical dispatch loop (v2 Section 1: Grounding Model: The Kitchener Orchestration Stack). The Kitchener steps that bracket WO execution are owned by HO2 and HO3:

| Kitchener Step | Tier | WO Relationship |
|----------------|------|-----------------|
| Step 1: Ideation (L3) | HO3 | Sets objective. Deferred — HO3 bookend not yet built. |
| Step 2: Scoping (L2) | HO2 | HO2 creates WOs with acceptance criteria. No WO type — this IS the WO creation act. |
| Step 3: Execution (L1) | HO1 | All four WO types execute here. HO1 loads prompt contract, calls LLM Gateway, returns result. |
| Step 4: Verification (L2) | HO2 | HO2 checks WO output against Step 2 criteria. Recorded as `WO_QUALITY_GATE`. |
| Step 5: Synthesis (L3) | HO3 | Final sign-off. Deferred — HO3 bookend not yet built. |

**Build approach**: Current implementation covers Steps 2-3-4 (the inner loop). Steps 1 and 5 are added when HO3 cognitive process is built (v2 Section 1: Grounding Model: The Kitchener Orchestration Stack).

### Type Rules

- `classify` — Input is raw user text or prior WO output. Output is a structured classification. Prompt contract required.
- `tool_call` — Input is tool name + arguments. Output is tool result. No LLM involved. Tool must be in the stack's registered tool set.
- `synthesize` — Input is one or more prior WO results. Output is a user-facing response. Prompt contract required.
- `execute` — Catch-all for LLM calls that don't fit the above. Prompt contract required. Use sparingly — prefer typed WOs.

---

## 3. Work Order Lifecycle

```
planned → dispatched → executing → completed
                                 → failed
```

| State | Set By | Kitchener Step | Controlling Tier | Meaning |
|-------|--------|----------------|------------------|---------|
| `planned` | HO2 | Step 2: Scoping (L2) | HO2 | WO created, validated, queued for dispatch |
| `dispatched` | HO2 | Step 2: Scoping (L2) | HO2 | WO sent to HO1 executor |
| `executing` | HO1 | Step 3: Execution (L1) | HO1 | HO1 has picked up the WO and is working |
| `completed` | HO1 | Step 3: Execution (L1) | HO1 | Execution finished successfully, result attached |
| `failed` | HO1/HO2 | Step 3/4 | HO1 or HO2 | Execution failed — error, timeout, or budget exhaustion |

**Tier ownership**: HO2 owns the `planned` and `dispatched` states (Step 2: Scoping). HO1 owns `executing` and `completed` (Step 3: Execution). The `failed` state can be set by either tier — HO1 during execution, or HO2 at planning-time validation. After all WOs complete, HO2 performs Step 4: Verification via the `WO_QUALITY_GATE` event (v2 Section 1: Grounding Model: The Kitchener Orchestration Stack).

### State Transition Rules

| From | To | Who | Kitchener Step | Condition |
|------|----|-----|----------------|-----------|
| `planned` | `dispatched` | HO2 | Step 2 → Step 3 boundary | WO passes validation |
| `dispatched` | `executing` | HO1 | Step 3: Execution | HO1 picks up the WO |
| `executing` | `completed` | HO1 | Step 3: Execution | Result produced, output validates against contract |
| `executing` | `failed` | HO1 | Step 3: Execution | Error, timeout, budget exceeded, or output validation failure |
| `planned` | `failed` | HO2 | Step 2: Scoping | Validation fails at planning time |

### Forbidden Transitions

- `completed` → any state (terminal)
- `failed` → any state (terminal)
- `executing` → `planned` (no regression)
- `dispatched` → `planned` (no regression)
- HO1 → `planned` or `dispatched` (HO1 cannot create or dispatch WOs)

---

## 4. Work Order Schema

```json
{
  "wo_id": "WO-SES-A1B2C3D4-001",
  "session_id": "SES-A1B2C3D4",
  "parent_wo_id": null,
  "wo_type": "classify",
  "tier_target": "HO1",
  "state": "planned",
  "created_at": "2026-02-12T22:00:00Z",
  "created_by": "ADMIN.ho2",

  "input_context": {
    "user_input": "show me all frameworks",
    "prior_results": [],
    "assembled_context": {}
  },

  "constraints": {
    "prompt_contract_id": "PC-C-001",
    "token_budget": 2000,
    "turn_limit": 3,
    "timeout_seconds": 30,
    "tools_allowed": []
  },

  "output_result": null,
  "error": null,
  "completed_at": null,

  "cost": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "llm_calls": 0,
    "tool_calls": 0,
    "elapsed_ms": 0
  }
}
```

### Field Descriptions

**Input fields** (set at creation by HO2):
- `input_context.user_input` — The raw user text or derived input for this WO
- `input_context.prior_results` — Results from earlier WOs in this chain (for synthesize)
- `input_context.assembled_context` — Context assembled by attention for this WO's tier
- `constraints.prompt_contract_id` — Contract ID from FMWK-011 (required for LLM-calling types)
- `constraints.token_budget` — Max tokens this WO may consume
- `constraints.turn_limit` — Max LLM round-trips (for multi-round tool use in HO1)
- `constraints.tools_allowed` — Tool IDs this WO may invoke (empty = no tools)

**Output fields** (set at completion by HO1):
- `output_result` — Structured result (dict). Schema defined by the prompt contract's output_schema.
- `error` — Error message if state is `failed`. Null otherwise.
- `completed_at` — ISO8601 timestamp when WO reached terminal state
- `cost` — Actual resource consumption (tokens, calls, time)

---

## 5. Ledger Recording

Every state transition produces a ledger entry. Two ledger files are involved:

### HO2 Ledger: `HO2/ledger/workorder.jsonl`

Records HO2's decisions — creation, dispatch, chain completion. HO2 events carry governance summaries; detailed traces live in HO1's ledger and are linked via `trace_hash` (see Section 5a).

| Event Type | When | Key Fields | Relational Metadata |
|------------|------|------------|---------------------|
| `WO_PLANNED` | HO2 creates WO | wo_id, wo_type, session_id, input_context summary | `relational.root_event_id`, `relational.related_artifacts` |
| `WO_DISPATCHED` | HO2 sends to HO1 | wo_id, tier_target | `relational.parent_event_id` (points to `WO_PLANNED` entry) |
| `WO_CHAIN_COMPLETE` | All WOs in a user turn are done | session_id, wo_count, total_cost, **`trace_hash`** | `relational.root_event_id`, `relational.related_artifacts` (all WOs in chain) |
| `WO_QUALITY_GATE` | HO2 approves or rejects final result | session_id, decision (pass/retry/escalate), **`trace_hash`** | `relational.parent_event_id` (points to `WO_CHAIN_COMPLETE`) |

### HO1 Ledger: `HO1/ledger/worker.jsonl`

Records HO1's execution — the canonical trace of all LLM calls and tool invocations. This is the detailed trace that HO2's `trace_hash` verifies (see Section 5a).

| Event Type | When | Key Fields | Relational Metadata |
|------------|------|------------|---------------------|
| `WO_EXECUTING` | HO1 picks up WO | wo_id, wo_type | `relational.parent_event_id` (points to HO2's `WO_DISPATCHED`), `relational.root_event_id` |
| `LLM_CALL` | HO1 makes an LLM call | wo_id, contract_id, input_tokens, output_tokens | `relational.parent_event_id` (points to `WO_EXECUTING`), `relational.related_artifacts` [{type: "framework", id: contract_id}] |
| `TOOL_CALL` | HO1 invokes a tool | wo_id, tool_id, args_summary, result_summary | `relational.parent_event_id` (points to `WO_EXECUTING`) |
| `WO_COMPLETED` | Execution succeeds | wo_id, output_result summary, cost | `relational.parent_event_id` (points to `WO_EXECUTING`), `relational.root_event_id` |
| `WO_FAILED` | Execution fails | wo_id, error, cost | `relational.parent_event_id` (points to `WO_EXECUTING`), `relational.root_event_id` |

### Ledger Invariants

- Every `WO_DISPATCHED` in HO2's ledger MUST have a corresponding `WO_EXECUTING` in HO1's ledger
- Every `WO_EXECUTING` MUST resolve to exactly one `WO_COMPLETED` or `WO_FAILED`
- `cost` fields MUST be populated on terminal events
- Ledger entries are append-only (FMWK-002 applies)
- Every HO2 terminal event (`WO_CHAIN_COMPLETE`, `WO_QUALITY_GATE`) MUST include a `trace_hash` field (see Section 5a)
- Every ledger entry MUST populate `relational.parent_event_id` when a causal parent exists (see Section 5b)
- Every ledger entry at chain boundaries MUST populate `relational.root_event_id` to enable causal chain traversal

---

## 5a. Hash-Anchored Trace Model

### Problem

The governance ledger (HO2m) must record verifiable summaries of what happened during WO execution. But storing full execution detail in HO2m causes ledger bloat — every LLM call, every tool invocation, every intermediate result would duplicate what HO1m already records. Without a linking mechanism, governance summaries become unverifiable claims (v2 Section 18: Critical Path — What's Next, open question: "Ledger efficiency / hash-anchored trace").

### Two-Tier Recording Model

| Tier | Ledger | What It Records | Purpose |
|------|--------|-----------------|---------|
| HO2 | `HO2/ledger/workorder.jsonl` | Governance summaries: WO planned, dispatched, chain complete, quality gate decision | Decision audit trail |
| HO1 | `HO1/ledger/worker.jsonl` | Detailed execution trace: every LLM call, tool call, token count, result | Execution evidence |

The `trace_hash` field links these two tiers. When HO2 writes a terminal governance event (`WO_CHAIN_COMPLETE` or `WO_QUALITY_GATE`), it includes a SHA256 hash of the corresponding HO1 trace entries. This hash is the integrity link — it proves that the governance summary corresponds to a specific, unmodified execution trace.

### trace_hash Computation

1. HO1 completes all WOs in a chain and writes trace entries to `HO1/ledger/worker.jsonl`
2. HO2 reads the HO1 trace entries for the completed chain (identified by `wo_id` and `session_id`)
3. HO2 computes `SHA256(concatenated HO1 trace entries for this chain, in ledger order)`
4. HO2 writes the hash as the `trace_hash` field on `WO_CHAIN_COMPLETE` and `WO_QUALITY_GATE` events

**Ordering**: The `trace_hash` is computed AFTER HO1 completes, so HO2 reads the written trace before computing the hash. This avoids coordination race conditions.

### trace_hash Field Location

The `trace_hash` value is stored in the ledger entry's `metadata.context_fingerprint.context_hash` field, as defined in `ledger_entry_metadata.schema.json` (PKG-PHASE2-SCHEMAS-001). This framework does NOT redefine the schema — it consumes the existing `context_fingerprint.context_hash` field for this purpose.

### Verification

Any auditor (ADMIN, KERNEL.semantic meta agent) can verify a governance summary by:

1. Reading the `trace_hash` from the HO2 governance event
2. Reading the corresponding HO1 trace entries (using `relational.root_event_id` to find the chain)
3. Recomputing the SHA256 hash
4. Comparing: match = verified, mismatch = integrity violation

### Implementation Boundary

This section defines the **protocol** — the two-tier model, the hash computation sequence, and the verification procedure. The **implementation** (hash computation code, trace entry serialization format, coordination mechanism) belongs to PKG-WORK-ORDER-001 (HANDOFF-13).

---

## 5b. Metadata Key Standard

### Purpose

Define how relational and graph metadata fields appear in all ledger entries produced by the work order protocol. These fields create a graph structure over the append-only ledger, enabling relationship-based retrieval (Graph RAG) without breaking immutability (v2 Section 6: Memory Architecture — "Meta ledger is graph-indexed").

### Schema Reference

All relational metadata fields are defined in `ledger_entry_metadata.schema.json` (PKG-PHASE2-SCHEMAS-001). This framework references that schema as-is. If extensions are needed, they are documented below as Schema Extension Proposals — the schema file is NOT modified by this framework.

### Required Relational Fields

Every ledger entry produced by the work order protocol MUST include the applicable relational metadata fields under the `metadata.relational` namespace:

| Field Path | Type | When Required | Description |
|------------|------|---------------|-------------|
| `metadata.relational.parent_event_id` | string (`LED-{8 hex}`) | When a causal parent exists | Points to the direct parent ledger entry. Example: `WO_DISPATCHED` points to its `WO_PLANNED` entry. |
| `metadata.relational.root_event_id` | string (`LED-{8 hex}`) | At chain boundaries and terminal events | Points to the root of the causal chain. Example: all events in a WO chain share the same root (the first `WO_PLANNED`). |
| `metadata.relational.related_artifacts` | array of `{type, id}` | When the event references governed artifacts | Lists artifacts this event touches. Types: `package`, `framework`, `spec`, `file`, `registry`, `ledger_entry`. |

### Provenance Fields

Every ledger entry produced by the work order protocol SHOULD include provenance metadata under the `metadata.provenance` namespace:

| Field Path | Type | When Required | Description |
|------------|------|---------------|-------------|
| `metadata.provenance.agent_id` | string | Always | The specific agent instance that created the entry |
| `metadata.provenance.agent_class` | string (enum) | Always | One of: `KERNEL.syntactic`, `KERNEL.semantic`, `ADMIN`, `RESIDENT` |
| `metadata.provenance.work_order_id` | string (`WO-*`) | When executing under a WO | The work order being executed |
| `metadata.provenance.session_id` | string (`SES-*`) | Always | The session this entry belongs to |
| `metadata.provenance.framework_id` | string (`FMWK-*`) | When applicable | The framework governing this action |

### Context Fingerprint Fields

For LLM-calling events (`LLM_CALL`), the following fields under `metadata.context_fingerprint` SHOULD be populated:

| Field Path | Type | Description |
|------------|------|-------------|
| `metadata.context_fingerprint.context_hash` | string | SHA256 of the assembled context sent to the LLM |
| `metadata.context_fingerprint.prompt_pack_id` | string (`PRM-*`) | The governed prompt pack used |
| `metadata.context_fingerprint.tokens_used.input` | integer | Input tokens consumed |
| `metadata.context_fingerprint.tokens_used.output` | integer | Output tokens consumed |
| `metadata.context_fingerprint.model_id` | string | LLM model identifier |

### Graph Traversal Patterns

The relational fields enable the following traversal patterns, used by HO2 operational learning and KERNEL.semantic meta agent (v2 Section 9: Learning Model — Three Timescales):

| Pattern | Query | Use Case |
|---------|-------|----------|
| Causal chain | Follow `parent_event_id` links upward | Trace a failure back to its root cause |
| Chain scope | All entries sharing `root_event_id` | Get all events in a WO chain |
| Artifact impact | All entries where `related_artifacts` contains artifact X | How many events touch a given spec/framework |
| Agent history | All entries matching `provenance.agent_id` | Audit trail for a specific agent |
| Framework failures | `provenance.framework_id` + `outcome.status = failure` | Which framework keeps failing (operational learning) |

### Downstream Frameworks

FMWK-009 (Tier Boundary), FMWK-010 (Cognitive Stack), and FMWK-011 (Prompt Contracts) adopt the metadata key standard defined in this section. Terminology and field paths defined here are authoritative for the batch.

---

## 6. Validation Rules

### At Planning Time (HO2)

1. `wo_type` MUST be one of: `classify`, `tool_call`, `synthesize`, `execute`
2. `session_id` MUST be non-empty and match the active session
3. `constraints.token_budget` MUST be > 0 and within the session's remaining budget
4. `constraints.prompt_contract_id` MUST be set for LLM-calling types (`classify`, `synthesize`, `execute`)
5. `constraints.tools_allowed` MUST be set and non-empty for `tool_call` type
6. If `parent_wo_id` is set, the parent WO MUST exist and be in `completed` state

### At Execution Time (HO1)

1. HO1 MUST NOT exceed `constraints.token_budget`
2. HO1 MUST NOT exceed `constraints.turn_limit` for multi-round tool use
3. HO1 MUST NOT invoke tools not listed in `constraints.tools_allowed`
4. HO1 MUST validate output against the prompt contract's output_schema (if defined)
5. If budget is exhausted before completion, HO1 MUST set state to `failed` with reason `budget_exhausted`

### At Quality Gate (HO2)

1. HO2 reviews the completed WO's `output_result`
2. HO2 may: accept (pass to user), retry (create new WO), or escalate (log governance event)
3. Quality decisions are recorded in `WO_QUALITY_GATE` ledger entries

---

## 7. Budget Model

Each cognitive stack has a **session budget** allocated at session start. Every WO deducts from this budget.

| Level | Budget Source | Enforced By |
|-------|-------------|-------------|
| Session | Configured per agent class (ADMIN, RESIDENT) | Session Host |
| Work Order | Allocated by HO2 from remaining session budget | HO2 Supervisor |
| LLM Call | Subset of WO budget consumed per call | HO1 Executor |

### Budget Exhaustion

- If a single WO exhausts its budget → WO fails with `budget_exhausted`
- If the session budget is insufficient for a new WO → HO2 returns a degraded response
- Budget is tracked in `cost` fields on every WO and rolled up at session level

---

## 8. Orchestration Patterns

HO2 composes work orders into chains. The dispatch pattern determines how WOs flow.

### Pipeline (v1 — implemented first)

Sequential WO chain. Each WO's output feeds the next WO's input.

```
WO-001 (classify) → result → WO-002 (tool_call) → result → WO-003 (synthesize) → final
```

### Parallel (future)

Multiple WOs dispatched concurrently. HO2 waits for all to complete before merging.

### Voting (future)

Multiple WOs answer the same question. HO2 picks the best result.

### Hierarchical (future)

A WO spawns sub-WOs via `parent_wo_id`. Recursive decomposition.

---

## 9. Error Handling

| Error | Who Detects | What Happens |
|-------|-------------|-------------|
| Invalid WO schema | HO2 at planning | WO set to `failed`, not dispatched |
| LLM call fails | HO1 executor | WO set to `failed`, error logged |
| Budget exhausted | HO1 executor | WO set to `failed`, partial cost logged |
| Timeout | HO1 executor | WO set to `failed`, elapsed_ms recorded |
| Output validation fails | HO1 executor | WO set to `failed`, validation errors logged |
| All WOs fail for a turn | HO2 supervisor | Degrade to direct LLM call (backwards compat) |

---

## 10. Implementation Mapping

| Component | Package | Installs To | What It Does |
|-----------|---------|-------------|-------------|
| `work_order.py` | PKG-WORK-ORDER-001 | `HOT/kernel/` | WorkOrder dataclass, state machine, validation |
| `wo_ledger.py` | PKG-WORK-ORDER-001 | `HOT/kernel/` | WO-specific ledger entry types |
| `wo_schema.json` | PKG-WORK-ORDER-001 | `HOT/config/` | JSON Schema for validation |
| `ho2_supervisor.py` | PKG-HO2-SUPERVISOR-001 | `HO2/kernel/` | Creates, dispatches, merges WOs |
| `ho1_executor.py` | PKG-HO1-EXECUTOR-001 | `HO1/kernel/` | Receives, executes, reports WOs |

---

## Conformance

- Reference implementation: `HOT/kernel/work_order.py` (PKG-WORK-ORDER-001)
- Governing specs: SPEC-WO-001 (work order validation), SPEC-LEDGER-001 (ledger integrity)
- Related frameworks: FMWK-002 (Ledger Protocol), FMWK-009 (Tier Boundary), FMWK-010 (Cognitive Stack), FMWK-011 (Prompt Contracts)
- Design authority: `_staging/architecture/KERNEL_PHASE_2_v2.md` (2026-02-14)

## Status

- Version: 1.1.0
- State: draft
- Owner: ray
- Created: 2026-02-12
- Updated: 2026-02-14
- Changes in 1.1.0: Kitchener step alignment (Sections 2, 3), hash-anchored trace model (Section 5a), metadata key standard (Section 5b), relational metadata in ledger events (Section 5)
