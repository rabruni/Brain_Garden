# BUILDER_HANDOFF_13: Work Order — The Atom of Cognitive Dispatch

## 1. Mission

Create `PKG-WORK-ORDER-001` — the atomic unit of cognitive dispatch between HO2 (deliberative/supervisory) and HO1 (reactive/execution). A work order is a structured, bounded, one-shot instruction that HO2 creates and HO1 executes. This package provides the `WorkOrder` dataclass, state machine, WO-specific ledger entry types, and JSON Schema for cognitive dispatch WOs. Without this package, there is no structured communication between tiers — just raw function calls. Both HO2 and HO1 depend on this dataclass. If either package owned it, the other would have a circular dependency. WO is shared infrastructure.

After this handoff, the system has a typed, validated, state-machine-enforced work order that HO2 can create, HO1 can execute, and both tiers can log with full relational metadata per FMWK-008.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-WORK-ORDER-001/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> install all layers -> install YOUR new package. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_13.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results. New failures you introduced are blockers. Pre-existing failures from unvalidated packages are noted but not blockers.
10. **Baseline snapshot.** Your results file must include a baseline snapshot (package count, file_ownership rows, total tests, all gate results) so the next agent can diff against it.

**Task-specific constraints:**

11. **LedgerClient method is `write()`.** The method is `LedgerClient.write(LedgerEntry) -> str`. NOT `append()`. Every reference in this spec uses `write()` — do not substitute.
12. **Separate schema, not extension.** `cognitive_work_order.schema.json` is a SEPARATE schema from the existing `work_order.schema.json`. No `$ref` cross-linking. Coexistence, convergence deferred.
13. **4 cognitive types only.** `classify`, `tool_call`, `synthesize`, `execute`. Do not add speculative types (delegate, escalate, etc.).
14. **5 lifecycle states only.** `planned`, `dispatched`, `executing`, `completed`, `failed`. Do not add speculative states.
15. **Relational metadata from day one.** Every WO ledger entry MUST include `metadata.relational` fields per FMWK-008 Section 5b. Append-only ledger means lost connections are permanent.
16. **No real LLM calls in tests.** All tests use mock/fixture data. Zero tests require an API key.

---

## 3. Architecture / Design

### Bounded Context

| Owns | Does NOT Own |
|------|-------------|
| `WorkOrder` dataclass (all fields) | WO creation logic (HO2 — HANDOFF-15) |
| `WorkOrderStateMachine` (transition enforcement) | WO execution logic (HO1 — HANDOFF-14) |
| `WorkOrderValidator` (schema validation) | Budget allocation (Token Budgeter) |
| WO-specific ledger entry types (7 types) | Prompt contract loading (FMWK-011) |
| `cognitive_work_order.schema.json` | Routing decisions (HO2) |
| `manifest.json` | |

### Kitchener Role

Steps 2, 3, 4 data contract. The WO is what flows between HO2 and HO1 at every step:

| Kitchener Step | Tier | WO Relationship |
|----------------|------|-----------------|
| Step 2: Scoping (L2) | HO2 | HO2 creates WOs with acceptance criteria. `planned` and `dispatched` states. |
| Step 3: Execution (L1) | HO1 | HO1 receives WOs, executes them. `executing`, `completed`, `failed` states. |
| Step 4: Verification (L2) | HO2 | HO2 checks WO output against Step 2 criteria. `WO_QUALITY_GATE` event. |

### WorkOrder Dataclass

