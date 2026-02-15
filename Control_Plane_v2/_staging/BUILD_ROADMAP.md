# BUILD ROADMAP: Bootstrap → Kitchener Cognitive Dispatch

**Status**: ACTIVE — build sequence reference
**Created**: 2026-02-14
**Design Authority**: `architecture/KERNEL_PHASE_2_v2.md` (Feb 14) — the ONLY source of design truth
**Process Standard**: `handoffs/BUILDER_HANDOFF_STANDARD.md` — how handoffs execute

---

## Preamble: What Already Exists

### Bootstrap State (17 packages, 8/8 gates)

The system boots. ADMIN reaches its `admin>` prompt via AnthropicProvider. The following infrastructure is installed and gate-verified:

| Layer | Packages | What They Provide |
|-------|----------|-------------------|
| 0 | PKG-GENESIS-000, PKG-KERNEL-001 | Bootstrap pre-seed, core kernel (auth, authz, hashing, merkle, ledger_client, paths, layout, pristine, provenance, packages, schema_validator, plane, registry, signing, preflight, package_audit, install_auth, tier_manifest) |
| 1 | PKG-REG-001, PKG-LAYOUT-001, PKG-LAYOUT-002 | Registry utilities (id_allocator, resolve), layout.json v1.0 → v1.1 |
| 2 | PKG-VOCABULARY-001, PKG-SPEC-CONFORMANCE-001, PKG-FRAMEWORK-WIRING-001 | Vocabulary, spec conformance, framework/spec/schema wiring (11 spec packs, 4 frameworks: FMWK-000 through FMWK-007, 7 schemas) |
| 3 | PKG-PROMPT-ROUTER-001, PKG-TOKEN-BUDGETER-001, PKG-ATTENTION-001, PKG-SESSION-HOST-001, PKG-ANTHROPIC-PROVIDER-001, PKG-PHASE2-SCHEMAS-001 | Prompt routing, token budgets, attention assembly, session loop, Anthropic SDK provider, Phase 2 schemas (prompt_contract, attention_template, ledger_entry_metadata) |
| 4 | PKG-ADMIN-001, PKG-BOOT-MATERIALIZE-001, PKG-GOVERNANCE-UPGRADE-001 | ADMIN CLI + config + attention template, boot materialization, governance upgrade |

### Key Interfaces Already Defined

These are the existing contracts. New packages consume or wrap them — they do NOT reimplement them.

| Interface | Package | Signature | Role in New System |
|-----------|---------|-----------|-------------------|
| `PromptRouter.route()` | PKG-PROMPT-ROUTER-001 | `route(PromptRequest) → PromptResponse` | Becomes LLM Gateway. HO1 calls this for all LLM invocations. |
| `LLMProvider.send()` | PKG-PROMPT-ROUTER-001 | `send(model_id, prompt, ...) → ProviderResponse` | Unchanged. Pluggable provider protocol. |
| `TokenBudgeter.allocate/check/debit()` | PKG-TOKEN-BUDGETER-001 | `allocate(BudgetScope, BudgetAllocation) → str` | Unchanged. Already supports session→WO→agent hierarchy. |
| `AttentionService.assemble()` | PKG-ATTENTION-001 | `assemble(AttentionRequest) → AssembledContext` | Code absorbed into HO2 Supervisor. Interface adapts. |
| `SessionHost.process_turn()` | PKG-SESSION-HOST-001 | `process_turn(user_message) → TurnResult` | Archived. Session lifecycle folds into HO2 Supervisor. |
| `ToolDispatcher.execute()` | PKG-SESSION-HOST-001 | `execute(tool_id, arguments) → ToolResult` | Reused by HO1 Executor for tool calls within WOs. |
| `LedgerClient` | PKG-KERNEL-001 | append-only JSONL with search | Unchanged. HO1 and HO2 both write via this. |
| `SchemaValidator` | PKG-KERNEL-001 | JSON Schema validation | Unchanged. Validates WOs, contracts, templates. |

### Existing Schemas

| Schema | Package | Used By |
|--------|---------|---------|
| `prompt_contract.schema.json` | PKG-PHASE2-SCHEMAS-001 | FMWK-011, HO1 Executor |
| `attention_template.schema.json` | PKG-PHASE2-SCHEMAS-001 | FMWK-010, HO2 Supervisor |
| `ledger_entry_metadata.schema.json` | PKG-PHASE2-SCHEMAS-001 | FMWK-008, HO1, HO2 |
| `work_order.schema.json` | PKG-FRAMEWORK-WIRING-001 | FMWK-008 extends this for cognitive dispatch |
| `router_config.schema.json` | PKG-PROMPT-ROUTER-001 | LLM Gateway config |
| `budget_config.schema.json` | PKG-TOKEN-BUDGETER-001 | Budget configuration |
| `admin_config.schema.json` | PKG-ADMIN-001 | ADMIN agent config |

---

## Code Absorption & Reuse Table

Every existing package has a disposition. Nothing is ambiguous.

| Package | Disposition | Detail |
|---------|-------------|--------|
| PKG-GENESIS-000 | **Unchanged** | Bootstrap pre-seed. No changes needed. |
| PKG-KERNEL-001 | **Unchanged** | Core infrastructure. All 23 modules stay. |
| PKG-PROMPT-ROUTER-001 | **Renamed** (HANDOFF-16B) | `prompt_router.py` → `llm_gateway.py`. Class renamed `PromptRouter` → `LLMGateway`. Backward-compat alias during transition. No functionality change. |
| PKG-ATTENTION-001 | **Archived** (Phase 0B) | Code absorbed into HO2 Supervisor. `attention_service.py` pipeline logic reused inside HO2's attention retrieval. `attention_stages.py` `ContextProvider` reused for ledger/registry/file reads. Package itself archived — not installed. |
| PKG-SESSION-HOST-001 | **Archived** (Phase 0B) | Replaced by HO2 Supervisor (session lifecycle) + thin Session Host v2 (turn wrapping). `tool_dispatch.py` `ToolDispatcher` class reused by HO1 Executor. Package itself archived — not installed. |
| PKG-TOKEN-BUDGETER-001 | **Unchanged** | Already supports session→WO→agent budget hierarchy. Wired into HO1 (per-WO debit) and HO2 (per-session allocation). |
| PKG-ANTHROPIC-PROVIDER-001 | **Unchanged** | Provider for LLM Gateway. No changes needed. |
| PKG-FRAMEWORK-WIRING-001 | **Unchanged** | Frameworks, specs, schemas. `work_order.schema.json` extended by FMWK-008. |
| PKG-PHASE2-SCHEMAS-001 | **Unchanged** | Provides `prompt_contract.schema.json`, `attention_template.schema.json`, `ledger_entry_metadata.schema.json`. Consumed by new packages. |
| PKG-REG-001 | **Unchanged** | Registry utilities. |
| PKG-VOCABULARY-001 | **Unchanged** | Vocabulary definitions. |
| PKG-SPEC-CONFORMANCE-001 | **Unchanged** | Spec conformance checks. |
| PKG-ADMIN-001 | **Rewired** (HANDOFF-17) | `main.py` will use new Shell (PKG-SHELL-001) which talks to HO2 Supervisor. Config and attention template stay. |
| PKG-LAYOUT-001 | **Unchanged** | Base layout. |
| PKG-LAYOUT-002 | **Unchanged** | Layout v1.1 update. |
| PKG-BOOT-MATERIALIZE-001 | **Unchanged** | Boot materialization. |
| PKG-GOVERNANCE-UPGRADE-001 | **Unchanged** | Governance upgrade. |

