# Builder Handoff #5: Flow Runner (Agent Orchestrator)

## Mission

Build the flow runner — the component that reads a work order, instantiates an agent from a framework definition, wires attention → router, and manages the execution lifecycle. This is the last kernel component needed before the first governed agent can run.

**v1 scope (Stage 2): single-step execution only.** One work order → one prompt → one response → done. Multi-step orchestration, aperture model, and HO2→HO1 delegation are v2 extension points — design the interfaces now but don't implement the multi-step logic.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. No exceptions.
3. **Package everything.** New code ships as packages with manifest.json, SHA256 hashes, proper dependencies.
4. **End-to-end verification.** Full install chain must pass all gates.
5. **No hardcoding.** Every timeout, retry count, budget default — config-driven.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      CALLER                                  │
│         (human, DoPeJar, ADMIN, or parent flow)              │
│                                                              │
│  Input: Work Order (validated against work_order.schema.json)│
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                     FLOW RUNNER                              │
│                 (KERNEL.semantic)                             │
│                                                              │
│  1. Validate work order                                      │
│  2. Resolve framework → determine agent class + tier         │
│  3. Allocate budget (→ Token Budgeter)                       │
│  4. Create execution context                                 │
│  5. Assemble context (→ Attention Service)                   │
│  6. Send prompt (→ Prompt Router)                            │
│  7. Validate result against acceptance criteria              │
│  8. Log outcome (→ Ledger)                                   │
│  9. Return result                                            │
│                                                              │
│  v2 extensions: aperture model, multi-step, HO2→HO1 deleg.  │
└──────┬──────────┬──────────┬──────────┬─────────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
   Attention   Prompt     Token      Ledger
   Service     Router     Budgeter   (write)
```

**Key identity:** The flow runner IS kernel infrastructure (KERNEL.semantic). It is NOT an agent. It's the machinery that brings agents to life by reading framework definitions and executing work orders.

**What an "agent" is in this system:** An agent is not a persistent process. It's an execution context: `(agent_class, framework_id, tier, work_order, prompt_contracts)`. The flow runner creates this context, runs it, and discards it. Agents don't remember — they READ (from ledger/registries via attention).

---

## The v1 Flow (Single-Step)

### Inputs

```python
@dataclass
class FlowRequest:
    work_order: dict            # Validated WO (work_order.schema.json)
    caller_id: str              # Who submitted this (human, agent_id, or "system")
    dev_mode: bool = False      # Bypass auth, use mock provider
```

### Outputs

```python
@dataclass
class FlowResult:
    status: str                 # "success", "failure", "rejected", "timeout", "budget_exhausted"
    work_order_id: str          # WO that was executed
    agent_id: str               # Generated agent instance ID
    response: str | None        # LLM response text (None if rejected/failed before send)
    tokens_used: dict | None    # {input: N, output: M}
    validation_result: dict | None  # Acceptance criteria results
    ledger_entry_ids: list[str] # All ledger entries created during execution
    error: str | None           # Error message if failed
    duration_ms: int            # Wall-clock execution time
```

### Step-by-Step

#### Step 1: Validate Work Order

- Validate WO against `work_order.schema.json` (structural validation — KERNEL.syntactic)
- Check required fields: work_order_id, type, plane_id, spec_id, framework_id, scope, acceptance
- If `authorization` is present, validate authorization chain
- If `budget` is present, validate budget fields
- **FAIL-CLOSED**: invalid WO → reject immediately

#### Step 2: Resolve Framework

Read the framework manifest for the WO's `framework_id`:
1. Look up in `frameworks_registry.csv` — find framework dir
2. Read `manifest.yaml` from the framework dir
3. Extract: agent classes permitted, path authorizations, invariants, required gates
4. Determine `agent_class` from WO (if specified) or from framework defaults
5. Determine `tier` from WO's `plane_id`
6. Generate `agent_id`: `AGT-{framework_id}-{wo_id}-{timestamp}`

**FAIL-CLOSED**: framework not found, or agent_class not permitted by framework → reject

#### Step 3: Allocate Budget

Call Token Budgeter to allocate budget for this WO:
1. If WO has `budget` field, use those limits
2. If no explicit budget, use framework defaults (config-driven)
3. Budgeter returns allocation confirmation or rejection
4. Budget scope: `{session_id, work_order_id, agent_id}`

**FAIL-CLOSED**: budget allocation denied (session over-committed) → reject

#### Step 4: Create Execution Context

Build the execution context — the "agent instance":

```python
@dataclass
class ExecutionContext:
    agent_id: str
    agent_class: str            # KERNEL.syntactic | KERNEL.semantic | ADMIN | RESIDENT
    framework_id: str
    tier: str                   # hot | ho2 | ho1
    work_order: dict
    prompt_contracts: list[dict]  # Prompt contracts available to this agent
    budget_scope: dict          # Budget allocation from step 3
    path_authorizations: list[str]  # What files this agent can touch
    tool_permissions: list[dict]    # What tools this agent can invoke
    session_id: str
    created_at: str             # ISO timestamp