```python
@dataclass
class WorkOrder:
    wo_id: str                          # WO-{session_id}-{seq:03d}
    session_id: str                     # SES-{8 alphanum}
    wo_type: str                        # classify | tool_call | synthesize | execute
    tier_target: str                    # "HO1" (always, for now)
    state: str                          # planned | dispatched | executing | completed | failed
    created_at: str                     # ISO8601 UTC
    created_by: str                     # Agent ID (always an HO2 agent)

    # Optional identity
    parent_wo_id: Optional[str] = None  # Parent WO for chained dispatch

    # Input (set at creation by HO2)
    input_context: Dict[str, Any] = field(default_factory=dict)
    #   .user_input: str
    #   .prior_results: List[Dict]
    #   .assembled_context: Dict

    constraints: Dict[str, Any] = field(default_factory=dict)
    #   .prompt_contract_id: str (required for LLM-calling types)
    #   .token_budget: int (> 0, within session budget)
    #   .turn_limit: int (max LLM round-trips)
    #   .timeout_seconds: int
    #   .tools_allowed: List[str]

    acceptance_criteria: Dict[str, Any] = field(default_factory=dict)

    # Output (set at completion by HO1)
    output_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    completed_at: Optional[str] = None

    # Cost tracking
    cost: Dict[str, Any] = field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "llm_calls": 0,
        "tool_calls": 0,
        "elapsed_ms": 0,
    })
```

### State Machine

```
planned --> dispatched --> executing --> completed
                                    --> failed
```

Valid transitions:

| From | To | Who | Condition |
|------|----|-----|-----------|
| `planned` | `dispatched` | HO2 | WO passes validation |
| `planned` | `failed` | HO2 | Validation fails at planning time |
| `dispatched` | `executing` | HO1 | HO1 picks up the WO |
| `executing` | `completed` | HO1 | Result produced, output validates |
| `executing` | `failed` | HO1 | Error, timeout, budget exceeded |

Forbidden transitions:

| Transition | Reason |
|------------|--------|
| `completed` -> any | Terminal state — never regresses |
| `failed` -> any | Terminal state — never regresses |
| `executing` -> `planned` | No backward regression |
| `dispatched` -> `planned` | No backward regression |
| HO1 -> `planned` or `dispatched` | HO1 cannot create or dispatch WOs |

### WO Ledger Entry Types

7 event types, split across two ledgers per FMWK-008 Section 5:

**HO2 Ledger** (`HO2/ledger/workorder.jsonl`):

| Event Type | When | Relational Metadata |
|------------|------|---------------------|
| `WO_PLANNED` | HO2 creates WO | `root_event_id`, `related_artifacts` |
| `WO_DISPATCHED` | HO2 sends to HO1 | `parent_event_id` -> `WO_PLANNED` |
| `WO_CHAIN_COMPLETE` | All WOs in turn done | `root_event_id`, `related_artifacts`, `trace_hash` |
| `WO_QUALITY_GATE` | HO2 approves/rejects | `parent_event_id` -> `WO_CHAIN_COMPLETE`, `trace_hash` |

**HO1 Ledger** (`HO1/ledger/worker.jsonl`):

| Event Type | When | Relational Metadata |
|------------|------|---------------------|
| `WO_EXECUTING` | HO1 picks up WO | `parent_event_id` -> HO2 `WO_DISPATCHED`, `root_event_id` |
| `WO_COMPLETED` | Execution succeeds | `parent_event_id` -> `WO_EXECUTING`, `root_event_id` |
| `WO_FAILED` | Execution fails | `parent_event_id` -> `WO_EXECUTING`, `root_event_id` |

Every ledger entry uses `LedgerClient.write(LedgerEntry)` and includes:
- `metadata.provenance`: `agent_id`, `agent_class`, `work_order_id`, `session_id`
- `metadata.relational`: `parent_event_id`, `root_event_id`, `related_artifacts` (when applicable)

### Schema Coexistence

Two WO schemas coexist:

| Schema | Package | Types | Purpose |
|--------|---------|-------|---------|
| `work_order.schema.json` | PKG-FRAMEWORK-WIRING-001 | `code_change`, `spec_delta`, `registry_change`, `dependency_add` | Governance WOs (syntactic) |
| `cognitive_work_order.schema.json` | PKG-WORK-ORDER-001 | `classify`, `tool_call`, `synthesize`, `execute` | Cognitive dispatch WOs |

