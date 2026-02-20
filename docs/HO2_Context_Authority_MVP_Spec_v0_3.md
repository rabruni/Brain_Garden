# HO2 Context Authority MVP — Spec v0.3 (Intent Included)
*Ledger‑Derived Context • Deterministic Liveness • Reachability • Scarcity Projection • Replay & Audit*

## TL;DR
You’re right: **Intent is foundational**. If you ship projection without an Intent model, you’ll end up baking “session = intent” assumptions into edges, conflicts, and closure semantics—hard to unwind later.

This v0.3 spec includes a **minimal, explicit Intent model now** (IDs, lifecycle, scope, supersession, conflict policy), while still allowing a **bridge mode** for early rollout:
- **Bridge mode**: auto-create an Intent per session (`INTENT_DECLARED`), but it is still a *real* Intent entity with lifecycle events.
- When you later introduce “true” intents (user-defined roots, forks), you won’t rewrite HO2—only how intents are declared.

This keeps MVP simple **without** creating future debt.

---

## 0) Non‑Negotiable Invariants
1. **Source ledgers are immutable** (append-only). Never rewrite historical entries.
2. **Lifecycle is explicit**: an obligation remains live until an explicit event exists: `CLOSED | RETIRED | SUPERSEDED | ABANDONED`.
3. **Suppression ≠ liveness**: suppression changes **visibility** only, never causal liveness.
4. **Deterministic replay**: same `(source ledgers + ruleset)` ⇒ identical eligibility + projection.
5. **Supersession is declared, not inferred** (no semantic guessing).
6. **All references are hash-stable**: `(ledger_id, entry_id, entry_hash)`.
7. **Eligibility and visibility are separate phases**:
   - Eligibility = HO2 authority decision (binary)
   - Visibility = budgeted projection (reversible)
8. **No silent intent drift**: changes in focus must produce explicit intent transitions (supersede/close/fork).

---

## 1) Scope (v0.3 MVP)
### Included
- Intent model (minimal but real)
- Work Orders (WO) model (minimal)
- Ordered lifecycle evaluation (“latest event wins”)
- Reachability graph from **active intent root** + **GLOBAL_ROOT**
- Projection under token budget with STUBs
- Conflict flags + default strict sequentiality
- CLI + tests + adversarial suite

### Deferred
- Semantic constraint refinement (subset reasoning)
- Auto-supersession from text meaning
- Multi-intent unions (beyond fork/branch semantics defined here)
- Long-term “hot/cold” archival tiers (classification only)

---

## 2) Why Intent Must Be Included Now (Design Risk)
If you postpone Intent:
- **Reachability degenerates** to “flat filter,” or hard-coded session groupings.
- **Conflict semantics** become arbitrary (“most recent wins”) and get relied on.
- **Supersession** becomes vague at the top level (WOs compete without a governing root).
- **Replay** becomes brittle because “current intent” becomes implicit.

So the MVP must include:
- Intent as a first-class entity
- Explicit lifecycle events for intent
- A deterministic “active intent selection” policy

---

## 3) Entities & Vocabulary (Minimal)
### 3.1 Source Reference Object (required)
```json
{
  "ref": {
    "ledger_id": "HO2_BASE",
    "entry_id": "E-2026-02-18-000123",
    "entry_hash": "sha256:..."
  }
}
```

### 3.2 Canonical hashing (required)
Define canonical serialization now:
- Canonical JSON: UTF‑8, sorted keys, no insignificant whitespace
- Hash covers: `entry_type`, `timestamp`, `entity_id`, typed payload
- Exclude signatures from hash input (or follow your existing kernel rule exactly)

---

## 4) Intent Model (Foundational, Minimal)
### 4.1 Intent definition
Intent is a **root obligation namespace** that anchors context.

#### Intent fields (minimum)
- `intent_id` (stable unique)
- `parent_intent_id` (optional; enables hierarchy)
- `root_intent_id` (optional; can be derived)
- `scope` enum: `GLOBAL | PROJECT | ARTIFACT | SESSION`
- `objective` (short string)
- `targets[]` (optional structured list; encouraged)
- `created_by` (actor)
- `status` derived by ordered lifecycle events

