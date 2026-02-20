# HO2 Context Authority MVP — Latest Spec (v0.2)
*Ledger‑Derived Context • Deterministic Liveness • Reachability • Scarcity Projection • Replay & Audit*

## TL;DR
This MVP adds a **new immutable HO2 Overlay Ledger** (“Context Authority Ledger”) that computes **deterministic, replayable context projections** from immutable source ledgers.

Key properties:
- **Context is derived, not stored**: `context = reachable ∩ live` (from the active intent root).
- **Supersession/closure is declared, not inferred**: no semantic guessing.
- **Suppression is visibility-only**: it never changes liveness.
- **Every decision is auditable & replayable**: `PROJECTION_COMPUTED` records *what/why* with stable references and a `ruleset_hash`.

This design aligns with current production agent best practices around **stateful orchestration, HITL checkpoints, tracing/observability, and eval-driven hardening**.

---

## 0) Non‑Negotiable Invariants
1. **Source ledgers are immutable** (append-only JSONL). Never rewrite historical entries.
2. **Eligibility termination is explicit**: an obligation remains live until an explicit lifecycle event exists: `CLOSED | RETIRED | SUPERSEDED | ABANDONED`.
3. **Suppression ≠ liveness**: suppression changes **visibility** only, not causal liveness.
4. **Deterministic replay**: same `(source ledgers + HO3 ruleset)` ⇒ identical eligibility + projection.
5. **No inference for supersession**: no semantic similarity, no “user moved on” logic.
6. **All references are hash-stable**: overlay entries point back to exact source entries by `(ledger_id, entry_id, entry_hash)`.

---

## 1) Scope (MVP)
### Included
- **HO2 Context Authority Ledger** (overlay, immutable)
- **Active intent resolution** (single active root for MVP; conflict surfaced)
- **Ordered lifecycle evaluation** (*latest-event-wins*) for liveness
- **Reachability graph** from intent root + **GLOBAL pseudo-root**
- **Projection under token budget** (visible vs suppressed) with **STUBs**
- **Conflict flags** (competing intents, invalid closures, constraint conflicts)
- CLI to compute projection + tests (incl. adversarial suite)

### Deferred (non-MVP)
- Semantic constraint refinement (subset reasoning)
- Auto-supersession from text meaning
- Multi-root intent unions
- Long-term “hot/cold” storage tiers (allowed only as *classification*, not lifecycle)

---

## 2) Architecture Overview
### Roles
- **HO1 (Execution / Working Field)**: consumes *visible* context; can request expansion. Never decides eligibility.
- **HO2 (Causal Authority)**: derives eligibility and constructs projections; writes overlay decisions.
- **HO3 (Governance)**: defines invariants and policy knobs (unsuppressible classes, conflict handling, budgets).
- **Meta (offline)**: learns from metrics/evals; proposes HO3 rule updates. Never injects live context.

### Key separation
- **Eligibility** (HO2, binary, auditable) → “May exist in context?”
- **Visibility** (HO2 projection, budgeted, reversible) → “Shown to HO1 this turn?”

---

## 3) Ledgers
### 3.1 Source ledgers (immutable)
Contain binding “speech acts” and lifecycle events:
- Intent, WO, Constraint, Dependency, Error, Resolution/Supersession/Abandonment.

**Admission rule (prevents “ledger-as-transcript”)**
Write only when an item becomes *binding*:
- Intent: when declared as active objective
- Work Order: when accepted
- Constraint: when binding
- Dependency: when it blocks something (not speculative)
- Error: when detected

### 3.2 HO2 Overlay Ledger (immutable)
Contains **derived authority artifacts**:
- `PROJECTION_COMPUTED` (required)
- `CONFLICT_FLAG` (recommended)
- Optional lifecycle overlays ONLY if source ledgers don’t carry them (prefer source).

Overlay ledger never “fixes history”; it records decisions with proofs and `ruleset_hash`.

---