Both share common fields (`wo_id`, `session_id`, `budget`) but are structurally independent. No `$ref` cross-linking. Convergence deferred.

### Adversarial Analysis: WorkOrder Dataclass Design

**Hurdles**: Two WO schemas coexist (governance + cognitive). The WorkOrder dataclass must include ALL fields that HANDOFF-14 (HO1 Executor) and HANDOFF-15 (HO2 Supervisor) need: `input_context`, `output_result`, `acceptance_criteria`, `constraints`, `cost`. Relational metadata (`parent_wo_id`, `root_event_id`) must be present from day one — append-only ledger means lost connections are permanent.

**Too Much**: Over-specifying the state machine with speculative WO types (`delegate`, `escalate`) or complex transition guards (conditional transitions based on cost thresholds). Stop at 4 cognitive types and 5 states. Do not build orchestration logic (pipeline, parallel, voting) — that belongs to HO2 (HANDOFF-15).

**Not Enough**: If the WO dataclass is too thin (missing `acceptance_criteria`, `cost`, or relational fields), HANDOFF-14 and HANDOFF-15 will independently ad-hoc these fields, creating divergent representations that cannot be reconciled without breaking the append-only ledger.

**Synthesis**: Full dataclass with all needed fields. Strict state machine (no regression, terminal states enforced). 4 cognitive types only. Relational metadata from day one. Separate schema, not extension of the governance schema.

### Adversarial Analysis: Schema Coexistence

**Hurdles**: Two schemas for "work order" creates potential confusion. Builders might try to merge them or reference one from the other. Field names overlap but semantics differ (`type` means `code_change` in one, `classify` in the other).

**Too Much**: Merging the schemas now would require reworking `work_order.schema.json` consumers (PKG-FRAMEWORK-WIRING-001), which is stable and gate-verified. The refactoring cost outweighs the naming clarity.

**Not Enough**: Without the cognitive schema, WO validation falls back to ad-hoc Python checks in HO1 and HO2 — unauditable, unversioned, and fragile.

**Synthesis**: Separate schemas. Clear naming (`cognitive_work_order.schema.json`). Convergence deferred to a future housekeeping handoff when both consumers are stable.

---

## 4. Implementation Steps

### Step 1: Write tests (DTT)

Create `_staging/PKG-WORK-ORDER-001/HOT/tests/test_work_order.py` with all tests from the Test Plan (Section 6). Tests use `tmp_path` fixtures and mock data. No real LLM calls, no real API keys.

### Step 2: Implement WorkOrder dataclass

Create `_staging/PKG-WORK-ORDER-001/HOT/kernel/work_order.py`:

```python
"""Work Order — the atomic unit of cognitive dispatch.

HO2 creates work orders, HO1 executes them, HO2 verifies them.
This module provides the WorkOrder dataclass, state machine
(WorkOrderStateMachine), and validator (WorkOrderValidator).

Governed by FMWK-008 (Work Order Protocol).

Usage:
    from kernel.work_order import WorkOrder, WorkOrderStateMachine, WorkOrderValidator

    wo = WorkOrder.create(
        wo_type="classify",
        session_id="SES-A1B2C3D4",
        created_by="ADMIN.ho2",
        input_context={"user_input": "show me all frameworks"},
        constraints={"prompt_contract_id": "PC-C-001", "token_budget": 2000},
    )

    WorkOrderStateMachine.transition(wo, "dispatched")
"""
```

Classes and methods:

**`WorkOrder`** (dataclass):
- All fields per Architecture section above
- `create(wo_type, session_id, created_by, input_context, constraints, ...) -> WorkOrder` — class method, generates `wo_id` from session_id + sequence, sets `created_at`, validates `wo_type`
- `to_dict() -> Dict` — serialization
- `from_dict(data: Dict) -> WorkOrder` — deserialization
- `to_json() -> str` — JSON serialization
- `from_json(json_str: str) -> WorkOrder` — JSON deserialization
- `is_terminal() -> bool` — True if state is `completed` or `failed`