```

- Resolve prompt contracts: look up contracts bound to this framework/agent_class
- Set path authorizations from framework manifest
- Set tool permissions from WO's `tool_permissions` (if present)
- Log `WO_STARTED` to ledger (via LedgerFactory pattern)

📝 Ledger write: WO_STARTED with full execution context as metadata

#### Step 5: Assemble Context (→ Attention Service)

Call the attention service:

```python
attention_request = AttentionRequest(
    agent_id=ctx.agent_id,
    agent_class=ctx.agent_class,
    framework_id=ctx.framework_id,
    tier=ctx.tier,
    work_order_id=wo["work_order_id"],
    session_id=ctx.session_id,
    prompt_contract=selected_contract,
)
assembled_context = attention_service.assemble(attention_request)
```

- If attention returns warnings, log them
- If attention fails (no context + on_empty:fail), log and return failure

#### Step 6: Send Prompt (→ Prompt Router)

Build the prompt from:
- The assembled context (from attention)
- The prompt contract's template
- The WO's input data (if `io_schema.input_schema` is defined)

Call the prompt router:

```python
router_response = prompt_router.send(
    prompt=rendered_prompt,
    contract=selected_contract,
    agent_id=ctx.agent_id,
    agent_class=ctx.agent_class,
    framework_id=ctx.framework_id,
    work_order_id=wo["work_order_id"],
    session_id=ctx.session_id,
)
```

- Router handles: auth, budget check, pre-log, dispatch, post-log, debit, output validation
- Flow runner receives: response text, tokens_used, ledger_entry_ids, validation_result

#### Step 7: Validate Acceptance Criteria

Check the WO's `acceptance` field:
1. If `acceptance.tests` is defined, run each test command (exit 0 = pass)
2. If `acceptance.checks` is defined, run each check command
3. If `io_schema.output_schema` is defined, validate response against it
4. Collect pass/fail results for each criterion

Log gate results to ledger.

**NOTE:** v1 acceptance criteria are simple (schema validation, basic checks). More complex criteria (running test suites, multi-file validation) are v2.

#### Step 8: Log Outcome

Write `WO_EXEC_COMPLETE` (or `WO_EXEC_FAILED`) to ledger with:
```
metadata:
  provenance: {agent_id, agent_class, framework_id, work_order_id, session_id}
  outcome: {status, quality_signal, error, gate_results}
  context_fingerprint: {context_hash from attention}
  tokens_used: {input, output} (from router)
  duration_ms: wall-clock time
```

📝 Ledger write: WO_EXEC_COMPLETE / WO_EXEC_FAILED

#### Step 9: Return

Return `FlowResult` with all execution metadata to the caller.

---

## Error Handling

| Condition | Step | Behavior |
|-----------|------|----------|
| Invalid work order | 1 | Reject, log WO_REJECTED |
| Framework not found | 2 | Reject, log WO_REJECTED |
| Agent class not permitted | 2 | Reject, log WO_REJECTED |
| Budget allocation denied | 3 | Reject, log WO_REJECTED |
| Attention service fails | 5 | Log failure, return status="failure" |
| Router rejects (auth/budget) | 6 | Log failure, return status="rejected" |
| Router times out | 6 | Log timeout, return status="timeout" |
| Provider error | 6 | Log error, return status="failure" |
| Acceptance criteria fail | 7 | Log failure, return status="failure" with gate_results |
| Any uncaught exception | any | Log to ledger, return status="failure", never crash silently |

Every error path writes to the ledger. The caller always gets a FlowResult, never an exception.

---

## v2 Extension Points (Design Now, Implement Later)

These interfaces should exist in v1 code as clearly marked extension points, but the implementations can be stubs or raise NotImplementedError.

### Multi-Step Execution

v1 is single-step: one prompt, one response, done.
v2 adds a step loop:

```python
# v2 extension point in flow_runner.py
class StepStrategy:
    """Base class for execution strategies."""

    def next_step(self, context: ExecutionContext, history: list[StepResult]) -> StepAction:
        """Decide what to do next: send_prompt, delegate, or complete."""
        raise NotImplementedError("Multi-step is v2")