### 4.2 Intent lifecycle events (source ledger)
- `INTENT_DECLARED { intent_id, parent_intent_id?, scope, objective, targets[]? }`
- `INTENT_SUPERSEDED { intent_id, superseded_by_intent_id, reason }`
- `INTENT_CLOSED { intent_id, outcome, reason? }`
- `INTENT_ABANDONED { intent_id, reason }` (rare, explicit)
- `INTENT_FORKED { parent_intent_id, child_intent_ids[], reason }` (optional but recommended)

> **Rule:** Intent supersession/closure must be explicit. HO2 must never infer it from conversation.

### 4.3 Active intent selection policy (HO3 rule)
Default MVP: **Strict Sequentiality**
- If multiple ACTIVE intents exist with no explicit supersession relation:
  - HO2 emits `CONFLICT_FLAG: COMPETING_INTENTS`
  - HO2 blocks projection (no HO1 context) until resolved
- A dev-mode override may allow “most-recent-wins,” but must be an explicit config flag.

---

## 5) Work Orders (WO) — Minimal
### 5.1 WO lifecycle events (source ledger)
- `WO_OPENED { wo_id, intent_id, targets[], acceptance[] }`
- `WO_SUPERSEDED { wo_id, superseded_by_wo_id, reason }`
- `WO_CLOSED { wo_id, result: success|failed, evidence_refs[] }`
- `WO_ABANDONED { wo_id, reason }`
- `WO_DEFERRED { wo_id, reason }` (reachability-control)

### 5.2 Adapter mapping (if your system uses other labels)
Allowed deterministic mapping for MVP:
- `WO_PLANNED → WO_OPENED`
- `WO_COMPLETED → WO_CLOSED(result=success)`
- `WO_FAILED → WO_CLOSED(result=failed)`

Abandonment remains explicit.

---

## 6) Optional Entities (May be Stubs in MVP)
Constraints, dependencies, and errors can be included later as first-class entities.
For MVP, you may implement only:
- `WO_CLOSED(result=failed)` as the primary “error signal” for ordering
- A single GLOBAL invariant bundle from config (non-lifecycle)

---

## 7) Ordered Lifecycle Evaluation (“Latest Event Wins”)
### 7.1 Reducer rule
For each entity (`intent_id`, `wo_id`, etc.):
- Gather all lifecycle events for that entity
- Sort by `(timestamp, entry_id)` (tie-breaker)
- The **last** event determines current state

### 7.2 LIVE / NOT LIVE mapping
LIVE if latest event is one of:
- `*_DECLARED`, `*_OPENED`, `*_ASSERTED`, `*_RAISED`, `*_REOPENED`
- (Optionally) `*_DEFERRED` (still live)

NOT LIVE if latest event is one of:
- `*_CLOSED`, `*_RETIRED`, `*_SUPERSEDED`, `*_ABANDONED`

---

## 8) Reachability (Graph-Based Context)
### 8.1 Nodes
- Intent nodes
- WO nodes
- (Optional later) Dep, Error, Constraint nodes
- Virtual node: `GLOBAL_ROOT`

### 8.2 Edges (explicit only)
- `WO -> INTENT` via `intent_id`
- `INTENT -> PARENT_INTENT` via `parent_intent_id`
- GLOBAL invariants attach to `GLOBAL_ROOT`
- `GLOBAL_ROOT` is implicitly reachable from any active intent

### 8.3 Deferred handling (reachability-control, not liveness)
If entity latest event is `*_DEFERRED`:
- Remains LIVE
- Node is reachable but can be **projected as STUB-only**
- Traversal stops at that node if it has outgoing edges (future-proof)

---

## 9) Eligibility (Binary)
Eligibility is computed as:
```
ELIGIBLE = LIVE ∩ REACHABLE
```

Eligibility reasons (minimum set):
- `DEFINES_INTENT` (active intent + ancestors)
- `OPEN_WO`
- `GLOBAL_INVARIANT`
- `REACHABLE_FROM_INTENT`

No recency. No embeddings. No semantic relevance.

---

## 10) Projection Under Scarcity (Visibility)
### 10.1 Unsuppressible (must be visible)
MVP definition:
- Active intent header (always visible)
- Any WO that is a direct blocker (if you model blockers)
- Any failed WO (treat as error signal)

### 10.2 Ordering (deterministic)
Priority tiers:
1. active intent + ancestors (headers)
2. failed WOs
3. open WOs
4. deferred (STUB-only)
5. remaining

Stable sort within tier: `(timestamp, entry_id)`.