**`WorkOrderStateMachine`**:
- `VALID_TRANSITIONS: Dict[str, Set[str]]` — the allowed transition map
- `TERMINAL_STATES: Set[str]` — `{"completed", "failed"}`
- `HO1_ALLOWED_STATES: Set[str]` — `{"executing", "completed", "failed"}` — states HO1 can transition to
- `transition(wo: WorkOrder, new_state: str, actor_tier: str = "HO2") -> WorkOrder` — validates transition, updates state, returns updated WO. Raises `InvalidTransitionError` on forbidden transition.

**`WorkOrderValidator`**:
- `validate(wo: WorkOrder) -> Tuple[bool, List[str]]` — validates all required fields, type enum, constraints for LLM-calling types
- `validate_against_schema(wo_dict: Dict, schema_path: Path) -> Tuple[bool, List[str]]` — validates against `cognitive_work_order.schema.json`

**Exceptions**:
- `InvalidTransitionError(Exception)` — raised on forbidden state transitions
- `WorkOrderValidationError(Exception)` — raised on validation failure

### Step 3: Implement WO Ledger Helper

Create `_staging/PKG-WORK-ORDER-001/HOT/kernel/wo_ledger.py`:

```python
"""WO-specific ledger entry helper.

Creates properly structured LedgerEntry instances for each WO lifecycle event.
Every entry includes metadata.relational fields per FMWK-008 Section 5b.

Usage:
    from kernel.wo_ledger import WOLedgerHelper

    helper = WOLedgerHelper(ledger_client)
    entry_id = helper.write_wo_planned(work_order, root_event_id=None)
"""
```

**`WOLedgerHelper`**:
- `__init__(self, ledger_client: LedgerClient)` — takes an initialized LedgerClient
- 7 methods, one per event type:
  - `write_wo_planned(wo: WorkOrder, root_event_id: Optional[str] = None) -> str` — returns entry ID
  - `write_wo_dispatched(wo: WorkOrder, parent_event_id: str) -> str`
  - `write_wo_executing(wo: WorkOrder, parent_event_id: str, root_event_id: str) -> str`
  - `write_wo_completed(wo: WorkOrder, parent_event_id: str, root_event_id: str) -> str`
  - `write_wo_failed(wo: WorkOrder, parent_event_id: str, root_event_id: str) -> str`
  - `write_wo_chain_complete(session_id: str, wo_ids: List[str], total_cost: Dict, trace_hash: str, root_event_id: str) -> str`
  - `write_wo_quality_gate(session_id: str, decision: str, parent_event_id: str, trace_hash: str) -> str`

Each method:
1. Creates a `LedgerEntry` with proper `event_type`
2. Populates `metadata.provenance` (`agent_id`, `agent_class`, `work_order_id`, `session_id`)
3. Populates `metadata.relational` (`parent_event_id`, `root_event_id`, `related_artifacts`)
4. Calls `self.ledger_client.write(entry)` — NOT `append()`
5. Returns the entry ID

### Step 4: Create cognitive_work_order.schema.json

Create `_staging/PKG-WORK-ORDER-001/HOT/schemas/cognitive_work_order.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://control-plane.local/schemas/cognitive_work_order.schema.json",
  "title": "Cognitive Work Order Schema",
  "description": "Schema for cognitive dispatch WOs — HO2 creates, HO1 executes",
  "type": "object",
  "required": ["wo_id", "session_id", "wo_type", "tier_target", "state", "created_at", "created_by"],
  "properties": {
    "wo_id": {
      "type": "string",
      "pattern": "^WO-SES-[A-Z0-9]{8}-\\d{3}$"
    },
    "session_id": {
      "type": "string",
      "pattern": "^SES-[A-Z0-9]{8}$"
    },
    "wo_type": {
      "type": "string",
      "enum": ["classify", "tool_call", "synthesize", "execute"]
    },
    "tier_target": {
      "type": "string",
      "enum": ["HO1"]
    },
    "state": {
      "type": "string",
      "enum": ["planned", "dispatched", "executing", "completed", "failed"]
    },
    ...
  }
}
```