## 4) Canonical Reference & Hashing
### 4.1 Source reference (required everywhere)
```json
{{
  "ref": {{
    "ledger_id": "HO2_BASE",
    "entry_id": "E-2026-02-18-000123",
    "entry_hash": "sha256:..."
  }}
}}
```

### 4.2 Canonical hashing (MVP requirement)
Define a canonical serialization before coding:
- **Canonical JSON**: UTF‑8, sorted keys, no insignificant whitespace
- Hash computed over the canonical JSON of the entry payload **excluding signatures**, but including:
  - `entry_type`, `timestamp`, `entity_id` (e.g., wo_id/dep_id), and typed fields.

> If your existing ledgers already define hashing, reuse that exact canonicalization.

---

## 5) Minimal Source Event Vocabulary (MVP)
> You can store these in the source ledger(s). Avoid overlay lifecycle events unless necessary.

### Intent
- `INTENT_DECLARED {{ intent_id, parent_intent_id?, scope, objective }}`
- `INTENT_SUPERSEDED {{ intent_id, superseded_by_intent_id }}`
- `INTENT_CLOSED {{ intent_id, outcome }}`

### Work Orders
- `WO_OPENED {{ wo_id, intent_id, targets[], acceptance[] }}`
- `WO_SUPERSEDED {{ wo_id, superseded_by_wo_id }}`
- `WO_CLOSED {{ wo_id, result, evidence_refs[] }}`
- `WO_DEFERRED {{ wo_id, reason }}` *(reachability-control; does not kill liveness)*

### Constraints
- `CONSTRAINT_ASSERTED {{ constraint_id, scope, intent_id?, text_hash, family? }}`
- `CONSTRAINT_RETIRED {{ constraint_id, reason }}`

### Dependencies
- `DEP_DECLARED {{ dep_id, intent_id, required_by_ref }}`
- `DEP_RESOLVED {{ dep_id, evidence_refs[] }}`
- `DEP_REOPENED {{ dep_id, reason, triggered_by_ref? }}`
- `DEP_DEFERRED {{ dep_id, reason }}` *(reachability-control)*

### Errors
- `ERROR_RAISED {{ error_id, intent_id, kind, evidence_refs[] }}`
- `ERROR_CLOSED {{ error_id, fix_refs[], verification_refs[] }}`
- `ERROR_REOPENED {{ error_id, reason }}` *(optional but supported)*

### Abandonment (explicit)
- `WO_ABANDONED {{ wo_id, reason }}`
- `DEP_ABANDONED {{ dep_id, reason }}`
- `INTENT_ABANDONED {{ intent_id, reason }}` *(optional)*

---

## 6) HO2 Overlay Event Types
### 6.1 PROJECTION_COMPUTED (required)
Records the computed view for a specific intent/turn/budget.
```json
{{
  "overlay_type": "PROJECTION_COMPUTED",
  "timestamp": "2026-02-18T12:34:56Z",
  "intent_id": "INT-001",
  "turn_id": "T-000045",
  "token_budget": 2400,

  "eligible_refs": [ {{ "ref": {{...}} }} ],
  "visible_refs":  [ {{ "ref": {{...}} }} ],
  "suppressed_refs": [
    {{ "ref": {{...}}, "reason": "BUDGET_EVICTION|LOW_URGENCY|FOLDED|DEFERRED" }}
  ],

  "eligibility_reasons": {{
    "E-...": ["OPEN_ERROR", "REACHABLE_FROM_INTENT"]
  }},

  "flags": [
    {{ "kind": "COMPETING_INTENTS|CONSTRAINT_CONFLICT|INVALID_LIFECYCLE", "details_ref": {{ "ref": {{...}} }} }}
  ],

  "ruleset_hash": "sha256:...",
  "proof_refs": [ {{ "ref": {{...}} }} ],
  "authority": {{ "tier": "HO2", "signer": "...", "sig": "..." }}
}}
```