### 10.3 Output with STUBs
- Visible entries: compact typed payload + provenance ref
- Suppressed entries: STUB with provenance + suppression_reason
- Deferred entries: STUB unless budget allows FULL

---

## 11) HO2 Overlay Ledger (Immutable)
### 11.1 Required overlay event: PROJECTION_COMPUTED
Records the point-in-time projection artifact.
```json
{
  "overlay_type": "PROJECTION_COMPUTED",
  "timestamp": "2026-02-18T12:34:56Z",
  "intent_id": "INT-001",
  "turn_id": "T-000045",
  "token_budget": 2400,

  "eligible_refs": [ { "ref": { "...": "..." } } ],
  "visible_refs":  [ { "ref": { "...": "..." } } ],
  "suppressed_refs": [
    { "ref": { "...": "..." }, "reason": "BUDGET_EVICTION|LOW_URGENCY|DEFERRED" }
  ],

  "eligibility_reasons": {
    "E-...": ["OPEN_WO", "REACHABLE_FROM_INTENT"]
  },

  "flags": [
    { "kind": "COMPETING_INTENTS|INVALID_LIFECYCLE", "details_ref": { "ref": { "...": "..." } } }
  ],

  "ruleset_hash": "sha256:...",
  "proof_refs": [ { "ref": { "...": "..." } } ],
  "authority": { "tier": "HO2", "signer": "...", "sig": "..." }
}
```

### 11.2 CONFLICT_FLAG (recommended)
```json
{
  "overlay_type": "CONFLICT_FLAG",
  "timestamp": "...",
  "kind": "COMPETING_INTENTS|CONSTRAINT_CONFLICT",
  "intent_id": "INT-001",
  "involved_refs": [ { "ref": { "...": "..." } } ],
  "proof_refs": [ { "ref": { "...": "..." } } ],
  "ruleset_hash": "sha256:..."
}
```

> NOTE: Prefer lifecycle events in the *source* ledger. Only use overlay lifecycle events when you cannot change source emitters yet.

---

## 12) CLI (MVP)
Command:
```
python3 scripts/ho2_project_context.py --intent INT-001 --budget 2400
```

Flow:
1. Load source ledgers
2. Resolve active intent (strict sequentiality)
3. Reduce lifecycle state (latest-event-wins)
4. Build reachability graph (GLOBAL_ROOT)
5. Compute ELIGIBLE
6. Project visible/suppressed under budget
7. Append PROJECTION_COMPUTED
8. Print summary + overlay ref

Exit codes:
- 0 success
- 3 blocked by strict sequentiality conflict
- 4 invalid lifecycle detected

---

## 13) Implementation Order (Best Practice)
1. `liveness.py` (reducer) + tests
2. `intent_resolver.py` (conflict/strict sequentiality) + tests
3. `reachability.py` + tests
4. `projection.py` + tests
5. overlay writer + CLI
6. adversarial suite + metrics

---

## 14) Adversarial Test Suite (Must Pass)
- Competing active intents → projection blocked (strict sequentiality)
- Intent supersession chain → latest active chosen deterministically
- Zombie WO (no close) → remains eligible if reachable
- Silent supersession attempt → both remain live; conflict flagged if same slot policy exists
- Deferred WO → live, STUB-only, non-traversable
- Deterministic replay: sets+order identical across runs with same inputs

---

## 15) Definition of Done
- Intent model exists in source ledger (bridge mode allowed)
- HO2 computes and records PROJECTION_COMPUTED deterministically
- Conflicts are surfaced, not guessed
- Suppression never changes liveness
- Tests and adversarial suite pass

---

## 16) Bridge Mode (Safe Rollout)
Bridge mode is allowed and recommended for speed:
- On session start, HO2 appends `INTENT_DECLARED` with `scope=SESSION`.
- That intent is still a real entity and participates in lifecycle, reachability, replay.
- Later, “true” intents can be introduced without changing HO2 projection logic.

Bridge mode is safe because it does not collapse intent into an implicit concept; it merely automates declaration.

---

## 17) Intent Transition Implementation Pattern (Deterministic Hybrid)

*Added 2026-02-18 — explicit implementation guidance for intent ownership near classification.*

This uses a **hybrid model**:
1. **Agentic signal generation** in HO1 classify WO
2. **Deterministic intent state machine** in HO2 resolver

No always-running HO3/HO2 background agent is required.