class SingleStepStrategy(StepStrategy):
    """v1: one prompt, one response, done."""

    def next_step(self, context, history):
        if not history:
            return StepAction(type="send_prompt")
        return StepAction(type="complete")
```

### Aperture Model

OPEN (explore) → CLOSING (prepare) → CLOSED (execute)

Aperture state influences which attention template is selected:
- OPEN: broad search, horizontal_search enabled, high max_queries
- CLOSING: narrowing, specific queries only, lower budget
- CLOSED: minimal context, just what's needed for final output

```python
# v2 extension point
class ApertureManager:
    """Manages aperture state transitions."""

    def current_state(self) -> str:
        """Returns: 'open', 'closing', 'closed'"""
        return "closed"  # v1: always closed (single-step)

    def should_transition(self, step_count: int, budget_remaining: float) -> str | None:
        """Returns new state or None. v2: config-driven transition rules."""
        return None  # v1: no transitions
```

### HO2→HO1 Delegation

An HO2 agent can decompose its WO into sub-WOs for HO1 agents:

```python
# v2 extension point
class DelegationManager:
    """Manages sub-WO creation and HO2→HO1 delegation."""

    def create_sub_wo(self, parent_wo: dict, sub_task: dict) -> dict:
        """Create a child WO with parent_work_order_id set. Budget from parent's remaining."""
        raise NotImplementedError("Delegation is v2")

    def collect_results(self, sub_results: list[FlowResult]) -> dict:
        """Aggregate sub-WO results back to parent."""
        raise NotImplementedError("Delegation is v2")
```

### Partial Work Recovery

What happens when execution fails mid-way?

```python
# v2 extension point
class RecoveryStrategy:
    """Handles partial work on failure."""

    def on_failure(self, context: ExecutionContext, partial_results: list, error: str) -> str:
        """Returns: 'discard', 'quarantine', 'retry'. v1: always discard."""
        return "discard"  # v1: discard partial work
```

---

## Existing Infrastructure to Compose

The flow runner does NOT rewrite these — it imports and uses them:

| Component | File (conflated repo) | What Flow Runner Uses |
|-----------|----------------------|----------------------|
| LedgerFactory | `HOT/kernel/ledger_factory.py` | `create_work_order_instance_with_linkage()`, `write_wo_events()` |
| LedgerClient | `HOT/kernel/ledger_client.py` | Write WO_STARTED, WO_EXEC_COMPLETE events |
| IsolatedWorkspace | `HOT/kernel/workspace.py` | Create ephemeral execution sandbox |
| Pristine enforcement | `HOT/kernel/pristine.py` | Validate agent's file access against path_authorizations |
| IntegrityChecker | `HOT/kernel/integrity.py` | Pre/post integrity verification |
| GateOperations | `HOT/kernel/gate_operations.py` | ID allocation for agent_id |
| Auth/AuthZ | `HOT/kernel/auth.py`, `authz.py` | Validate caller authorization |

**IMPORTANT:** These files live in the conflated repo. They are NOT in staging packages yet. The flow runner should import them via relative paths that work in both the conflated repo and clean installs. Use the `paths.py` pattern (`get_control_plane_root()` + env var override) for discovery.

**NOTE:** `ledger_factory.py` has `HO3` references (line 40-43). These are in the conflated repo, not staging. The flow runner should use tier names from the WO (`hot`/`ho2`/`ho1`), not from ledger_factory defaults. If ledger_factory doesn't handle `hot` as a tier name, add a mapping or use the clean staging version if available.

---

## New Framework: FMWK-005 Agent Orchestration

**Ships in:** PKG-FLOW-RUNNER-001

```yaml
framework_id: FMWK-005
title: Agent Orchestration Framework
version: "1.0.0"
status: active
ring: kernel
plane_id: hot
created_at: "2026-02-10T00:00:00Z"
assets:
  - agent_orchestration_standard.md
expected_specs:
  - SPEC-ORCHESTRATION-001