### 6.2 CONFLICT_FLAG (recommended)
```json
{{
  "overlay_type": "CONFLICT_FLAG",
  "timestamp": "...",
  "kind": "COMPETING_INTENTS|CONSTRAINT_CONFLICT",
  "intent_id": "INT-001",
  "involved_refs": [ {{ "ref": {{...}} }} ],
  "proof_refs": [ {{ "ref": {{...}} }} ],
  "ruleset_hash": "sha256:..."
}}
```

---

## 7) Ordered Liveness (Load‑Bearing Rule)
### 7.1 “Latest event wins” reducer
For each entity (wo_id, dep_id, error_id, constraint_id, intent_id):
- Gather all lifecycle events for that entity.
- Sort by `(timestamp, entry_id)` to break ties deterministically.
- The **last event** determines current lifecycle state.

### 7.2 LIVE / NOT LIVE mapping (MVP)
LIVE if latest lifecycle event is one of:
- `*_DECLARED`, `*_OPENED`, `*_ASSERTED`, `*_RAISED`, `*_REOPENED`, `*_UNDEFERRED` (if you add it)

NOT LIVE if latest lifecycle event is one of:
- `*_CLOSED`, `*_RETIRED`, `*_SUPERSEDED`, `*_ABANDONED`

> This explicitly fixes the `DEP_RESOLVED → DEP_REOPENED` bug class.

### 7.3 Liveness categories (reasons)
A live entity is eligible only if it matches one of:
- `DEFINES_INTENT`
- `OPEN_WO`
- `ACTIVE_CONSTRAINT`
- `UNRESOLVED_DEP`
- `OPEN_ERROR`

---

## 8) Reachability (Graph‑Based Context)
### 8.1 Nodes
- Intent nodes, WO nodes, Dep nodes, Error nodes, Constraint nodes
- Add a virtual node: **GLOBAL_ROOT**

### 8.2 Edges (explicit only)
- `INTENT -> PARENT_INTENT` (via `parent_intent_id`)
- `WO -> INTENT` (via `intent_id`)
- `DEP -> required_by_ref` (explicit ref)
- `ERROR -> INTENT`
- `CONSTRAINT -> INTENT` if scoped, else `CONSTRAINT -> GLOBAL_ROOT` if `scope=GLOBAL`

### 8.3 Traversal rule
- Start from `current_intent_id` node.
- Also include `GLOBAL_ROOT` as implicitly reachable.
- Reachable set = BFS/DFS over edges, stable order.

### 8.4 DEFERRED affects reachability (not liveness)
If an entity’s latest lifecycle event is `*_DEFERRED`:
- The node remains LIVE
- Traversal **stops at that node** (do not traverse its outgoing edges)
- It may still appear as a **STUB** (policy-controlled) so HO1 knows it exists.

---

## 9) Eligibility
Eligibility is computed as:
```
ELIGIBLE = LIVE ∩ REACHABLE
```
Each eligible entry must be accompanied by:
- at least one liveness category reason
- `REACHABLE_FROM_INTENT` (or `GLOBAL_ROOT` reachability)

---

## 10) Projection Under Scarcity (Visibility)
### 10.1 Unsuppressible (must be visible)
- `OPEN_ERROR`
- `ACTIVE_CONSTRAINT`
- Any **blocker** of current intent:
  - a `DEP_DECLARED/DEP_REOPENED` that blocks a visible WO or current intent
  - or any entity explicitly marked “blocks” via required_by edges

### 10.2 Ordering (stable, deterministic)
Priority tiers:
1. blockers
2. errors
3. constraints
4. open work orders
5. unresolved deps
6. everything else

Within a tier:
- deterministic sort by `(timestamp, entry_id)`

### 10.3 Visibility assembly
- Add visible entries until token budget exhausted.
- Remaining eligible entries become suppressed STUBs with `suppression_reason`.

### 10.4 Dependency reopen promotion
If `DEP_REOPENED` occurs:
- Any WO that depends on that dep becomes a **blocker** for ordering in the next projection.