### 17.1 Classify Output Contract (HO1)
Extend classify output schema to include:
- `speech_act`
- `ambiguity`
- `candidate_objective`
- `intent_relation` enum: `continue | switch | close | unclear`
- `confidence` (0..1)

HO1 suggests. HO2 decides.

### 17.2 Intent Resolver (HO2, Deterministic)
Add pure function:

`resolve_intent_transition(active_intent, classify_result, ruleset) -> TransitionDecision`

Properties:
- deterministic
- no LLM calls
- no randomness
- replay-safe with `ruleset_hash`

Recommended transition table:
- no active intent + relation != close -> `DECLARE`
- active intent + relation = continue -> `CONTINUE`
- active intent + relation = switch -> `SUPERSEDE + DECLARE`
- active intent + relation = close -> `CLOSE`
- relation = unclear -> policy-driven (`CONTINUE + CONFLICT_FLAG` by default)

### 17.3 Explicit Lifecycle Events (No Silent Inference)
Write only explicit intent lifecycle events:
- `INTENT_DECLARED`
- `INTENT_SUPERSEDED`
- `INTENT_CLOSED`
- optional `INTENT_CONFLICT_FLAG`

This preserves deterministic replay and auditability.

### 17.4 WO Planning Integration
After transition resolution, HO2 creates WOs tagged with `intent_id`.
- `intent_id` is control metadata for scope/continuity.
- WOs remain execution tasks, not intent authorities.

### 17.5 Post-Turn Intent Handling (HO2)
After Step 4 verification, HO2 may apply a second deterministic transition based on outcome/policy:
- normal success -> keep active intent
- repeated failure/escalation -> defer/flag
- explicit completion signal -> close intent

### 17.6 One-Active-Intent MVP Rule
MVP enforces one active intent per agent/session scope.
If multiple active intents are detected:
- emit deterministic conflict flag
- apply configured policy (`block` or `most_recent_wins`)

### 17.7 End-to-End Execution Flow
1. classify (HO1)
2. intent_transition (HO2 deterministic)
3. plan_wos(intent_id) (HO2)
4. execute (HO1)
5. verify (HO2)
6. optional post-turn intent_transition (HO2)

### 17.8 Rollout Strategy
1. Shadow mode first: compute + log intent decisions, no WO-routing effect.
2. Enable enforcement after replay/evals pass.

This keeps risk low while preserving deterministic semantics from day one.

---

## 18) Where Intent Lives: Classification as Intent Resolution

*Added 2026-02-18 — design analysis for intent placement in the Kitchener dispatch loop.*

### 18.1 Intent Is Not Classification — But They Happen Together

Classification answers: **"What type of message is this?"** (tool_query, greeting, information_request)

Intent answers: **"What is the user trying to accomplish, and is this the same goal as last turn?"**

These are two aspects of the same cognitive act — understanding the user. They should happen together at Step 2a, in the same LLM call, but they are different outputs.

Currently the classify contract returns:
```json
{"speech_act": "tool_query", "confidence": 0.9}
```

Extended to also return:
```json
{
  "speech_act": "tool_query",
  "intent": {
    "action": "continue",
    "scope": "exploring installed packages",
    "prior_intent_id": "INT-001"
  }
}
```

Where `action` is one of: `new`, `continue`, `supersede`, `close`.

The LLM does the semantic recognition ("is this the same goal or a new one?"). HO2 does the lifecycle bookkeeping (writing `INTENT_DECLARED`, `INTENT_SUPERSEDED`, `INTENT_CLOSED` to the ledger). Clean separation — cognition at HO1, governance at HO2.

### 18.2 The Intent-to-WO Relationship

Work orders are the execution units. An intent spawns work orders. The relationship is hierarchical:

```
Intent (goal-level, spans turns)
  "user wants to understand what frameworks are installed"
    │
    ├── Turn 1: "what frameworks are installed?"
    │     ├── Classify WO  → speech_act: tool_query, intent: new
    │     └── Synthesize WO → tools: list_packages → response
    │
    ├── Turn 2: "tell me more about FMWK-009"
    │     ├── Classify WO  → speech_act: tool_query, intent: continue
    │     └── Synthesize WO → tools: read_file → response
    │
    └── Turn 3: "thanks, now help me with something else"
          ├── Classify WO  → speech_act: greeting, intent: new (supersedes)
          └── ...
```