**Summary**: 13 unchanged, 1 renamed, 2 archived, 1 rewired.

---

## Deliverables Overview

6 phases. 12 deliverables. Phases 0-1 are governance/housekeeping. Phases 2-5 are code.

| Phase | ID | Deliverable | Pattern | Kitchener Role |
|-------|-----|-------------|---------|----------------|
| 0A | -- | FMWK-008A (Kitchener + metadata keys) | -- | Cross-cutting |
| 0B | -- | Archive PKG-ATTENTION-001 + PKG-SESSION-HOST-001 | -- | Cleanup |
| 0C | -- | Update READING_ORDER.md | -- | Cleanup |
| 1 | -- | FMWK-009 Tier Boundary | ACL + Capability | Cross-cutting |
| 1 | -- | FMWK-010 Cognitive Stack | Prototype / Factory | Cross-cutting |
| 1 | -- | FMWK-011 Prompt Contracts | Design by Contract | Step 3 |
| 2 | HANDOFF-13 | PKG-WORK-ORDER-001 | State Machine | Steps 2,3,4 data |
| 3 | HANDOFF-14 | PKG-HO1-EXECUTOR-001 | Command Executor | Step 3 |
| 3 | HANDOFF-15 | PKG-HO2-SUPERVISOR-001 | Mediator + Strategy | Steps 2,4 + session lifecycle |
| 4 | HANDOFF-16 | Session Host v2 Rewire | Adapter / Facade | Turn wrapping + degradation |
| 4 | HANDOFF-16B | LLM Gateway Rename | Rename Refactor | Infrastructure |
| 5 | HANDOFF-17 | PKG-SHELL-001 | Command Router | Human interface → HO2 |

---

## Phase 0: Housekeeping

### Phase 0A — FMWK-008A