---

## 11) Formatting Contract (HO1‑Ready)
### FULL entry
- `entry_id`, `entry_type`, `entity_id`, `intent_id`, `status`
- compact typed payload (minimal fields)
- provenance `ref`
- `ruleset_hash`

### STUB entry (ultra‑compact)
- `entry_id`, `entry_type`, `entity_id`, `status`
- provenance `ref`
- `suppression_reason`
- optional `short_why` (one line; non-lossy, generated at write-time only)

**Rule:** HO1 must always see that a thing exists even if suppressed (no “unknown unknowns”).

---

## 12) Conflict Handling (Best‑Practice Default)
### MVP recommended policy: Strict Sequentiality
If multiple ACTIVE intents exist and none supersedes the other:
- Write `CONFLICT_FLAG: COMPETING_INTENTS`
- **Block projection** (return no HO1 bundle) until resolved
  - OR allow a HO3 override flag for “most-recent-wins” during dev

---

## 13) Observability & Evals (Production Agent Best Practices)
This spec bakes in modern agent ops best practices:
- **Tracing / step logs**: every projection is an artifact (`PROJECTION_COMPUTED`) for audit and debugging.
- **Eval-driven hardening**: adversarial cases become permanent tests and eval datasets.
- **Human-in-the-loop checkpoints**: conflict blocking and “expand stub” requests provide safe pause/resume semantics common in stateful agent runtimes.
- **Schema-first tool contracts**: strict typed events + compact payloads prevent malformed agent outputs from corrupting the ledger.
- **Ruleset versioning** via `ruleset_hash`: enables safe policy evolution and historical replay.

---

## 14) CLI (MVP)
Command:
```
python3 scripts/ho2_project_context.py --intent INT-001 --budget 2400
```

Behavior:
1. Load source ledgers
2. Resolve current intent
3. Reduce lifecycle state (latest-event-wins)
4. Build reachability graph (GLOBAL_ROOT)
5. Compute ELIGIBLE = LIVE ∩ REACHABLE
6. Project visible/suppressed under budget
7. Append `PROJECTION_COMPUTED` to overlay ledger
8. Emit summary + overlay ref

Exit codes:
- `0` success
- `2` conflict flagged (if non-blocking policy)
- `3` projection blocked by strict sequentiality
- `4` invalid lifecycle detected

---

## 15) Implementation Plan (Recommended Order)
1. `liveness.py` + `test_liveness.py` (ordered reducer + reopen/defer)
2. `reachability.py` + tests (GLOBAL_ROOT + deferred stop)
3. `projection.py` + tests (unsuppressible + ordering + budget)
4. overlay writer (append-only) + CLI
5. adversarial suite

---

## 16) Adversarial Test Suite (Must Pass)
- Zombie WO: no close event ⇒ stays live
- Silent supersession attempt: new WO without explicit supersession ⇒ both live; conflict surfaced
- Contradiction burying: open error always visible
- Cross-intent leakage: scoped constraints don’t leak
- Dependency reopen: resolved then reopened ⇒ live again + blocker promotion
- Deferred: live but non-traversable unless reactivated
- Competing intents: strict sequentiality blocks projection (or flags deterministically)

---

## 17) Suggested File Layout
```
lib/ho2_context/
  schema.py
  canonical_hash.py
  index.py
  liveness.py
  reachability.py
  projection.py
  formatter.py
  overlay_writer.py
scripts/
  ho2_project_context.py
tests/
  test_liveness.py
  test_reachability.py
  test_projection.py
  test_adversarial.py
```

---

## 18) Definition of Done (MVP)
- Projections are computed and written as overlay entries
- Replay determinism holds
- Suppression never changes liveness
- Reopen and deferred semantics are correct
- Conflict handling policy enforced
- Adversarial tests pass

---

## 19) Sources (for best‑practice alignment)
This spec aligns with widely adopted production patterns:
- Eval-driven development and production evaluation flywheels
- Tracing/observability for agent steps
- Stateful agent orchestration with checkpointing / HITL
- Guardrails and policy versioning