Intent is the **why**. WO is the **what**. The classify step recognizes the why, and WOs carry `intent_id` so every piece of execution traces back to the goal.

### 18.3 Why This Is Right for a Cognitive Companion

A cognitive companion needs theory of mind — it needs to model what the user is trying to do, not just react to each message in isolation. That means:

1. **It recognizes when you're still working on the same thing** — intent: continue. The Context Authority keeps that intent's full context reachable.

2. **It recognizes when you've moved on** — intent: supersede. The old intent's context becomes unreachable (but still live in the ledger — never deleted, just no longer projected).

3. **It recognizes when you're done** — intent: close. Explicit lifecycle termination, not inference.

4. **It surfaces when things pile up** — two active intents that neither supersede each other → CONFLICT_FLAG. The companion says "you seem to have two open threads, which should I focus on?" instead of silently mixing context.

The classify LLM call already has the user message + session history. It's the natural point where the system forms its understanding of intent. Adding intent recognition to that call costs zero additional LLM calls — just a richer output schema.

### 18.4 Implementation Concern: Classify Budget

The classify step currently has `turn_limit: 1` and a small budget. Intent recognition requires session context — "is this the same goal as the last 3 turns?" That means the classify prompt needs to include recent turn history (which it gets from `assembled_context` via attention/session_manager). This is already partially there — but the prompt pack (`PRM-CLASSIFY-001.txt`) would need to be updated to ask for intent assessment, and the contract schema would need the new fields.

That's not a blocker — it's just the scope of the change. Classification becomes "classify + intent resolve" in one step, one LLM call, richer output.

### 18.5 How H-29 (HO3 Signal Memory) Fits

H-29 and the Context Authority solve **different problems** that overlap at one point:

- **H-29** solves: "How does the system learn from recurring patterns across sessions?" Signal accumulation → bistable gate → consolidation → bias injection. It's a **learning loop**.

- **Context Authority** solves: "How does HO2 decide what context HO1 sees on each turn?" Liveness → reachability → eligibility → projection under budget. It's a **context computation engine**.

They overlap at **Step 2b** — both inject context into the synthesize WO. H-29 injects `ho3_biases` (learning-derived). The Context Authority injects the full projection (live + reachable + budget-constrained).

H-29's biases become **one input** to the Context Authority's projection:

```
Context Authority inputs:
  1. Source ledger entries (intents, WOs) → liveness + reachability
  2. HO3 overlays/biases from H-29 → eligible context items with their own priority tier
  3. HO3 ruleset (static config for MVP) → policy knobs for unsuppressible classes, budget allocation
```

The bistable gate + consolidation (29B/29C) continues to operate as the learning mechanism that *produces* overlays. The Context Authority *consumes* those overlays as part of its eligibility/projection computation.

H-29's `signals.jsonl` and `overlays.jsonl` remain as-is — they're the signal memory. The Context Authority adds a *new* overlay ledger for projection decisions (`PROJECTION_COMPUTED`), which is separate from HO3's consolidation overlays.

The wall-clock decay in `read_signals()` needs to be reconciled with the spec's deterministic replay requirement — either decay becomes a projection-time input (passed as a parameter, not computed from wall clock) or it stays in the learning path (H-29) but doesn't feed into the Context Authority's eligibility computation.

### 18.6 Summary

| Question | Answer |
|----------|--------|
| Where does intent happen? | Step 2a, as an extension of classify |
| Who recognizes intent? | HO1 (LLM) — same classify call, richer output |
| Who manages intent lifecycle? | HO2 — writes INTENT_DECLARED/SUPERSEDED/CLOSED based on classify output |
| How does intent relate to WOs? | Intent is parent. WOs carry intent_id. Multiple turns of WOs under one intent. |
| What consumes intent? | Context Authority — starts reachability graph from active intent_id |
| How does H-29 fit? | H-29 produces biases (learning). Context Authority consumes them as eligible context items in projection. |

---

## 19) H-29 Implementation Baseline and Relationship to Context Authority

*Added 2026-02-18 — grounding summary of what was implemented in the H-29 track and how it fits this spec.*

### What H-29 Implemented

#### 18.1 29A: HO3 memory store (new package)
`PKG-HO3-MEMORY-001` added `HO3Memory` with:
- append-only `signals.jsonl` + `overlays.jsonl`
- `log_signal`, `read_signals`, `log_overlay`, `read_active_biases`, `check_gate`