Full schema must cover all fields from the WorkOrder dataclass. 4 cognitive types. 5 states. `additionalProperties: true` for forward compatibility.

### Step 5: Create manifest.json

Create `_staging/PKG-WORK-ORDER-001/manifest.json`:

```json
{
  "package_id": "PKG-WORK-ORDER-001",
  "version": "1.0.0",
  "schema_version": "1.2",
  "title": "Work Order - Cognitive Dispatch Atom",
  "description": "WorkOrder dataclass, state machine, WO-specific ledger helpers, and cognitive dispatch schema",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot",
  "layer": 3,
  "dependencies": [
    "PKG-KERNEL-001",
    "PKG-FRAMEWORK-WIRING-001",
    "PKG-PHASE2-SCHEMAS-001"
  ],
  "assets": [
    {
      "path": "HOT/kernel/work_order.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "source"
    },
    {
      "path": "HOT/kernel/wo_ledger.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "source"
    },
    {
      "path": "HOT/schemas/cognitive_work_order.schema.json",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "schema"
    },
    {
      "path": "HOT/tests/test_work_order.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "test"
    }
  ]
}
```

### Step 6: Build package archive

Build `_staging/PKG-WORK-ORDER-001.tar.gz` using Python `tarfile` with explicit `arcname`:

```python
import tarfile
from pathlib import Path

def build_pkg(pkg_dir, output_path):
    with tarfile.open(output_path, "w:gz") as tf:
        for f in sorted(Path(pkg_dir).rglob("*")):
            if f.is_file() and "__pycache__" not in str(f):
                tf.add(str(f), arcname=str(f.relative_to(pkg_dir)))
```

### Step 7: Rebuild CP_BOOTSTRAP.tar.gz

Add PKG-WORK-ORDER-001.tar.gz to the bootstrap archive. Total: 18 packages (17 existing + PKG-WORK-ORDER-001).

Verify: `tar tzf CP_BOOTSTRAP.tar.gz | grep '.tar.gz' | wc -l` should show 18.

### Step 8: Clean-room verification

Run verification commands per Section 8.

### Step 9: Write results file

Write `_staging/RESULTS_HANDOFF_13.md` following the standard format.

---

## 5. Package Plan

### New Package

| Field | Value |
|-------|-------|
| Package ID | `PKG-WORK-ORDER-001` |
| Layer | 3 |
| spec_id | `SPEC-GATE-001` |
| framework_id | `FMWK-000` |
| plane_id | `hot` |
| Dependencies | `PKG-KERNEL-001`, `PKG-FRAMEWORK-WIRING-001`, `PKG-PHASE2-SCHEMAS-001` |

### Assets

| Path | Classification |
|------|---------------|
| `HOT/kernel/work_order.py` | source |
| `HOT/kernel/wo_ledger.py` | source |
| `HOT/schemas/cognitive_work_order.schema.json` | schema |
| `HOT/tests/test_work_order.py` | test |
| `manifest.json` | manifest |

### No Modified Packages

This handoff creates one new package only. No existing packages are modified.

---

## 6. Test Plan

**File:** `_staging/PKG-WORK-ORDER-001/HOT/tests/test_work_order.py`

All tests use `tmp_path` fixtures and mock data. No real LLM calls. No real API keys. **25+ tests.**