(See accompanying chat citations.)

---

## 20) Integration Analysis: Current System vs. This Spec

*Added 2026-02-18 — grounding review against installed CP_2.1 system (22 packages, 649 tests, 8/8 gates).*

### 20.1 What Current Attention Does (Baseline)

Current attention lives in `PKG-HO2-SUPERVISOR-001/HO2/kernel/attention.py` and is called at **Step 2b** of the modified Kitchener loop in `ho2_supervisor.py`. It does two things:

1. Looks up an attention template (`ATT-ADMIN-001.json`) by agent class
2. Runs a priority probe (currently a stub — returns empty)

It returns a context bundle that gets injected into the synthesize WO's prompt via `{{attention_context}}` template variable. The entire module is ~100 lines. The priority probe is a placeholder that always returns `[]`.

### 20.2 How the Context Authority Replaces Attention

The Context Authority replaces both of those things with a fundamentally more capable system. The **projection output** IS the context bundle — but computed from ledger state via liveness reduction + reachability traversal + budget-constrained visibility, not from a static template lookup.

**The right architectural move:** Keep the call boundary (HO2 calls a module at Step 2b in the Kitchener loop), replace the implementation behind it. The interface would be roughly:

```
compute_projection(intent_id, turn_id, token_budget) -> ProjectionResult
```

Where `ProjectionResult` contains visible entries (FULL format) + suppressed entries (STUB format) + conflict flags.

HO2 doesn't need to know how liveness or reachability works internally. This makes the Context Authority:
- **Replaceable** — swap the module, keep the interface
- **Testable** — unit test liveness/reachability/projection independently
- **Evolvable** — upgrade internals without touching HO2 dispatch logic

### 20.3 Three Gaps Between Spec and Current System

#### Gap 1: Intent Does Not Exist Yet (CRITICAL)

This is the largest gap. The spec assumes a persistent `intent_id` that spans turns, with explicit lifecycle events (`INTENT_DECLARED → INTENT_SUPERSEDED → INTENT_CLOSED`). The current system dispatches **per-turn**. Sessions exist (with `SESSION_START` / `SESSION_END` events in `ho2m.jsonl`), but intents do not.

Everything in Sections 5–9 depends on intent as a first-class ledger entity:
- Reachability graph starts from `current_intent_id` (Section 8.3)
- WOs link to intents via `intent_id` field (Section 5)
- Constraints are scoped to intents (Section 5)
- Conflict detection looks for competing active intents (Section 12)

**Question:** Is session-as-intent sufficient for MVP? A session maps roughly to "user is working on X" — but sessions don't have explicit scope, objective, or supersession semantics. If intent is a first-class entity, it needs its own lifecycle events in the source ledgers, which means modifying packages that currently write to those ledgers (HO2, possibly HO1).

#### Gap 2: Event Vocabulary Mismatch (SIGNIFICANT)

The spec defines its own source event vocabulary (Section 5):
- `INTENT_DECLARED`, `INTENT_SUPERSEDED`, `INTENT_CLOSED`
- `WO_OPENED`, `WO_SUPERSEDED`, `WO_CLOSED`, `WO_DEFERRED`, `WO_ABANDONED`
- `CONSTRAINT_ASSERTED`, `CONSTRAINT_RETIRED`
- `DEP_DECLARED`, `DEP_RESOLVED`, `DEP_REOPENED`, `DEP_DEFERRED`
- `ERROR_RAISED`, `ERROR_CLOSED`, `ERROR_REOPENED`