- **Intent**: Align the Work Order Protocol with the Kitchener 5-step loop and establish the metadata key standard. This is the governance foundation — every WO, every ledger entry, every trace follows what FMWK-008 defines. Separate because governance standards must be locked before code is written against them.
- **Bounded Context**: Owns WO schema, WO lifecycle, ledger recording rules, metadata key standard. Does NOT own WO runtime code (that's PKG-WORK-ORDER-001) or prompt contracts (FMWK-011).
- **Kitchener Role**: Cross-cutting. Governs Steps 2 (HO2 creates WOs), 3 (HO1 executes WOs), and 4 (HO2 verifies WOs).
- **Pattern**: N/A (governance document, not code).
- **Interfaces**: N/A — defines schemas and rules consumed by all packages.
- **Files to Create/Modify**:
  - MODIFY: `_staging/FMWK-008_Work_Order_Protocol/work_order_protocol.md` — add Kitchener alignment, hash-anchored trace model, metadata key standard
  - CREATE: `_staging/FMWK-008_Work_Order_Protocol/manifest.yaml` — framework manifest (if not present)
- **Existing Code Reused**: Current FMWK-008 draft (Sections 1-10). `ledger_entry_metadata.schema.json` from PKG-PHASE2-SCHEMAS-001 (relational keys: `_parent_event_id`, `_root_event_id`, `_related_artifacts`).
- **Dependencies**: None. This is the root.
- **Acceptance Criteria**: DONE when the document defines: (a) how each Kitchener step maps to WO types, (b) the metadata key standard for relational/graph fields, (c) the hash-anchored trace model (governance ledger gets summaries + `trace_hash`, detail in trace files).
- **Failure Boundary**: N/A — governance document.

### Phase 0B — Archive PKG-ATTENTION-001 + PKG-SESSION-HOST-001

- **Intent**: Remove stale packages that will be replaced by HO2 Supervisor and Session Host v2. Prevents confusion — builders must not import from archived packages. Separate because archiving must happen before new packages reference the code they absorb.
- **Bounded Context**: Only touches package manifests and the archive. Does NOT delete source code (provenance). Marks packages as `ARCHIVED` in package state registry.
- **Kitchener Role**: Cleanup.
- **Pattern**: N/A (operational task).
- **Interfaces**: N/A.
- **Files to Create/Modify**:
  - MODIFY: `HOT/registries/packages_state.csv` — mark PKG-ATTENTION-001 and PKG-SESSION-HOST-001 as ARCHIVED
  - CREATE: `_staging/architecture/ARCHITECTURE_ARCHIVE_pre_v2.tar.gz` — already exists (verify it contains the archived packages)
- **Existing Code Reused**: N/A.
- **Dependencies**: None. Can run in parallel with Phase 0A.
- **Acceptance Criteria**: DONE when both packages are marked ARCHIVED in registry and cannot be installed by `package_install.py`.
- **Failure Boundary**: N/A.

### Phase 0C — Update READING_ORDER.md

- **Intent**: Bring the document index current with v2 architecture decisions. Stale index causes builders to read superseded docs as authority.
- **Bounded Context**: Owns document index and handoff registry. Does NOT own the documents themselves.
- **Kitchener Role**: Cleanup.
- **Pattern**: N/A.
- **Interfaces**: N/A.
- **Files to Create/Modify**:
  - MODIFY: `_staging/READING_ORDER.md` — add KERNEL_PHASE_2_v2.md as primary reference, mark superseded docs, add BUILD_ROADMAP.md, update critical path
  - MODIFY: `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` — correct the "HO3 does not exist" note (HO3 IS the correct name for the HOT tier per v2 Section 2)
- **Existing Code Reused**: N/A.
- **Dependencies**: Phase 0A (FMWK-008 must be updated first so READING_ORDER can reference the updated version).
- **Acceptance Criteria**: DONE when READING_ORDER.md reflects v2 as primary design authority and all document statuses are current.
- **Failure Boundary**: N/A.

---

## Phase 1: Governance Frameworks

Three frameworks that define the rules new packages must follow. No code packages — these are standards documents with schemas.

### FMWK-009 — Tier Boundary

- **Intent**: Formalize the visibility/syscall model. Without this, tier isolation is aspirational — any code can import any module. FMWK-009 makes "reading up = forbidden, calling through = allowed" enforceable. Separate because tier boundaries are orthogonal to cognitive dispatch — they apply to ALL code, not just the Kitchener loop.
- **Bounded Context**: Owns tier visibility rules, syscall definitions, import restrictions. Does NOT own budget enforcement (that's Token Budgeter + HO3 bookends, deferred) or auth/authz (existing PKG-KERNEL-001).
- **Kitchener Role**: Cross-cutting. Enforces invariant #1 (no direct LLM calls) and the visibility model from v2 Section 5.
- **Pattern**: ACL + Capability. Each tier has a capability ceiling. Syscalls are the only way to invoke higher-tier services.
- **Interfaces**: Defines the rules, not runtime APIs. Consumed by HANDOFF-14 (HO1 can only call LLM Gateway as syscall) and HANDOFF-15 (HO2 can read HO1m + HO2m, cannot read HO3m directly).
- **Files to Create**:
  - CREATE: `_staging/FMWK-009_Tier_Boundary/tier_boundary.md` — the standard
  - CREATE: `_staging/FMWK-009_Tier_Boundary/manifest.yaml` — framework manifest
- **Existing Code Reused**: `authz.py` role-based access (PKG-KERNEL-001). v2 Section 5 visibility table. v2 Section 12 capability model.
- **Dependencies**: FMWK-008 (metadata key standard defines how tier tags appear in ledger entries).
- **Acceptance Criteria**: DONE when the document specifies: (a) what each tier can see (v2 Section 5 table), (b) what constitutes a syscall vs. a forbidden read, (c) import restrictions per tier directory.
- **Failure Boundary**: N/A — governance document.

### FMWK-010 — Cognitive Stack

- **Intent**: Formalize invariant #7 — separate cognitive stacks per agent class. Without this, builders might create a single shared HO2 instance or conflate ADMIN and RESIDENT state. Separate because stack instantiation is the deployment model — it's about how many copies of HO2/HO1 exist, not what they do.
- **Bounded Context**: Owns stack instantiation rules, shared-vs-isolated boundary, session state structure. Does NOT own what HO2/HO1 do (that's HANDOFF-14/15) or how stacks communicate (FMWK-009).
- **Kitchener Role**: Cross-cutting. Defines how the Kitchener loop is instantiated per agent class.
- **Pattern**: Prototype / Factory. HO2 cognitive process is written once as generic code. Each agent class instantiates its own copy with different config (attention templates, framework config, WO context).
- **Interfaces**: Defines the rules. Consumed by HANDOFF-15 (HO2 Supervisor implements the factory pattern).
- **Files to Create**:
  - CREATE: `_staging/FMWK-010_Cognitive_Stack/cognitive_stack.md` — the standard
  - CREATE: `_staging/FMWK-010_Cognitive_Stack/manifest.yaml` — framework manifest
- **Existing Code Reused**: v2 Section 11 (shared code, isolated state). `attention_template.schema.json` from PKG-PHASE2-SCHEMAS-001 (per-agent templates).
- **Dependencies**: FMWK-009 (tier boundary rules constrain what a stack can access).
- **Acceptance Criteria**: DONE when the document specifies: (a) what's shared vs. isolated per v2 Section 11, (b) how a stack is instantiated (config + template + framework refs), (c) session state structure for HO2m.
- **Failure Boundary**: N/A — governance document.

### FMWK-011 — Prompt Contracts

- **Intent**: Formalize invariant #4 — communication is contractual. Without this, HO1 receives unstructured strings and returns unstructured strings. Contracts make every LLM exchange versioned, schema-validated, and auditable. Separate because contracts are the IPC protocol — they sit between HO2 (caller) and HO1 (executor), owned by neither.
- **Bounded Context**: Owns contract schema, contract lifecycle (versioning, validation rules), and the contract registry. Does NOT own specific contract instances (those ship with their consuming packages — classify.json with HANDOFF-14, etc.) or the runtime that loads them (HO1 Executor).
- **Kitchener Role**: Step 3 (Execution). Every HO1 LLM call loads a prompt contract.
- **Pattern**: Design by Contract. Pre-conditions (input_schema), post-conditions (output_schema), invariants (boundary constraints).
- **Interfaces**: Defines the contract format. Consumed by HANDOFF-14 (HO1 loads and validates against contracts).
- **Files to Create**:
  - CREATE: `_staging/FMWK-011_Prompt_Contracts/prompt_contracts.md` — the standard
  - CREATE: `_staging/FMWK-011_Prompt_Contracts/manifest.yaml` — framework manifest
- **Existing Code Reused**: `prompt_contract.schema.json` from PKG-PHASE2-SCHEMAS-001. `PromptRequest` dataclass fields (`contract_id`, `prompt_pack_id`) from PKG-PROMPT-ROUTER-001.
- **Dependencies**: None. Can be written in parallel with FMWK-009/010.
- **Acceptance Criteria**: DONE when the document specifies: (a) contract schema (extends `prompt_contract.schema.json`), (b) how contracts are loaded at runtime, (c) dual validation — syntactic (schema) then semantic (LLM output check), (d) versioning rules.
- **Failure Boundary**: N/A — governance document.

---

## Phase 2: The Atom

### HANDOFF-13 — PKG-WORK-ORDER-001

- **Intent**: The work order is the atomic unit of cognitive dispatch. HO2 creates them, HO1 executes them, HO2 verifies them. Without this package, there is no structured communication between tiers — just raw function calls. Separate because both HO2 and HO1 depend on the WO dataclass. If either package owned it, the other would have a circular dependency. WO is shared infrastructure.
- **Bounded Context**: Owns the `WorkOrder` dataclass, state machine (`planned→dispatched→executing→completed|failed`), WO validation, WO-specific ledger entry types. Does NOT own WO creation logic (HO2), WO execution logic (HO1), or budget allocation (Token Budgeter).
- **Kitchener Role**: Steps 2, 3, 4 data contract. The WO is what flows between HO2 and HO1 at every step.
- **Pattern**: State Machine. Terminal states are `completed` and `failed`. Forbidden transitions enforced (no regression, HO1 cannot create WOs).
- **Interfaces**:
  - IN: `WorkOrder.create(wo_type, session_id, input_context, constraints)` ← called by HO2
  - IN: `WorkOrder.transition(new_state)` ← called by HO2 (dispatch) or HO1 (executing/completed/failed)
  - OUT: `WorkOrder` instance with full state ← consumed by HO1 (execution) and HO2 (verification)
  - CALLS: `LedgerClient.append()` for state transition logging. `SchemaValidator.validate()` for WO validation.
- **Files to Create**:
  - CREATE: `_staging/PKG-WORK-ORDER-001/HOT/kernel/work_order.py` — `WorkOrder` dataclass, `WorkOrderStateMachine`, `WorkOrderValidator`
  - CREATE: `_staging/PKG-WORK-ORDER-001/HOT/kernel/wo_ledger.py` — WO-specific ledger entry types (`WO_PLANNED`, `WO_DISPATCHED`, `WO_EXECUTING`, `WO_COMPLETED`, `WO_FAILED`, `WO_CHAIN_COMPLETE`, `WO_QUALITY_GATE`)
  - CREATE: `_staging/PKG-WORK-ORDER-001/HOT/schemas/cognitive_work_order.schema.json` — JSON Schema for cognitive dispatch WOs (extends `work_order.schema.json`)
  - CREATE: `_staging/PKG-WORK-ORDER-001/HOT/tests/test_work_order.py` — unit tests
  - CREATE: `_staging/PKG-WORK-ORDER-001/manifest.json` — package manifest
- **Existing Code Reused**: `work_order.schema.json` from PKG-FRAMEWORK-WIRING-001 (base WO schema — extended, not replaced). `ledger_client.py` from PKG-KERNEL-001 (append API). `schema_validator.py` from PKG-KERNEL-001 (validation). `ledger_entry_metadata.schema.json` from PKG-PHASE2-SCHEMAS-001 (metadata key standard for relational fields).
- **Dependencies**: FMWK-008 (WO schema and lifecycle rules).
- **Acceptance Criteria**: DONE when `WorkOrder` can be created, transitioned through all valid states, validated against schema, and every transition produces a ledger entry with correct metadata keys.
- **Failure Boundary**: If `LedgerClient` is unavailable → WO transitions still occur in-memory but are not persisted. Logged as governance violation. If `SchemaValidator` is unavailable → WO validation is skipped with warning (fail-open for availability, logged).

---

## Phase 3: Cognitive Processes

Two packages, built in parallel. HO1 Executor and HO2 Supervisor. Together they implement Kitchener Steps 2→3→4.

### HANDOFF-14 — PKG-HO1-EXECUTOR-001

- **Intent**: HO1 is the single canonical execution point for all LLM calls in the system. Every LLM invocation — whether for user-facing responses, HO2's own planning decisions, or classification — flows through HO1. This is how invariant #1 (no direct LLM calls) and invariant #3 (agents don't remember, they READ) are enforced at the code level. Separate from HO2 because HO1 operates at a fundamentally different speed, model size, and token budget. HO1 is stateless and horizontally scalable. HO2 holds session state and is per-stack.
- **Bounded Context**: Owns WO execution, prompt contract loading, LLM Gateway invocation, tool loop (multi-round tool_use until text or budget), canonical trace writing to HO1m. Does NOT own WO creation (HO2), WO verification (HO2), attention/context assembly (HO2), or routing decisions (HO2).
- **Kitchener Role**: Step 3 (Execution). Receives dispatched WOs, executes them, returns results.
- **Pattern**: Command Executor. Each WO is a command. HO1 loads the appropriate prompt contract, assembles the LLM request, sends through Gateway, validates output, and returns.
- **Interfaces**:
  - IN: `HO1Executor.execute(work_order: WorkOrder) → WorkOrder` ← called by HO2 Supervisor
  - CALLS: `LLMGateway.route(PromptRequest) → PromptResponse` — for LLM calls (via syscall to HOT)
  - CALLS: `TokenBudgeter.debit(BudgetScope, TokenUsage) → DebitResult` — per-call budget debit
  - CALLS: `ToolDispatcher.execute(tool_id, arguments) → ToolResult` — for tool_call WO type
  - CALLS: `LedgerClient.append()` — writes to HO1m (canonical trace)
  - CALLS: `SchemaValidator.validate()` — validates output against prompt contract's `output_schema`
  - OUT: `WorkOrder` with `output_result` populated and state set to `completed` or `failed`
- **Files to Create**:
  - CREATE: `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` — `HO1Executor` class with `execute()` method, tool loop, contract loading
  - CREATE: `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/contract_loader.py` — loads and caches prompt contract JSON files, validates against `prompt_contract.schema.json`
  - CREATE: `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/classify.json` — minimum viable prompt contract for intent classification
  - CREATE: `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/synthesize.json` — minimum viable prompt contract for response synthesis
  - CREATE: `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/execute.json` — minimum viable prompt contract for general execution
  - CREATE: `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` — unit tests
  - CREATE: `_staging/PKG-HO1-EXECUTOR-001/manifest.json` — package manifest
- **Existing Code Reused**: `PromptRouter.route()` from PKG-PROMPT-ROUTER-001 (called as LLM Gateway). `ToolDispatcher` class from PKG-SESSION-HOST-001 `tool_dispatch.py` (reused for tool execution within WOs). `TokenBudgeter.debit()` from PKG-TOKEN-BUDGETER-001. `LedgerClient` from PKG-KERNEL-001. `prompt_contract.schema.json` from PKG-PHASE2-SCHEMAS-001.
- **Dependencies**: HANDOFF-13 (WorkOrder dataclass), FMWK-009 (tier boundary — HO1 can only call Gateway as syscall), FMWK-011 (prompt contract format).
- **Acceptance Criteria**: DONE when HO1Executor can receive a WorkOrder, load the corresponding prompt contract, make an LLM call through the Gateway, validate the output, debit the budget, write the canonical trace to HO1m, and return the completed WorkOrder. Multi-round tool loop works for tool_use responses.
- **Failure Boundary**: Gateway down → WO set to `failed`, error logged to HO1m. Contract missing → WO set to `failed` with `contract_not_found`. Budget exhausted → WO set to `failed` with `budget_exhausted`, partial cost logged. Output validation fails → WO set to `failed` with validation errors.

### HANDOFF-15 — PKG-HO2-SUPERVISOR-001

- **Intent**: HO2 is the deliberative supervisor — the brain of the Kitchener loop. It plans what work to do (Step 2), dispatches it to HO1 (Step 3 trigger), and verifies the results (Step 4). It also handles attention (context assembly), memory arbitration, and session lifecycle. Separate from HO1 because HO2 makes cognitive decisions (what to plan, what context to include, whether results pass quality gates) while HO1 just executes. Different responsibilities, different model requirements, different scaling characteristics.
- **Bounded Context**: Owns Kitchener Steps 2 and 4, attention retrieval (horizontal scan + priority probe), memory arbitration, WO chain orchestration, session lifecycle (session ID, start/end events, history), quality gating. Does NOT own WO execution (HO1), LLM call mechanics (LLM Gateway), token counting (Token Budgeter), or WO dataclass (PKG-WORK-ORDER-001). **Critical**: HO2 does NOT call LLM Gateway directly. All HO2 cognitive decisions (planning, verification) are dispatched as internal WOs to HO1.
- **Kitchener Role**: Steps 2 (Scoping) and 4 (Verification). Also triggers Step 3 by dispatching WOs to HO1.
- **Pattern**: Mediator + Strategy. HO2 mediates between user input and HO1 execution. Strategy pattern for attention retrieval (different templates per agent class) and arbitration (different strategies per context — offer-choice vs. auto-resume vs. escalate).
- **Interfaces**:
  - IN: `HO2Supervisor.handle_turn(user_message: str) → TurnResult` ← called by Session Host v2 / Shell
  - IN: `HO2Supervisor.start_session() → str` ← returns session_id
  - IN: `HO2Supervisor.end_session() → None`
  - CALLS: `HO1Executor.execute(WorkOrder) → WorkOrder` — dispatches all WOs (including HO2's own planning/verification)
  - CALLS: `WorkOrder.create()` — creates WOs for each step
  - CALLS: `TokenBudgeter.allocate()` — allocates per-WO budgets from session budget
  - CALLS: `TokenBudgeter.check()` — checks remaining budget before dispatch
  - CALLS: `LedgerClient.append()` — writes to HO2m (orchestration trace)
  - CALLS: `LedgerClient.search()` — reads HO1m (canonical traces) and HO2m (session state) for attention
  - OUT: `TurnResult` with user-facing response, WO chain summary, cost summary
- **Files to Create**:
  - CREATE: `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` — `HO2Supervisor` class with `handle_turn()`, `start_session()`, `end_session()`
  - CREATE: `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/attention.py` — `AttentionRetriever` with horizontal scan + priority probe, memory arbitration logic (absorbed from PKG-ATTENTION-001)
  - CREATE: `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/quality_gate.py` — `QualityGate` with verify logic (Step 4)
  - CREATE: `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/session_manager.py` — session lifecycle (start/end, session ID generation, history tracking)
  - CREATE: `_staging/PKG-HO2-SUPERVISOR-001/HO2/attention_templates/ATT-ADMIN-001.json` — minimum viable ADMIN attention template (uses `attention_template.schema.json`)
  - CREATE: `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` — unit tests
  - CREATE: `_staging/PKG-HO2-SUPERVISOR-001/manifest.json` — package manifest
- **Existing Code Reused**: `AttentionService` pipeline logic from PKG-ATTENTION-001 `attention_service.py` (absorbed — horizontal scan, priority probe, budget tracking). `ContextProvider` from PKG-ATTENTION-001 `attention_stages.py` (ledger/registry/file reads). `SessionHost` session management patterns from PKG-SESSION-HOST-001 `session_host.py` (session ID format, history tracking). `attention_template.schema.json` from PKG-PHASE2-SCHEMAS-001. `ATT-ADMIN-001.json` template from PKG-ADMIN-001 (starting point for new template).
- **Dependencies**: HANDOFF-13 (WorkOrder dataclass), HANDOFF-14 (HO1 Executor — HO2 dispatches to HO1), FMWK-009 (tier boundary — HO2 can read HO1m + HO2m, cannot read HO3m directly), FMWK-010 (cognitive stack — instantiation pattern).
- **Acceptance Criteria**: DONE when HO2Supervisor can receive user input, plan a WO chain (classify → retrieve → synthesize), dispatch each WO to HO1 Executor, verify results against acceptance criteria, manage session lifecycle, and return a user-facing response. Attention retrieval assembles context from HO2m (horizontal scan) and HO3m (priority probe, initially empty). All orchestration decisions logged to HO2m.
- **Failure Boundary**: HO1 Executor down → degrade to direct LLM call through Gateway (backwards-compat with v1). Attention retrieval fails → empty context (fail-open with warning, not fail-closed — absence of context is safer than blocking the response). Budget insufficient for new WO → return degraded response explaining budget exhaustion. All failures logged to HO2m.

---

## Phase 4: Infrastructure Updates

### HANDOFF-16 — Session Host v2 Rewire

- **Intent**: The v1 Session Host was a flat loop — it handled attention, routing, tool dispatch, and session state all in one class. V2 replaces the inner loop with Kitchener dispatch through HO2. Session Host v2 is a thin adapter: it wraps user input as a turn, calls HO2 Supervisor, and returns the response. It also handles degradation fallback (if HO2 fails, fall back to direct LLM call). Separate because the shell/CLI layer should not know about Kitchener internals — Session Host v2 is the API boundary.
- **Bounded Context**: Owns turn wrapping, degradation fallback, and the API contract between Shell and HO2. Does NOT own session lifecycle (moved to HO2 Supervisor), attention (HO2), or WO orchestration (HO2).
- **Kitchener Role**: Not a Kitchener step. Infrastructure adapter between Shell and the Kitchener loop.
- **Pattern**: Adapter / Facade. Adapts the Shell's simple `process_turn(message)` interface to HO2 Supervisor's richer API.
- **Interfaces**:
  - IN: `SessionHostV2.process_turn(user_message: str) → TurnResult` ← called by Shell
  - IN: `SessionHostV2.start_session(agent_config: AgentConfig) → str`
  - IN: `SessionHostV2.end_session() → None`
  - CALLS: `HO2Supervisor.handle_turn(user_message) → TurnResult`
  - CALLS: `HO2Supervisor.start_session() → str`
  - CALLS: `LLMGateway.route(PromptRequest) → PromptResponse` — degradation fallback only
  - OUT: `TurnResult` — same interface as v1 for backward compatibility
- **Files to Create**:
  - CREATE: `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py` — `SessionHostV2` with thin delegation + degradation
  - CREATE: `_staging/PKG-SESSION-HOST-V2-001/HOT/tests/test_session_host_v2.py` — unit tests
  - CREATE: `_staging/PKG-SESSION-HOST-V2-001/manifest.json` — package manifest
- **Existing Code Reused**: `TurnResult` and `AgentConfig` dataclasses from PKG-SESSION-HOST-001 (interface compatibility). Degradation fallback pattern from v2 Section 1 (degrade to direct LLM call through Gateway).
- **Dependencies**: HANDOFF-14 (HO1 Executor), HANDOFF-15 (HO2 Supervisor).
- **Acceptance Criteria**: DONE when SessionHostV2 can delegate `process_turn()` to HO2 Supervisor and return the result. Degradation fallback activates when HO2 raises an unrecoverable error, falling back to a direct LLM call through LLM Gateway. Degradation events logged to HO1m.
- **Failure Boundary**: HO2 Supervisor down → degrade to direct LLM call through Gateway (v1-compatible behavior). LLM Gateway also down → return error response to Shell.

### HANDOFF-16B — LLM Gateway Rename

- **Intent**: Mechanical rename of `PromptRouter` → `LLMGateway` to match the v2 terminology. The routing intelligence was absorbed into HO2 — what remains is a deterministic pipe (Log→Send→Log→Count). The name should reflect the actual responsibility. Separate because this is a zero-functionality-change refactor that can be done independently.
- **Bounded Context**: Owns the rename of `prompt_router.py` → `llm_gateway.py` and `PromptRouter` class → `LLMGateway` class. Does NOT change any behavior, add any features, or modify any interfaces.
- **Kitchener Role**: Infrastructure. LLM Gateway is called by HO1 as a syscall.
- **Pattern**: Rename Refactor. Backward-compat alias (`PromptRouter = LLMGateway`) during transition period.
- **Interfaces**: Same as `PromptRouter.route()`. No interface changes.
- **Files to Create/Modify**:
  - CREATE: `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` — renamed copy of `prompt_router.py` with class renamed to `LLMGateway`. Includes `PromptRouter = LLMGateway` alias.
  - CREATE: `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` — renamed tests
  - CREATE: `_staging/PKG-LLM-GATEWAY-001/manifest.json` — package manifest (supersedes PKG-PROMPT-ROUTER-001)
- **Existing Code Reused**: Entire `prompt_router.py` from PKG-PROMPT-ROUTER-001 (copied and renamed, not rewritten).
- **Dependencies**: HANDOFF-14 (HO1 Executor — ensure it imports `LLMGateway` or the alias).
- **Acceptance Criteria**: DONE when `LLMGateway` class passes all existing `PromptRouter` tests under the new name. `PromptRouter` alias exists for backward compatibility.
- **Failure Boundary**: N/A — mechanical rename. If tests fail, the rename introduced a bug.

---

## Phase 5: Human Interface

### HANDOFF-17 — PKG-SHELL-001

- **Intent**: The shell is the human-facing command router. It replaces PKG-ADMIN-001's `main.py` direct-to-SessionHost wiring with a proper command parser that talks to HO2 Supervisor (through Session Host v2). Separate because the shell is a presentation concern — it handles input parsing, output formatting, command routing — none of which are cognitive. Changing how the user types commands should never require changing how HO2 plans work orders.
- **Bounded Context**: Owns command parsing, input/output formatting, REPL loop, agent selection (ADMIN vs. future RESIDENT). Does NOT own cognitive dispatch (HO2), LLM calls (HO1), session lifecycle (HO2 Supervisor), or turn processing (Session Host v2).
- **Kitchener Role**: Not a Kitchener step. Human interface that feeds into the loop.
- **Pattern**: Command Router. Parses user input, routes to appropriate handler (cognitive turn vs. admin command vs. system command).
- **Interfaces**:
  - IN: `Shell.run() → None` — starts REPL loop
  - IN: User input from stdin
  - CALLS: `SessionHostV2.process_turn(user_message) → TurnResult` — for cognitive turns
  - CALLS: `SessionHostV2.start_session(AgentConfig) → str` — on startup
  - CALLS: `SessionHostV2.end_session() → None` — on exit
  - OUT: Formatted response to stdout
- **Files to Create**:
  - CREATE: `_staging/PKG-SHELL-001/HOT/kernel/shell.py` — `Shell` class with REPL loop, command parsing, agent config loading
  - CREATE: `_staging/PKG-SHELL-001/HOT/tests/test_shell.py` — unit tests
  - CREATE: `_staging/PKG-SHELL-001/manifest.json` — package manifest
- **Existing Code Reused**: `main.py` from PKG-ADMIN-001 (REPL loop pattern, agent config loading). `AgentConfig` dataclass from PKG-SESSION-HOST-001.
- **Dependencies**: HANDOFF-16 (Session Host v2 — Shell calls SessionHostV2).
- **Acceptance Criteria**: DONE when Shell can start a session, accept user input, route it through SessionHostV2 to HO2, and display the response. Admin commands (e.g., `show frameworks`) are parsed and dispatched. Exit command ends session cleanly.
- **Failure Boundary**: Session Host v2 down → Shell displays error and exits. Invalid input → Shell displays help text, does not crash.

---

## Cross-Cutting Sections

### Token Budgeter Wiring

The Token Budgeter (PKG-TOKEN-BUDGETER-001) already supports the hierarchical budget model needed by the Kitchener loop. No new package needed — just correct wiring:

| Budget Level | Who Allocates | Who Debits | Existing API |
|-------------|--------------|-----------|-------------|
| Session | Session Host v2 at session start | N/A (ceiling, not consumed directly) | `TokenBudgeter.allocate(session_scope)` |
| Work Order | HO2 Supervisor at WO creation | HO1 Executor at each LLM call | `TokenBudgeter.allocate(wo_scope)` / `TokenBudgeter.debit(wo_scope, usage)` |
| Per-call | N/A | HO1 Executor after LLM response | `TokenBudgeter.debit()` with `TokenUsage` |

**Budget enforcement chain**: HO2 checks `TokenBudgeter.check()` before creating each WO. HO1 checks before each LLM call. If budget is exhausted mid-WO, HO1 fails the WO with `budget_exhausted`. If session budget cannot accommodate a new WO, HO2 returns a degraded response.

**HO3 budget enforcement** (deferred): When HO3 cognitive process is built, it will set per-session budget ceilings. Until then, budgets are configured per agent class in `AgentConfig`.

### Dependency Graph

```
Phase 0:
  FMWK-008 ────────────────────────────────────┐
  Archive (0B) ──── (independent)               │
                                                │
Phase 1:                                        │
  FMWK-009 ←── FMWK-008                        │
  FMWK-010 ←── FMWK-009                        │
  FMWK-011 ──── (independent)                  │
  READING_ORDER (0C) ←── FMWK-008              │
                                                │
Phase 2:                                        │
  HANDOFF-13 (WO) ←── FMWK-008 ────────────────┘

Phase 3:
  HANDOFF-14 (HO1) ←── H-13, FMWK-009, FMWK-011
  HANDOFF-15 (HO2) ←── H-13, H-14, FMWK-009, FMWK-010

Phase 4:
  HANDOFF-16  (SH-v2)  ←── H-14, H-15
  HANDOFF-16B (Gateway) ←── H-14

Phase 5:
  HANDOFF-17 (Shell) ←── H-16
```

**Parallelism opportunities**:
- Phase 0A + 0B can run in parallel
- FMWK-011 can run in parallel with FMWK-009/010
- HANDOFF-14 + HANDOFF-15 can run in parallel (both depend on H-13, but not on each other — HO2's dependency on HO1 is runtime, not build-time. Tests use MockProvider/mock HO1.)
- HANDOFF-16B can run in parallel with HANDOFF-16

### Undispositioned Handoffs (Deferred to Stage 2+)

These handoffs from the original build plan have not been assigned to this roadmap. They map to v2 concepts but require infrastructure that doesn't exist yet.

| Handoff | Original Scope | v2 Mapping | Why Deferred |
|---------|---------------|------------|-------------|
| HANDOFF-6 | Ledger Query API | KERNEL.semantic meta agent cross-tier reads | Requires meta learning ledger + graph indexing. No consumer until HO3 cognitive process exists. |
| HANDOFF-7 | Signal Detector | Meta/Cross-cutting Learning (v2 Section 9) | Requires operational data from running Kitchener loops. Can't detect patterns without patterns to detect. |
| HANDOFF-8 | Learning Loops | Three-timescale learning model (v2 Section 9) | Operational learning is built into HO2 (HANDOFF-15). Meta and Core learning require Stage 2+ infrastructure. |

**Decision**: These handoffs are NOT dead — they represent real v2 capabilities. They are deferred because they require a running Kitchener loop (Stage 1 output) to have meaning. Revisit after HANDOFF-17 is validated.

---

## TDD Test Results

### Test Suite 1: Completeness — Every v2 Component Has a Deliverable

| v2 Component | v2 Section | Roadmap Deliverable | Status |
|---|---|---|---|
| Kitchener Step 2 (Scoping) | S1 | HANDOFF-15: HO2 Supervisor | PASS |
| Kitchener Step 3 (Execution) | S1 | HANDOFF-14: HO1 Executor | PASS |
| Kitchener Step 4 (Verification) | S1 | HANDOFF-15: HO2 Supervisor | PASS |
| Steps 1+5 (HO3 bookends) | S1 | Explicitly deferred | PASS |
| Degradation to direct LLM | S1 | HANDOFF-16: Session Host v2 | PASS |
| HO1 cognitive process | S3 | HANDOFF-14 | PASS |
| HO2 cognitive process | S3 | HANDOFF-15 | PASS |
| HO3 cognitive process | S3 | Deferred | PASS |
| LLM Gateway | S8 | HANDOFF-16B | PASS |
| Token Budgeter | S8 | Exists, wiring in cross-cutting section | PASS |
| Cross-cutting Meta Agent | S8 | Deferred (Stage 2+) | PASS |
| Work Order schema | S17 | HANDOFF-13 | PASS |
| Attention (horizontal scan) | S7 | Inside HANDOFF-15 | PASS |
| Attention (priority probe) | S7 | Inside HANDOFF-15 | PASS |
| Memory arbitration | S7 | Inside HANDOFF-15 | PASS |
| Prompt contracts | S12/S13 | FMWK-011 | PASS |
| Dual validation | S13 | FMWK-011 + HO2 verify | PASS |
| Cognitive stack instantiation | S11 | FMWK-010 | PASS |
| Visibility/syscall model | S5 | FMWK-009 | PASS |
| HO1m ledger | S6 | HO1 writes via ledger_client | PASS |
| HO2m ledger | S6 | HO2 writes via ledger_client | PASS |
| HO3m ledger | S6 | Deferred (HO3 bookends) | PASS |
| Meta Learning Ledger | S6 | Deferred (Stage 2+) | PASS |
| Session Host | S18 | HANDOFF-16 | PASS |
| Shell UX | S18 | HANDOFF-17 | PASS |
| Operational Learning | S9 | Built into HO2 (HANDOFF-15) | PASS |

**Result: 26/26 PASS.** Every v2 component maps to a deliverable or is explicitly deferred.

### Test Suite 2: Invariant Coverage

| # | Invariant | Enforced By | Status |
|---|---|---|---|
| 1 | No direct LLM calls | HO1 calls Gateway only; FMWK-009 forbids direct | PASS |
| 2 | Every agent under a WO | PKG-WORK-ORDER-001 + HO2 creates all WOs | PASS |
| 3 | Agents don't remember, they READ | HO2 reads ledgers; HO1 stateless | PASS |
| 4 | Communication is contractual | FMWK-011 + HO1 loads contracts | PASS |
| 5 | Budgets enforced not advisory | Token Budgeter wired into HO1+HO2 | PASS |
| 6 | Validation is structural | schema_validator reused; dual validation | PASS |
| 7 | Separate cognitive stacks | FMWK-010 defines instantiation | PASS |

**Result: 7/7 PASS.**

### Test Suite 3: Flow Trace — "hello" Through All Deliverables

```
User types "hello"
  → PKG-SHELL-001 (H-17) receives input, parses as cognitive turn
  → Session Host v2 (H-16) wraps as turn, calls HO2
  → HO2 Supervisor (H-15) receives
    → creates WO#1 classify via PKG-WORK-ORDER-001 (H-13)
    → dispatches to HO1 Executor (H-14)
      → loads prompt contract classify.json (FMWK-011)
      → calls LLM Gateway (H-16B) via PromptRequest
      → debits Token Budgeter (existing PKG-TOKEN-BUDGETER-001)
      → writes HO1m trace via LedgerClient (existing PKG-KERNEL-001)
      → returns completed WO#1
    → HO2 horizontal scan (HO2m) → creates WO#2 retrieve → HO1 → result
    → HO2 priority probe (HO3m) → creates WO#3 retrieve → HO1 → result
    → HO2 arbitrates: must-mention vs options, chooses strategy
    → creates WO#4 synthesize → HO1 → user-facing response
    → HO2 verifies result against acceptance criteria (Step 4) → approved
    → logs orchestration to HO2m via LedgerClient
  → Session Host v2 delivers TurnResult to Shell
  → Shell formats and prints to stdout → user sees response
```

**Result: 14/14 steps trace to a deliverable. PASS.**

### Test Suite 4: No Duplication — Single Owner Per Concern

| Concern | Single Owner | Status |
|---|---|---|
| Attention retrieval | HO2 only (PKG-ATTENTION-001 archived) | PASS |
| LLM routing decisions | HO2 only (Gateway is dumb pipe) | PASS |
| LLM call execution | LLM Gateway only | PASS |
| WO lifecycle | PKG-WORK-ORDER-001 only | PASS |
| Budget tracking | Token Budgeter only | PASS |
| Session lifecycle | HO2 Supervisor only | PASS |
| Ledger writes | ledger_client.py only | PASS |

**Result: 7/7 PASS.**

### Test Suite 5: Dependency Acyclicity

```
FMWK-008 → (none)
FMWK-009 → FMWK-008
FMWK-010 → FMWK-009
FMWK-011 → (none)
H-13     → FMWK-008
H-14     → H-13, FMWK-009, FMWK-011
H-15     → H-13, H-14, FMWK-009, FMWK-010
H-16     → H-14, H-15
H-16B    → H-14
H-17     → H-16
```

**Result: PASS. No cycles.** H-15 depends on H-14 at build time (for testing), but this is a unidirectional dependency. At runtime, HO2 calls HO1 — never the reverse.

### Test Suite 6: Failure Boundaries

| Deliverable | Failure Specified? | Status |
|---|---|---|
| HO1 Executor | Gateway down → WO fails. Contract missing → WO fails. Budget gone → WO fails. | PASS |
| HO2 Supervisor | HO1 down → degrade to direct LLM. Attention fails → empty context. | PASS |
| Session Host v2 | HO2 down → fall back to direct LLM call. | PASS |
| Shell | Session Host down → error + exit. | PASS |
| LLM Gateway | Provider down → circuit breaker (already exists in PromptRouter). | PASS |

**Result: 5/5 PASS.**

### Overall Score

```
Completeness:    26/26 PASS
Invariants:       7/7  PASS
Flow Trace:      14/14 PASS
No Duplication:   7/7  PASS
Acyclicity:       1/1  PASS
Failure Bounds:   5/5  PASS
                 ─────────────
Total:           60/60 PASS, 4 gaps identified (2 MEDIUM, 2 LOW)
```

---

## Gap Dispositions

| # | Gap | Severity | Description | Disposition |
|---|------|----------|-------------|-------------|
| G1 | HO3m content | MEDIUM | HO2's priority probe reads HO3m for "north stars" and "salience anchors." No deliverable populates HO3m with queryable content. | **DEFER**. HO3m content emerges from user/agent interaction through meta/learning loops. V1 escape hatch: if priority probe finds nothing, return empty — HO2 proceeds with horizontal scan only. Ask user explicitly if anchors are needed. |
| G2 | Attention templates | LOW | FMWK-010 says templates are per-agent config. No deliverable creates the actual templates. | **SUB-TASK of HANDOFF-15**. HO2 Supervisor ships with minimum viable `ATT-ADMIN-001.json` using `attention_template.schema.json` from PKG-PHASE2-SCHEMAS-001. |
| G3 | Prompt contracts | LOW | FMWK-011 defines the protocol. No deliverable creates the actual contract files. | **SUB-TASK of HANDOFF-14**. HO1 Executor ships with minimum viable contracts: `classify.json`, `synthesize.json`, `execute.json`. Uses `prompt_contract.schema.json` from PKG-PHASE2-SCHEMAS-001. |
| G4 | HO2's own thinking | MEDIUM | HO2 needs to make cognitive decisions. Does it call LLM Gateway directly or dispatch WOs to HO1? | **RESOLVED: HO2 dispatches to HO1.** All LLM calls go through HO1, including HO2's own planning and verification. Keeps HO1 as single canonical trace point. Enforces invariant #1. HO2 creates internal WOs (`classify intent`, `verify output`) and dispatches them to HO1 like any other WO. |

---

## Standards Compliance

Every deliverable in this roadmap follows the established pipeline:

1. **Frameworks** define governance standards (FMWK-008 through FMWK-011)
2. **Packages** implement code against those frameworks (HANDOFF-13 through HANDOFF-17)
3. Built and tested in `_staging/`
4. Clean room verification: extract `CP_BOOTSTRAP.tar.gz` → install Layers 0-2 → install new packages → all gates pass
5. Package system: `manifest.json`, SHA256, `tar.gz`, declared dependencies
6. Handoff standard: 10-question gate, DTT (Design→Test→Then implement), results file, full regression
7. **One package per handoff — never bundled**

---

## Authority

### Design Authority (one source of truth)

- `Control_Plane_v2/_staging/architecture/KERNEL_PHASE_2_v2.md` — ALL design decisions derived from this document

### Implementation References (existing code — targets, not authority)

| File | Package | Role in Roadmap |
|------|---------|----------------|
| `PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` | PKG-PROMPT-ROUTER-001 | Rename target → LLM Gateway (H-16B) |
| `PKG-ATTENTION-001/HOT/kernel/attention_service.py` | PKG-ATTENTION-001 | Absorption target → HO2 Supervisor (H-15) |
| `PKG-ATTENTION-001/HOT/kernel/attention_stages.py` | PKG-ATTENTION-001 | `ContextProvider` reused by HO2 |
| `PKG-SESSION-HOST-001/HOT/kernel/session_host.py` | PKG-SESSION-HOST-001 | Pattern reference for Session Host v2 (H-16) |
| `PKG-SESSION-HOST-001/HOT/kernel/tool_dispatch.py` | PKG-SESSION-HOST-001 | `ToolDispatcher` reused by HO1 Executor (H-14) |
| `PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | PKG-TOKEN-BUDGETER-001 | Wiring target — unchanged |

### Work in Progress (need updating to match v2)

| File | Issue |
|------|-------|
| `FMWK-008_Work_Order_Protocol/work_order_protocol.md` | Draft predates v2. Phase 0A updates it. |
| `READING_ORDER.md` | Stale index. Phase 0C rewrites it. |
| `handoffs/BUILDER_HANDOFF_STANDARD.md` | Contains "HO3 does not exist" note which contradicts v2. Phase 0C corrects it. |

### Process Standard

- `handoffs/BUILDER_HANDOFF_STANDARD.md` — 10-question gate format, DTT, results file format

---

## Final Verification Checklist

- [ ] Document compiles as valid markdown
- [ ] Every deliverable has all 10 fields (intent, bounded context, kitchener role, pattern, interfaces, files, existing code reused, dependencies, acceptance criteria, failure boundary)
- [ ] Dependency graph has no cycles
- [ ] Every existing package accounted for (13 unchanged, 1 renamed, 2 archived, 1 rewired)
- [ ] Cross-reference against v2 Section 18 critical path — nothing missing
- [ ] All 4 gap dispositions reflected in deliverable entries (G2 in H-15, G3 in H-14, G4 in H-15 bounded context)
- [ ] Code absorption table matches deliverable "Existing Code Reused" sections
- [ ] Flow trace hits every deliverable
- [ ] No deliverable bundles multiple packages