Reference:
- `Control_Plane_v2/_staging/PKG-HO3-MEMORY-001/HOT/kernel/ho3_memory.py:94`

#### 18.2 29B: HO2 wiring hooks (optional)
`HO2Supervisor` gained:
- optional HO3 fields (`ho3_enabled`, thresholds, etc.)
  - `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:77`
- bias injection into assembled context (`ho3_biases`)
  - `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:192`
- post-turn signal logging + gate checks, returning `consolidation_candidates`
  - `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:307`

#### 18.3 29C: consolidation plumbing + provider routing primitives
- `run_consolidation()` method added to HO2
  - `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:537`
- consolidation contract/prompt added to HO1
  - `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/consolidate.json`
  - `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-CONSOLIDATE-001.txt`
- HO1 tracks `tool_ids_used` and passes `domain_tags` to gateway
  - `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py:211`
  - `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py:383`
- Gateway supports domain-tag route resolution
  - `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py:219`

### Important Current Reality (Runtime Integration Gaps)

1. `HO3Memory` is not instantiated in ADMIN runtime path.
   - `build_session_host_v2()` creates HO2 without passing `ho3_memory` and without HO3 config wiring from `admin_config.json`.
   - References:
     - `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py:1259`
     - `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py:1293`

2. `run_consolidation()` is defined but not invoked in runtime flow.
   - Only definition + tests call it; no production caller currently.

3. Domain-tag routing exists but is effectively dormant in ADMIN path unless routes are wired/configured.
   - Gateway has the feature, but ADMIN build path does not populate route map in `RouterConfig`.

Conclusion:
- H-29 delivered core components and tests.
- End-to-end “always active” HO3 behavior is not fully wired by default in current ADMIN runtime.

### Relationship to HO2 Context Authority MVP

This spec is a different and larger context model:
- deterministic liveness + reachability
- `ELIGIBLE = LIVE ∩ REACHABLE`
- projection artifacts (`PROJECTION_COMPUTED`) in an HO2 overlay ledger

H-29 is signal-memory + bias overlay, not full Context Authority:
- tracks recurrence signals and consolidates overlays
- does not implement intent-rooted reachability/liveness projection

Therefore they are complementary:
1. H-29 provides HO3 memory primitives (signals, overlays, gate, optional biases).
2. Context Authority provides deterministic HO2 projection logic.
3. Best fit: Context Authority becomes primary Step-2b context engine; H-29 overlays can be one input signal source into that projection.

---

## 20) HANDOFF-29: What Was Built and How It Connects

*Added 2026-02-18 — detailed implementation record of H-29 (A/B/C) and gap mapping to Context Authority spec.*

### 20.1 29A — PKG-HO3-MEMORY-001 (new package, data store only)

- `ho3_memory.py`: Two ledger files — `signals.jsonl` (raw signal events) and `overlays.jsonl` (consolidated overlays)
- Two operations only: **LOG** (append signal/overlay) and **READ** (scan + aggregate on read)
- `SignalAccumulator`: Computed on read by grouping `signals.jsonl` by `signal_id` → count, session_ids, last_seen, decay
- `GateResult`: Bistable consolidation gate — 3 conditions (count ≥ N, sessions ≥ M, not already consolidated within window)
- Explicitly NOT a cognitive process. No LLM calls. Pure data plane.

### 20.2 29B — Wire HO3 into HO2 (modified PKG-HO2-SUPERVISOR-001)

- **Step 2b+**: After attention retrieval, `read_active_biases()` → injects `ho3_biases` into assembled_context for the synthesize WO. This is **Kitchener Step 1** (Ideation/bias injection).
- **Post-turn**: After user response delivered, extracts `intent:<speech_act>` signal from classify result, logs to HO3 via `log_signal()`, checks gate. If crossed → populates `consolidation_candidates` on TurnResult.
- All guarded by `if self._ho3_memory and self._config.ho3_enabled` — zero behavioral change when disabled.

### 20.3 29C — Consolidation Dispatch + Domain Routing (modified HO1, HO2, Gateway)