The current system writes different events:
- `WO_PLANNED`, `WO_DISPATCHED`, `WO_COMPLETED`, `WO_FAILED` (in ho2m.jsonl)
- `EXCHANGE`, `DISPATCH`, `PROMPT_REJECTED`, `BUDGET_WARNING` (in governance.jsonl)
- `LLM_CALL`, `TOOL_CALL`, `WO_COMPLETED`, `WO_FAILED` (in ho1m.jsonl)
- `SESSION_START`, `SESSION_END`, `TURN_RECORDED` (in ho2m.jsonl)
- `SIGNAL_ACCUMULATED`, `SIGNAL_CONSOLIDATED` (in ho2m.jsonl, added by H-29)

These don't map 1:1. For example:
- `WO_PLANNED` ≈ `WO_OPENED` (close enough)
- `WO_COMPLETED` ≈ `WO_CLOSED` (close enough)
- `WO_FAILED` → no direct equivalent in spec — is it `WO_CLOSED` with `result=failed`? Or `WO_ABANDONED`?
- `CONSTRAINT_ASSERTED` → nothing in current system writes this. Constraints are static config.
- `DEP_DECLARED` → nothing in current system writes this. Dependencies are in package manifests, not ledgers.
- `ERROR_RAISED` → nothing in current system writes this as a tracked entity with lifecycle.
- `INTENT_*` → nothing. Intents don't exist.

**Question:** Does the Context Authority need an adapter layer that translates current events into spec vocabulary? Or should the source ledgers start writing the new vocabulary? The adapter approach is faster but carries translation debt. The vocabulary change is cleaner but touches multiple packages (HO2, HO1, Gateway).

#### Gap 3: Constraint/Dependency/Error Entity Model (SIGNIFICANT)

The spec assumes constraints, dependencies, and errors are tracked as **individual ledger entities** with their own IDs and lifecycle events:
- Constraints have `constraint_id`, `scope`, `family`, `text_hash` and can be `ASSERTED` → `RETIRED`
- Dependencies have `dep_id`, `required_by_ref` and can be `DECLARED` → `RESOLVED` → `REOPENED` → `DEFERRED`
- Errors have `error_id`, `evidence_refs` and can be `RAISED` → `CLOSED` → `REOPENED`

In the current system:
- **Constraints** live in `admin_config.json` as static configuration. They are not ledger entities. They don't have IDs, lifecycle, or explicit retirement.
- **Dependencies** live in `manifest.json` as package-level declarations. They are install-time, not runtime. They don't have IDs or lifecycle events.
- **Errors** are transient — `WO_FAILED` is written, but there's no `error_id`, no tracking of whether the error was resolved, and no reopening mechanism.

**Question:** Which of these entities need to become first-class ledger citizens for MVP? All three? Or can MVP operate with a reduced entity set (e.g., intents + WOs only, deferring constraints/deps/errors to post-MVP)?

### 20.4 Additional Concerns and Questions

#### C1: Overlay Ledger Filesystem Path

The spec is clear (Section 3.2): the overlay is a **new separate ledger**, not new event types in `ho2m.jsonl`. Source ledgers record what happened; the overlay records what was decided about context. This separation is load-bearing for deterministic replay — you replay source ledgers to recompute the overlay, so they can't be the same file.

Current HO2 ledger is at `HO2/ledger/ho2m.jsonl`. The overlay needs its own path. Candidates:
- `HO2/ledger/ho2_context_authority.jsonl`
- `HO2/ledger/ho2_overlay.jsonl`

**Question:** Which path? And does the existing "one ledger per tier" convention (ho2m.jsonl) need updating to acknowledge that a tier can have multiple ledger files (source + overlay)?

#### C2: Centralized Budget Source (REQUIREMENT)

Budgets are currently scattered across multiple locations:
- `HO2Config.synthesize_budget` (hardcoded in supervisor, was 4000, now 16000/100000)
- `admin_config.json` → `budget_config.synthesize_budget` (100000)
- Token budgeter's own scope/debit logic
- The projection budget in this spec (Section 10, CLI example uses `--budget 2400`)

**Requirement:** All budget values must be centralized in **one admin-editable source file** that the system reads at runtime. Admin should be able to change any budget (synthesize, projection, classify, total session) from a single location without touching code.

