# Agent Prompt: HANDOFF-13

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY -- print this FIRST before doing anything else:**
> **Agent: HANDOFF-13** -- PKG-WORK-ORDER-001: Work Order dataclass, state machine, WO ledger helpers, and cognitive dispatch schema

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST -- it is your complete specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_13_work_order.md`

**Also read these files to understand the governance and existing patterns:**
- `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` -- results file format, baseline snapshot format
- `Control_Plane_v2/_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` -- binding governance framework (Sections 1-5b are critical)
- `Control_Plane_v2/_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` -- LedgerClient.write() API and LedgerEntry dataclass
- `Control_Plane_v2/_staging/PKG-PHASE2-SCHEMAS-001/HOT/schemas/ledger_entry_metadata.schema.json` -- relational metadata key definitions
- `Control_Plane_v2/_staging/PKG-FRAMEWORK-WIRING-001/HOT/schemas/work_order.schema.json` -- existing governance WO schema (coexistence target)

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. End-to-end verification: clean-room install with 18 packages, 8/8 gates PASS.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_13.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.
6. LedgerClient method is write() -- NOT append(). Every call must use LedgerClient.write(LedgerEntry).
7. cognitive_work_order.schema.json is SEPARATE from work_order.schema.json. No $ref cross-linking.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is the bounded context of PKG-WORK-ORDER-001? What does it own, and what does it explicitly NOT own?

2. How does `cognitive_work_order.schema.json` relate to the existing `work_order.schema.json`? Do they share `$ref` references? What are the 4 cognitive WO types vs. the 4 governance WO types?

3. What are the 5 lifecycle states, and which are terminal? What is the exact state machine (draw all valid transitions)?

4. What is the exact LedgerClient method for writing entries -- `append()` or `write()`? What is its signature?

5. Name the 7 WO ledger event types. Which 4 go in HO2's ledger and which 3 go in HO1's ledger?

6. What `metadata.relational` fields must every WO ledger entry include per FMWK-008 Section 5b? Where does `trace_hash` go in the metadata structure?

7. What are `plane_id`, `layer`, and `dependencies` for this package? What assets go in `manifest.json`?

8. Name all forbidden state transitions and explain why each exists (terminal states, no regression, tier ownership).

9. How many tests minimum, and do any require a real LLM call or API key?

10. Who consumes the WorkOrder dataclass downstream? Name the specific handoffs and what they do with WorkOrder instances.

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

---

## Expected Answers (for reviewer -- do NOT show to agent)

1. **Owns**: `WorkOrder` dataclass (all fields), `WorkOrderStateMachine` (transition enforcement), `WorkOrderValidator` (schema validation), WO-specific ledger entry types (7 types via `WOLedgerHelper`), `cognitive_work_order.schema.json`, `manifest.json`. **Does NOT own**: WO creation logic (HO2 -- HANDOFF-15), WO execution logic (HO1 -- HANDOFF-14), budget allocation (Token Budgeter), prompt contract loading (FMWK-011), routing decisions (HO2).

2. They coexist as **SEPARATE schemas**. No `$ref` cross-linking. Existing schema covers governance WOs with 4 types: `code_change`, `spec_delta`, `registry_change`, `dependency_add`. New schema covers cognitive dispatch WOs with 4 types: `classify`, `tool_call`, `synthesize`, `execute`. Both share common fields (`wo_id`, `session_id`, `budget`) but are structurally independent. Convergence deferred.

3. **5 states**: `planned`, `dispatched`, `executing`, `completed`, `failed`. **Terminal**: `completed` and `failed`. **Transitions**: `planned`->`dispatched` (HO2), `planned`->`failed` (HO2), `dispatched`->`executing` (HO1), `executing`->`completed` (HO1), `executing`->`failed` (HO1).

4. **`write()`**. The method is `LedgerClient.write(LedgerEntry) -> str`. NOT `append()`. Returns the entry ID string.

5. **7 event types**: (HO2 ledger) `WO_PLANNED`, `WO_DISPATCHED`, `WO_CHAIN_COMPLETE`, `WO_QUALITY_GATE`. (HO1 ledger) `WO_EXECUTING`, `WO_COMPLETED`, `WO_FAILED`.

6. Per FMWK-008 Section 5b: `metadata.relational.parent_event_id` (when causal parent exists), `metadata.relational.root_event_id` (at chain boundaries and terminal events), `metadata.relational.related_artifacts` (when referencing governed artifacts). Plus provenance fields: `metadata.provenance.agent_id`, `metadata.provenance.agent_class`, `metadata.provenance.work_order_id`, `metadata.provenance.session_id`. The `trace_hash` goes into `metadata.context_fingerprint.context_hash` (as defined in `ledger_entry_metadata.schema.json`).

7. **plane_id**: `hot`. **layer**: 3. **Dependencies**: `PKG-KERNEL-001`, `PKG-FRAMEWORK-WIRING-001`, `PKG-PHASE2-SCHEMAS-001`. **Assets**: `HOT/kernel/work_order.py` (source), `HOT/kernel/wo_ledger.py` (source), `HOT/schemas/cognitive_work_order.schema.json` (schema), `HOT/tests/test_work_order.py` (test), `manifest.json`.

8. **Forbidden transitions and reasons**: (a) `completed` -> any state: terminal state, never regresses -- audit integrity depends on immutability. (b) `failed` -> any state: terminal state, same reason. (c) `executing` -> `planned`: no backward regression -- a WO that is executing cannot un-execute. (d) `dispatched` -> `planned`: no backward regression -- a WO that was sent to HO1 cannot be un-sent. (e) HO1 -> `planned` or `dispatched`: tier ownership -- only HO2 creates and dispatches WOs. HO1 can only set `executing`, `completed`, or `failed`. These prevent state corruption and enforce the Kitchener step boundaries.

9. **37 tests** (25+ minimum per spec, actual plan has 37). **Zero** require real LLM calls or API keys. All use mock/fixture data and `tmp_path` fixtures.

10. **HANDOFF-14** (PKG-HO1-EXECUTOR-001): HO1 Executor receives dispatched WorkOrder instances, transitions to `executing`, loads prompt contract from `constraints.prompt_contract_id`, executes via LLM Gateway, populates `output_result` and `cost`, transitions to `completed` or `failed`. **HANDOFF-15** (PKG-HO2-SUPERVISOR-001): HO2 Supervisor creates WorkOrder instances via `WorkOrder.create()`, validates, transitions to `dispatched`, dispatches to HO1, verifies results against `acceptance_criteria`, logs `WO_QUALITY_GATE`. **HANDOFF-16** (Session Host v2): passes WorkOrder instances through delegation -- wraps user turns, delegates to HO2. All three depend on WorkOrder being complete and stable.