invariants:
  - level: MUST
    statement: Every agent execution MUST be governed by a work order — no open-ended permissions
  - level: MUST
    statement: Every work order execution MUST be logged to the ledger (WO_STARTED + WO_EXEC_COMPLETE/FAILED)
  - level: MUST
    statement: Agent instantiation MUST read from framework definitions — agents don't create themselves
  - level: MUST NOT
    statement: The flow runner MUST NOT make LLM calls directly — all prompts go through the prompt router
  - level: MUST
    statement: Budget enforcement MUST be mandatory — agents that exceed budget are stopped
  - level: MUST NOT
    statement: Timeouts, budget defaults, and retry counts MUST NOT be hardcoded
  - level: MUST
    statement: v2 extension points (multi-step, aperture, delegation, recovery) MUST be defined as interfaces in v1 code
path_authorizations:
  - "HOT/kernel/flow_runner.py"
  - "HOT/FMWK-005_Agent_Orchestration/*.yaml"
  - "HOT/FMWK-005_Agent_Orchestration/*.md"
  - "HOT/tests/test_flow_runner.py"
required_gates:
  - G0
  - G1
  - G5
```

---

## Package Plan

### PKG-FLOW-RUNNER-001 (Layer 3)

Assets:
- `HOT/kernel/flow_runner.py` — main flow runner: WO validation, framework resolution, execution lifecycle
- `HOT/FMWK-005_Agent_Orchestration/manifest.yaml` — framework manifest
- `HOT/tests/test_flow_runner.py` — all tests

Dependencies:
- `PKG-KERNEL-001` (for ledger_client, paths, pristine)
- `PKG-PHASE2-SCHEMAS-001` (for work_order.schema.json, ledger_entry_metadata.schema.json)
- `PKG-TOKEN-BUDGETER-001` (for budget allocation)
- `PKG-PROMPT-ROUTER-001` (for prompt dispatch)
- `PKG-ATTENTION-001` (for context assembly)

This is the highest-dependency package — it composes all the other Layer 3 components.

---

## Config Schema: flow_runner_config.schema.json

Create a new config schema for flow runner settings:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://control-plane.local/schemas/flow_runner_config.schema.json",
  "title": "Flow Runner Configuration v1.0",
  "type": "object",
  "properties": {
    "default_budget": {
      "type": "object",
      "properties": {
        "token_limit": { "type": "integer", "minimum": 1 },
        "turn_limit": { "type": "integer", "minimum": 1 },
        "timeout_seconds": { "type": "integer", "minimum": 1 }
      },
      "description": "Default budget when WO doesn't specify one"
    },
    "agent_id_prefix": {
      "type": "string",
      "default": "AGT",
      "description": "Prefix for generated agent IDs"
    },
    "max_concurrent_flows": {
      "type": "integer",
      "minimum": 1,
      "default": 1,
      "description": "Max concurrent flow executions (v1: always 1)"
    },
    "execution_timeout_seconds": {
      "type": "integer",
      "minimum": 1,
      "description": "Global timeout for flow execution (overrides WO budget if lower)"
    },
    "v2_features": {
      "type": "object",
      "properties": {
        "multi_step_enabled": { "type": "boolean", "default": false },
        "aperture_enabled": { "type": "boolean", "default": false },
        "delegation_enabled": { "type": "boolean", "default": false },
        "recovery_enabled": { "type": "boolean", "default": false }
      },
      "description": "v2 feature flags (all false in v1)"
    }
  },
  "additionalProperties": true
}
```

---

## Test Plan (DTT — Tests First)

### Write ALL these tests BEFORE any implementation code.

**Work Order Validation (Step 1):**
1. `test_valid_wo_accepted` — well-formed WO passes validation
2. `test_invalid_wo_rejected` — malformed WO rejected with error
3. `test_missing_required_fields_rejected` — missing framework_id, scope, etc. rejected
4. `test_authorization_validated` — authorization chain checked when present
5. `test_wo_rejected_logged` — rejected WO writes WO_REJECTED to ledger

**Framework Resolution (Step 2):**
6. `test_framework_found` — framework_id resolved to manifest
7. `test_framework_not_found_rejected` — unknown framework → rejection
8. `test_agent_class_from_wo` — agent_class extracted from WO
9. `test_agent_class_not_permitted` — agent_class not in framework → rejection
10. `test_agent_id_generated` — unique agent ID created with correct format
11. `test_tier_from_plane_id` — tier determined from WO plane_id

**Budget Allocation (Step 3):**
12. `test_budget_from_wo` — WO budget fields used for allocation
13. `test_default_budget_when_absent` — config defaults used when WO has no budget
14. `test_budget_denied_rejects` — over-committed session → WO rejected
15. `test_budget_scope_correct` — budget scoped to session + WO + agent