This means:
- The Context Authority's projection budget comes from this central file, not a hardcoded default
- HO2's synthesize budget reads from this central file, not `HO2Config`
- Token budgeter respects limits from this central file
- The file must be hot-reloadable or read-per-turn (not cached at boot and forgotten)

**Decision:** Per agent class. Each agent class config (e.g., `admin_config.json`) owns all budget values for that class. The existing `budget_config` section in `admin_config.json` is the right home — it just needs to be expanded to include projection budget and any other budget values currently hardcoded elsewhere. When RESIDENT is built, it gets its own config with its own budget section.

#### C3: HO3 Ruleset

Section 0.4 says "same `(source ledgers + HO3 ruleset)` ⇒ identical projection." The `ruleset_hash` appears in multiple event types. But HO3 as a cognitive process is not yet built — HO3 currently has signal accumulation/consolidation (H-29B/C) and bias injection, but no ruleset mechanism.

**Question:** For MVP, is the ruleset a static JSON file (like a config)? Or does it need to be a ledger-derived entity itself? Static config is simpler and sufficient for MVP. The `ruleset_hash` still works — it hashes the config file.

#### C4: GLOBAL_ROOT Semantics

Section 8.2 introduces a `GLOBAL_ROOT` virtual node for constraints with `scope=GLOBAL`. This means some constraints are always reachable regardless of current intent.