### WorkOrder Creation Tests

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_create_classify_wo` | `WorkOrder.create(wo_type="classify", ...)` returns a WorkOrder with state `planned`, correct `wo_type`, auto-generated `wo_id`, `created_at` set |
| 2 | `test_create_tool_call_wo` | `wo_type="tool_call"` accepted, `tier_target` is `HO1` |
| 3 | `test_create_synthesize_wo` | `wo_type="synthesize"` accepted |
| 4 | `test_create_execute_wo` | `wo_type="execute"` accepted |
| 5 | `test_create_invalid_type_rejected` | `wo_type="delegate"` raises error — only 4 types allowed |
| 6 | `test_create_required_fields` | Missing `session_id` or `created_by` raises error |
| 7 | `test_create_default_cost` | Default `cost` dict has all 6 zero fields |

### State Machine Transition Tests

| # | Test | Validates |
|---|------|-----------|
| 8 | `test_planned_to_dispatched` | Valid transition, state updated |
| 9 | `test_dispatched_to_executing` | Valid transition |
| 10 | `test_executing_to_completed` | Valid transition, `is_terminal()` returns True |
| 11 | `test_executing_to_failed` | Valid transition, `is_terminal()` returns True |
| 12 | `test_planned_to_failed` | Valid transition (validation fail at planning) |
| 13 | `test_completed_to_any_forbidden` | `completed` -> `dispatched` raises `InvalidTransitionError` |
| 14 | `test_failed_to_any_forbidden` | `failed` -> `executing` raises `InvalidTransitionError` |
| 15 | `test_executing_to_planned_forbidden` | No backward regression |
| 16 | `test_dispatched_to_planned_forbidden` | No backward regression |
| 17 | `test_ho1_cannot_set_planned` | `transition(wo, "planned", actor_tier="HO1")` raises error |
| 18 | `test_ho1_cannot_set_dispatched` | `transition(wo, "dispatched", actor_tier="HO1")` raises error |

### WorkOrder Validation Tests

| # | Test | Validates |
|---|------|-----------|
| 19 | `test_validate_valid_wo` | Well-formed WO passes validation |
| 20 | `test_validate_missing_prompt_contract` | LLM-calling type (`classify`) without `constraints.prompt_contract_id` fails |
| 21 | `test_validate_tool_call_needs_tools` | `tool_call` without `constraints.tools_allowed` fails |
| 22 | `test_validate_budget_positive` | `constraints.token_budget` of 0 or negative fails |

### WO Ledger Entry Tests

| # | Test | Validates |
|---|------|-----------|
| 23 | `test_write_wo_planned_creates_entry` | `WOLedgerHelper.write_wo_planned()` calls `ledger_client.write()` with event_type `WO_PLANNED` |
| 24 | `test_write_wo_dispatched_has_parent` | `WO_DISPATCHED` entry includes `metadata.relational.parent_event_id` |
| 25 | `test_write_wo_executing_has_relational` | `WO_EXECUTING` entry includes both `parent_event_id` and `root_event_id` |
| 26 | `test_write_wo_completed_has_cost` | `WO_COMPLETED` entry includes cost in metadata |
| 27 | `test_write_wo_failed_has_error` | `WO_FAILED` entry includes error in metadata |
| 28 | `test_write_wo_chain_complete_has_trace_hash` | `WO_CHAIN_COMPLETE` entry includes `trace_hash` in `metadata.context_fingerprint.context_hash` |
| 29 | `test_write_wo_quality_gate_has_decision` | `WO_QUALITY_GATE` entry includes decision field |
| 30 | `test_all_entries_have_provenance` | Every event type populates `metadata.provenance` with `agent_id`, `agent_class`, `work_order_id`, `session_id` |

### Schema Coexistence Tests

| # | Test | Validates |
|---|------|-----------|
| 31 | `test_cognitive_schema_validates_independently` | `cognitive_work_order.schema.json` loads and validates a cognitive WO without referencing `work_order.schema.json` |
| 32 | `test_cognitive_schema_rejects_governance_type` | `wo_type="code_change"` fails cognitive schema validation |

### Serialization Tests

| # | Test | Validates |
|---|------|-----------|
| 33 | `test_wo_json_roundtrip` | `WorkOrder.to_json()` -> `WorkOrder.from_json()` produces identical object |
| 34 | `test_wo_dict_roundtrip` | `WorkOrder.to_dict()` -> `WorkOrder.from_dict()` produces identical object |

### Edge Case Tests

| # | Test | Validates |
|---|------|-----------|
| 35 | `test_parent_wo_id_chain` | WO with `parent_wo_id` set serializes and deserializes correctly |
| 36 | `test_empty_input_context` | WO with empty `input_context` dict is valid |
| 37 | `test_wo_id_format` | Generated `wo_id` matches pattern `WO-SES-{8 alphanum}-{seq:03d}` |

**37 tests total.** Covers: creation (7), state machine (11), validation (4), ledger entries (8), schema coexistence (2), serialization (2), edge cases (3).

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Existing WO schema | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/schemas/work_order.schema.json` | Coexistence — new cognitive schema alongside this. Shared field names for alignment. |
| LedgerClient | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | `write()` API (NOT `append()`). `LedgerEntry` dataclass. |
| SchemaValidator | `_staging/PKG-KERNEL-001/HOT/kernel/schema_validator.py` | `validate_manifest()` for package validation. Pattern reference for validation approach. |
| ledger_entry_metadata schema | `_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` | Relational metadata keys: `parent_event_id`, `root_event_id`, `related_artifacts`. Provenance keys. Context fingerprint for `trace_hash`. |
| FMWK-008 WO Protocol | `_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` | Binding governance: WO lifecycle, state transitions, ledger recording rules, metadata key standard (Sections 1-5b). |
| Builder standard | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Results file format, baseline snapshot format. |
| HANDOFF-12 example | `_staging/handoffs/BUILDER_HANDOFF_12_boot_materialize.md` | Reference handoff format. |

