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

| Type | Tier Target | Description | LLM Call? |
|------|-------------|-------------|-----------|
| `classify` | HO1 | Classify user intent, input type, or content | YES |
| `tool_call` | HO1 | Execute a registered tool (read file, query ledger, gate check) | NO |
| `synthesize` | HO1 | Combine, format, or summarize prior WO results | YES |
| `execute` | HO1 | General-purpose LLM call with full context | YES |

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

| State | Set By | Meaning |
|-------|--------|---------|
| `planned` | HO2 | WO created, validated, queued for dispatch |
| `dispatched` | HO2 | WO sent to HO1 executor |
| `executing` | HO1 | HO1 has picked up the WO and is working |
| `completed` | HO1 | Execution finished successfully, result attached |
| `failed` | HO1 | Execution failed — error, timeout, or budget exhaustion |

### State Transition Rules

| From | To | Who | Condition |
|------|----|-----|-----------|
| `planned` | `dispatched` | HO2 | WO passes validation |
| `dispatched` | `executing` | HO1 | HO1 picks up the WO |
| `executing` | `completed` | HO1 | Result produced, output validates against contract |
| `executing` | `failed` | HO1 | Error, timeout, budget exceeded, or output validation failure |
| `planned` | `failed` | HO2 | Validation fails at planning time |

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

Records HO2's decisions — creation, dispatch, chain completion.

| Event Type | When | Key Fields |
|------------|------|------------|
| `WO_PLANNED` | HO2 creates WO | wo_id, wo_type, session_id, input_context summary |
| `WO_DISPATCHED` | HO2 sends to HO1 | wo_id, tier_target |
| `WO_CHAIN_COMPLETE` | All WOs in a user turn are done | session_id, wo_count, total_cost |
| `WO_QUALITY_GATE` | HO2 approves or rejects final result | session_id, decision (pass/retry/escalate) |

### HO1 Ledger: `HO1/ledger/worker.jsonl`

Records HO1's execution — the canonical trace of all LLM calls and tool invocations.

| Event Type | When | Key Fields |
|------------|------|------------|
| `WO_EXECUTING` | HO1 picks up WO | wo_id, wo_type |
| `LLM_CALL` | HO1 makes an LLM call | wo_id, contract_id, input_tokens, output_tokens |
| `TOOL_CALL` | HO1 invokes a tool | wo_id, tool_id, args_summary, result_summary |
| `WO_COMPLETED` | Execution succeeds | wo_id, output_result summary, cost |
| `WO_FAILED` | Execution fails | wo_id, error, cost |

### Ledger Invariants

- Every `WO_DISPATCHED` in HO2's ledger MUST have a corresponding `WO_EXECUTING` in HO1's ledger
- Every `WO_EXECUTING` MUST resolve to exactly one `WO_COMPLETED` or `WO_FAILED`
- `cost` fields MUST be populated on terminal events
- Ledger entries are append-only (FMWK-002 applies)

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
- Related frameworks: FMWK-002 (Ledger Protocol), FMWK-009 (Tier Boundary), FMWK-011 (Prompt Contracts)

## Status

- Version: 1.0.0
- State: draft
- Owner: ray
- Created: 2026-02-12