- `run_consolidation(signal_ids)`: Out-of-band, after user response. Re-checks gate (idempotent), creates consolidation WO, dispatches to HO1, on success writes overlay with `source_event_ids` back to HO3 `overlays.jsonl`. This is **Kitchener Step 5** (Synthesis/learning).
- `tool_ids_used` tracking in HO1 cost dict → HO2 extracts `tool:<tool_id>` signals
- Domain-tag provider routing in Gateway (3-step precedence: explicit > domain_tag > default)

### 20.4 How H-29 Maps to the Context Authority Spec

| Context Authority Concept | H-29 Implementation | Gap |
|---|---|---|
| **Source ledgers (immutable, append-only)** | `signals.jsonl` + `overlays.jsonl` — both append-only via LedgerClient | **Aligned.** Same invariant. |
| **Overlay ledger (derived decisions)** | `overlays.jsonl` already exists — stores consolidated biases with `source_event_ids` provenance | **Close, but different purpose.** `overlays.jsonl` stores consolidation outputs, not projection decisions. The spec's overlay stores `PROJECTION_COMPUTED` (what was visible/suppressed). |
| **Liveness (latest-event-wins)** | Not implemented. H-29 has no lifecycle events. Signals accumulate, overlays consolidate, but nothing is ever "closed" or "superseded". | **Full gap.** H-29 entities are immortal until decay zeroes them out. |
| **Reachability (graph from intent root)** | Not implemented. No graph. No intent node. Signals are flat — grouped by `signal_id`, no parent/child relationships. | **Full gap.** |
| **Eligibility = LIVE ∩ REACHABLE** | Not implemented. `read_active_biases()` returns all overlays with salience > 0. No eligibility computation. | **Full gap.** |
| **Projection under token budget** | Not implemented. All active biases injected — no budget-constrained visibility, no suppression, no STUBs. | **Full gap.** |
| **Intent as first-class entity** | Not implemented. Closest thing is `intent:<speech_act>` signal (e.g., "intent:tool_query"), but that's a classification label, not a persistent intent with lifecycle. | **Full gap.** |
| **Conflict detection** | Not implemented. No competing intents, no constraint conflicts. | **Full gap.** |
| **Deterministic replay** | Partially present. Gate check is a pure function of accumulated state + config. But `read_active_biases()` uses wall-clock decay, so results vary with time. | **Partial gap.** Decay breaks replay determinism. |
| **Bistable gate → consolidation** | Fully implemented. Gate crosses → `run_consolidation()` → LLM WO → overlay written. | **Aligned.** This is the signal-to-learning path that the spec doesn't explicitly cover (it's more about context projection than learning). |
| **HO3 as policy source** | Not implemented. H-29's HO3 is a data store. The spec's HO3 defines invariants, policy knobs, unsuppressible classes, budgets. | **Conceptual gap.** H-29 HO3 = memory. Spec HO3 = governance. |

### 20.5 The Key Tension

H-29 and the Context Authority spec are solving **different problems** that overlap at one point:

- **H-29** solves: "How does the system learn from recurring patterns across sessions?" Signal accumulation → bistable gate → consolidation → bias injection. It's a **learning loop**.
- **Context Authority** solves: "How does HO2 decide what context HO1 sees on each turn?" Liveness → reachability → eligibility → projection under budget. It's a **context computation engine**.

They overlap at **Step 2b** — both inject context into the synthesize WO. H-29 injects `ho3_biases` (learning-derived). The Context Authority would inject the full projection (live + reachable + budget-constrained).

### 20.6 How They Fit Together

H-29's biases become **one input** to the Context Authority's projection:

```
Context Authority inputs:
  1. Source ledger entries (WOs, constraints, deps, errors) → liveness + reachability
  2. HO3 overlays/biases from H-29 → treated as eligible context items with their own priority tier
  3. HO3 ruleset → policy knobs for unsuppressible classes, budget allocation
```

The bistable gate + consolidation (29B/29C) would continue to operate as the learning mechanism that *produces* overlays. The Context Authority would *consume* those overlays as part of its eligibility/projection computation.

H-29's `signals.jsonl` and `overlays.jsonl` would remain as-is — they're the signal memory. The Context Authority adds a *new* overlay ledger for projection decisions (`PROJECTION_COMPUTED`), which is separate from HO3's consolidation overlays.

The wall-clock decay in `read_signals()` would need to be reconciled with the spec's deterministic replay requirement — either decay becomes a projection-time input (passed as a parameter, not computed from wall clock) or it stays in the learning path (H-29) but doesn't feed into the Context Authority's eligibility computation.