**Question:** In a multi-agent-class system (ADMIN, RESIDENT, future classes), is GLOBAL_ROOT shared across agent classes? Or per-class? The current architecture has separate stacks per agent class (invariant #7). A global constraint visible to all agent classes may violate that invariant.

#### C5: Admission Rule Enforcement

Section 3.1 defines an admission rule: "Write only when an item becomes binding." This is a governance decision about what gets written to source ledgers. Currently, HO2 writes events liberally (WO_PLANNED, WO_DISPATCHED, WO_QUALITY_GATE, TURN_RECORDED, etc.).

**Question:** Does this admission rule require changes to how HO2/HO1/Gateway write events? Or is it only for the NEW event types introduced by this spec? Retroactively applying the admission rule to existing events could break forensic tooling (H-30) that depends on the current event density.

#### C6: Deterministic Replay Scope

Section 0.4 guarantees deterministic replay. This requires that the projection function has no external dependencies — no clock reads, no random, no network calls.

**Question:** Does `timestamp` in `PROJECTION_COMPUTED` come from a wall clock (non-deterministic across replays) or from source ledger timestamps (deterministic)? If wall clock, replay would produce different timestamps but identical eligibility/visibility. Need to define what "identical" means — same eligible set + same visible set, or byte-identical overlay entries?

### 20.5 Landing Strategy Options

#### Option A: Foundation-First (Clean, Slower)

1. **H-31A**: Introduce intent as a first-class ledger entity. Add `INTENT_DECLARED`, `INTENT_CLOSED`, `INTENT_SUPERSEDED` to HO2's event vocabulary. Map session-start to intent-declared for ADMIN class.
2. **H-31B**: Build liveness reducer + reachability graph + projection (Sections 7–10). New package `PKG-HO2-CONTEXT-AUTHORITY-001` or integrated into PKG-HO2-SUPERVISOR-001.
3. **H-31C**: Wire projection into HO2 Step 2b, replacing `attention.py`. Overlay ledger writes.
4. **H-31D**: Adversarial test suite (Section 16).

Pro: Clean architecture, no translation debt.
Con: 4 handoffs before attention replacement is visible. Intent vocabulary change touches HO2.

#### Option B: MVP Bridge (Faster, Carries Debt)

1. Map `session_id → intent_id` (session is the intent for MVP)
2. Map `WO_PLANNED → WO_OPENED`, `WO_COMPLETED → WO_CLOSED`, `WO_FAILED → WO_CLOSED(result=failed)`
3. Skip constraints/deps/errors as ledger entities for MVP (they don't exist yet)
4. Build liveness + reachability + projection against translated events
5. Wire into Step 2b

Pro: One large handoff, visible change fast.
Con: Adapter layer becomes tech debt. Intent-as-session limits future multi-intent scenarios.

### 20.6 Recommendation

**Start with Gap 1 (Intent).** Everything else in the spec flows from intent as the root node. Without it, reachability has no starting point, conflict detection has nothing to compare, and projection has no scope boundary. Resolving whether intent is session-scoped or a new first-class entity is the load-bearing decision.

Once intent is resolved, the implementation order in Section 15 (liveness → reachability → projection → overlay → adversarial) is correct and well-sequenced.

---

## 21) Open Questions to Resolve Before Build Freeze

*Added 2026-02-18 — implementation gating questions to avoid scope creep and ambiguity.*

1. **Intent root for MVP:** Is `intent_id = session_id` acceptable as an explicit temporary bridge, or must `INTENT_DECLARED`/`INTENT_CLOSED` be introduced first as first-class source events?
2. **Event mapping authority:** Do we ship with a deterministic adapter from current events (`WO_PLANNED/WO_COMPLETED/WO_FAILED`, etc.) to Context Authority lifecycle vocabulary, or require producers to emit the new vocabulary directly?
3. **WO failure semantics:** In lifecycle reduction, does `WO_FAILED` map to `WO_CLOSED(result=failed)` or to an abandonment state? This affects liveness and replay behavior.
4. **MVP entity scope:** For first release, are constraints/dependencies/errors required as first-class lifecycle entities, or is MVP limited to intents + WOs with those classes deferred?
5. **Conflict policy default:** Should ADMIN default to `flag + continue` (non-blocking) while recording `CONFLICT_FLAG`, with strict blocking configurable per agent class?
6. **Replay determinism contract:** Is replay equality defined as (a) identical eligible/visible/suppressed sets and stable ordering, or (b) byte-identical overlay entries including timestamps/signatures?
7. **Overlay ledger path:** Confirm canonical path now (recommended: `HO2/ledger/ho2_context_authority.jsonl`) and codify that HO2 may own multiple ledger files (source + overlay).
8. **GLOBAL_ROOT scope:** Is `GLOBAL_ROOT` per agent class (recommended for isolation) or shared across classes?
9. **Ruleset source for MVP:** Is `ruleset_hash` derived from static config (recommended) until HO3 ruleset governance exists, with no synchronous HO3 cognition involved?
10. **Budget source of truth:** Confirm one runtime source file per agent class (`admin_config.json` budget section) for projection budget, synthesize budget, classify budget, and session budget.
11. **Budget mode interaction:** When budget mode is `warn` or `off`, should projection still enforce hard minimum visibility for unsuppressible classes (errors, active constraints, blockers)?
12. **Admission rule boundary:** Does “binding-only writes” apply only to newly introduced Context Authority entities/events, leaving existing forensic event density unchanged?
13. **Tie-breaker canonicalization:** For same-timestamp events, is `(timestamp, entry_id)` the universal tie-breaker across all source ledgers, and are entry IDs guaranteed globally unique per ledger?
14. **Suppressed STUB guarantees:** What is the minimum STUB payload required so HO1 can request deterministic expansion without ambiguity (`entry_id`, `entity_id`, `entry_type`, `status`, `ref`, `suppression_reason`)?
15. **Dependency blocker promotion:** Is blocker promotion from `DEP_REOPENED` one-hop only (direct required_by), or transitive through downstream WO/dependency chains?
16. **CLI contract stability:** Should `ho2_project_context.py` output schema be versioned from day one (e.g., `projection_schema_version`) to support replay tooling and future migrations?
17. **Integration cut line:** Is replacement of `attention.py` immediate in MVP, or should Context Authority run in shadow mode first (compute + log overlay, no control-plane effect) for one validation phase?
18. **Test gate policy:** Which adversarial tests are release blockers vs non-blocking diagnostics during MVP bridge mode?