---

## 8. End-to-End Verification

```bash
# 1. Run package tests
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest PKG-WORK-ORDER-001/HOT/tests/test_work_order.py -v
# Expected: 37 tests pass

# 2. Verify package archive contents
tar tzf _staging/PKG-WORK-ORDER-001.tar.gz
# Expected:
#   manifest.json
#   HOT/kernel/work_order.py
#   HOT/kernel/wo_ledger.py
#   HOT/schemas/cognitive_work_order.schema.json
#   HOT/tests/test_work_order.py

# 3. Verify CP_BOOTSTRAP contents
tar tzf _staging/CP_BOOTSTRAP.tar.gz | grep '.tar.gz' | wc -l
# Expected: 18 (17 existing + PKG-WORK-ORDER-001)

# 4. Clean-room install
TESTDIR=$(mktemp -d)
INSTALLDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$INSTALLDIR"
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TESTDIR"
cd "$TESTDIR" && bash install.sh --root "$INSTALLDIR" --dev
# Expected: 18 packages installed, 8/8 gates PASS

# 5. Verify work_order.py importable
python3 -c "
import sys, pathlib
sys.path.insert(0, '$INSTALLDIR/HOT/kernel')
from work_order import WorkOrder, WorkOrderStateMachine, WorkOrderValidator
wo = WorkOrder.create(
    wo_type='classify',
    session_id='SES-TEST0001',
    created_by='ADMIN.ho2',
    input_context={'user_input': 'hello'},
    constraints={'prompt_contract_id': 'PC-C-001', 'token_budget': 2000},
)
print(f'Created: {wo.wo_id}, state={wo.state}, type={wo.wo_type}')
WorkOrderStateMachine.transition(wo, 'dispatched')
print(f'After dispatch: state={wo.state}')
WorkOrderStateMachine.transition(wo, 'executing', actor_tier='HO1')
print(f'After execute: state={wo.state}')
WorkOrderStateMachine.transition(wo, 'completed', actor_tier='HO1')
print(f'After complete: state={wo.state}, terminal={wo.is_terminal()}')
"
# Expected: state transitions planned->dispatched->executing->completed, terminal=True

# 6. Verify wo_ledger.py importable
python3 -c "
import sys, pathlib
sys.path.insert(0, '$INSTALLDIR/HOT/kernel')
from wo_ledger import WOLedgerHelper
print('WOLedgerHelper imported successfully')
"

# 7. Verify cognitive schema loads
python3 -c "
import json, pathlib
schema = json.loads(pathlib.Path('$INSTALLDIR/HOT/schemas/cognitive_work_order.schema.json').read_text())
print(f'Schema: {schema[\"title\"]}')
print(f'Types: {schema[\"properties\"][\"wo_type\"][\"enum\"]}')
print(f'States: {schema[\"properties\"][\"state\"][\"enum\"]}')
"
# Expected: 4 types, 5 states

# 8. Verify schema coexistence
python3 -c "
import json, pathlib
cog = json.loads(pathlib.Path('$INSTALLDIR/HOT/schemas/cognitive_work_order.schema.json').read_text())
gov = json.loads(pathlib.Path('$INSTALLDIR/HOT/schemas/work_order.schema.json').read_text())
assert '\$ref' not in json.dumps(cog), 'Cognitive schema must not \$ref governance schema'
assert cog['properties']['wo_type']['enum'] != gov['properties']['type']['enum'], 'Types must differ'
print('Schema coexistence verified: separate schemas, no cross-refs, different types')
"

# 9. Gate check
python3 "$INSTALLDIR/HOT/scripts/gate_check.py" --root "$INSTALLDIR" --all
# Expected: 8/8 gates PASS

# 10. Full regression
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest . -v --ignore=PKG-FLOW-RUNNER-001
# Expected: all pass, no new failures
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `work_order.py` | `_staging/PKG-WORK-ORDER-001/HOT/kernel/` | CREATE |
| `wo_ledger.py` | `_staging/PKG-WORK-ORDER-001/HOT/kernel/` | CREATE |
| `cognitive_work_order.schema.json` | `_staging/PKG-WORK-ORDER-001/HOT/schemas/` | CREATE |
| `test_work_order.py` | `_staging/PKG-WORK-ORDER-001/HOT/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-WORK-ORDER-001/` | CREATE |
| `PKG-WORK-ORDER-001.tar.gz` | `_staging/` | CREATE |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (18 packages) |
| `RESULTS_HANDOFF_13.md` | `_staging/` | CREATE |

**Not modified:** No existing package source files. No existing schemas. No existing manifests.

---

## 10. Design Principles

1. **The WO is a data contract, not an executor.** `WorkOrder` carries data and validates transitions. It does NOT call LLMs, execute tools, or manage sessions. Those responsibilities belong to HO1 (HANDOFF-14) and HO2 (HANDOFF-15).

2. **Terminal states are sacred.** `completed` and `failed` never regress. Once a WO reaches a terminal state, it is immutable. This is the foundation of audit integrity — if terminal WOs could be reopened, the ledger trace becomes unreliable.

3. **Relational metadata is not optional.** Every ledger entry includes `metadata.relational` fields per FMWK-008 Section 5b. The append-only ledger means connections that are not written at creation time are permanently lost. `parent_event_id` and `root_event_id` enable the graph traversal patterns that HO2 operational learning and KERNEL.semantic meta agent depend on.

4. **Schema separation preserves stability.** `cognitive_work_order.schema.json` and `work_order.schema.json` are independent. Neither references the other. This means changes to the cognitive schema during Kitchener loop development cannot break the governance WO pipeline, and vice versa.

5. **State machine enforces tier ownership.** HO1 cannot create or dispatch WOs — only HO2 can. HO1 can only transition WOs to `executing`, `completed`, or `failed`. This is not a convention; it is enforced by `WorkOrderStateMachine.transition()` checking `actor_tier`.

6. **LedgerClient.write() everywhere.** The method is `LedgerClient.write(LedgerEntry) -> str`. Never `append()`. This is consistent across the codebase and enforced by this handoff spec.