**Execution Context (Step 4):**
16. `test_context_created` — ExecutionContext has all required fields
17. `test_prompt_contracts_resolved` — contracts for framework/agent_class loaded
18. `test_path_authorizations_set` — from framework manifest
19. `test_tool_permissions_set` — from WO tool_permissions
20. `test_wo_started_logged` — WO_STARTED written to ledger with full metadata

**Attention (Step 5):**
21. `test_attention_called` — attention service called with correct AttentionRequest
22. `test_attention_warnings_logged` — warnings from attention captured
23. `test_attention_failure_handled` — attention fail → flow returns failure

**Prompt Routing (Step 6):**
24. `test_router_called` — router called with assembled context + contract
25. `test_router_rejection_handled` — auth/budget rejection → flow failure
26. `test_router_timeout_handled` — timeout → flow timeout
27. `test_router_response_captured` — response text, tokens, entry IDs captured

**Acceptance Criteria (Step 7):**
28. `test_output_schema_validated` — response validated against io_schema.output_schema
29. `test_acceptance_all_pass` — all criteria pass → success
30. `test_acceptance_partial_fail` — some criteria fail → failure with gate_results

**Outcome (Step 8):**
31. `test_success_logged` — WO_EXEC_COMPLETE logged with full outcome metadata
32. `test_failure_logged` — WO_EXEC_FAILED logged with error detail
33. `test_ledger_entry_ids_collected` — all ledger entries from flow in result

**Full Flow (End-to-End Unit):**
34. `test_happy_path_single_step` — full flow: valid WO → framework → budget → context → prompt → accept → success
35. `test_dev_mode_bypasses_auth` — dev mode skips auth, uses mock provider
36. `test_result_always_returned` — no exceptions leak, FlowResult always returned

**v2 Extension Points:**
37. `test_single_step_strategy` — SingleStepStrategy: send one prompt, then complete
38. `test_aperture_always_closed_v1` — ApertureManager returns "closed" in v1
39. `test_delegation_not_implemented_v1` — DelegationManager raises NotImplementedError
40. `test_recovery_discards_v1` — RecoveryStrategy returns "discard" in v1

### End-to-End Install Test
1. Clean-room extract CP_BOOTSTRAP → install Layers 0-2 (8 packages)
2. Install PKG-PHASE2-SCHEMAS-001
3. Install PKG-TOKEN-BUDGETER-001
4. Install PKG-PROMPT-ROUTER-001
5. Install PKG-ATTENTION-001
6. Install PKG-FLOW-RUNNER-001
7. All gates pass at every step
8. Integration test: create mock framework manifest → create WO → run flow → verify ledger entries (WO_STARTED + WO_EXEC_COMPLETE) + budget debit + response returned

---

## Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Work order schema | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/schemas/work_order.schema.json` | Validate WOs |
| Ledger metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | Structure ledger entries |
| Framework manifests | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/FMWK-*/manifest.yaml` | Framework resolution pattern |
| Framework registry | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/registries/frameworks_registry.csv` | Framework lookup |
| LedgerFactory | `HOT/kernel/ledger_factory.py` (conflated repo) | WO lifecycle events |
| IsolatedWorkspace | `HOT/kernel/workspace.py` (conflated repo) | Execution sandboxing |
| Pristine enforcement | `HOT/kernel/pristine.py` (conflated repo) | Path authorization enforcement |
| Attention handoff | `_staging/BUILDER_HANDOFF_4_attention_service.md` | Attention interface |
| Router handoff | `_staging/BUILDER_HANDOFF_3_prompt_router.md` | Router interface |
| DoPeJar flow | `KERNEL_PHASE_2.md` lines 878-907 | The concrete example of how it all fits |

---

## Design Principles (Non-Negotiable)

1. **Flow runner is infrastructure, not an agent.** It's KERNEL.semantic machinery. It reads framework definitions and creates execution contexts — it doesn't decide what to do.
2. **Work orders are mandatory.** No agent runs without a WO. No open-ended permissions. The WO IS the mandate.
3. **Agents don't remember, they READ.** No internal state between executions. All persistent state = ledger queries via attention.
4. **Budget is enforced, not advisory.** If the budget says stop, execution stops. No negotiation.
5. **v1 is deliberately simple.** One prompt, one response, done. The extension points exist as interfaces for v2, not as implemented features.
6. **Compose, don't rewrite.** LedgerFactory, IsolatedWorkspace, pristine.py — use them. Don't rewrite them.
7. **Every execution writes to the ledger.** WO_STARTED on begin, WO_EXEC_COMPLETE/FAILED on end. The ledger is the permanent record.
