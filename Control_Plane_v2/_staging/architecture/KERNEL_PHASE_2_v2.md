# Kernel Phase 2 v2: The Cognitive Dispatch Model

**Status**: ACTIVE — authoritative design reference
**Created**: 2026-02-14
**Supersedes**: KERNEL_PHASE_2.md (Feb 10), ADMIN_DESIGN.md cognitive dispatch section (Feb 12)
**Sources**: KERNEL_PHASE_2.md, Cognitive Hierarchy GPT Discussion, Kitchener Orchestration Model, Feb 14 architecture session

---

## What We're Building

A cognitive operating system for AI agents. Not a chatbot — an arena where governed agents think, remember, and improve under structured oversight.

### How It Behaves

When a user speaks, their words enter a **three-tier thinking loop** inspired by Kitchener's model of hierarchical cognition:

**The Critic (HO2)** receives the input first. It doesn't answer — it *plans*. It scans recent memory for open threads, probes governance for commitments that matter right now, and decides what the worker needs to know. Then it writes a **work order** — a scoped, budgeted, time-limited instruction — and hands it down.

**The Worker (HO1)** executes. It loads a prompt contract, makes the LLM call through a deterministic gateway, and returns the result. It doesn't decide what to do or what matters. It does what it's told, traces everything it did, and hands back.

**The Critic (HO2)** verifies. Did the result meet the acceptance criteria from the plan? If yes, deliver. If no, retry with tighter constraints or escalate. Every decision — what was retrieved, what was excluded, why — is recorded.

Later, a **Strategist (HO3)** will bookend this loop: setting objectives before the Critic plans, and signing off after the Critic verifies. For now, we build the inner three steps.

### What Users Experience

**The user sees a conversation.** They say "hello" and get a response that remembers their daughter's dance recital is Saturday, offers to resume the closet design project, and feels natural. They don't see the four work orders, the memory arbitration, the attention scan, or the verification step. The governance is invisible.

**The admin sees the plumbing.** They can query any ledger, trace any decision, see why the system mentioned the dance recital instead of the control plane project, and audit every LLM call with its token cost.

**Nobody sees an unaccountable agent.** Every action is scoped by a work order, logged to an append-only ledger, validated against a prompt contract, and bounded by a token budget. The system doesn't hallucinate silently — the Critic catches it. The system doesn't drift — the frameworks constrain it. The system doesn't forget — it reads.

---

## 1. Grounding Model: The Kitchener Orchestration Stack

Cognitive dispatch in this system is inspired by Kitchener's model of hierarchical cognition, adapted for agentic systems:

| Level | Role | Function |
|---|---|---|
| **Level 3: Strategist** (Epistemic) | Governance & Goal Agents | Sets objectives, evaluates validity of underlying logic, ensures "why" of the mission is met |
| **Level 2: Critic** (Metacognition) | Monitoring Agents | Reviews Level 1 outputs for errors, logic gaps, hallucinations. Decides redo/accept/escalate |
| **Level 1: Workers** (Cognition) | Task Execution Agents | Processes raw data, generates outputs. Specialized per task. |

### The Canonical Dispatch Loop (5-step)

This is THE cognitive dispatch loop. All agent work follows this pattern:

```
Step 1: Ideation       (Level 3)  Sets objective + epistemic boundaries
Step 2: Scoping        (Level 2)  Translates goal → instructions + acceptance criteria
Step 3: Execution      (Level 1)  Performs task per Level 2 specifications
Step 4: Verification   (Level 2)  Checks output against Step 2 criteria
Step 5: Synthesis      (Level 3)  Final sign-off: does this answer the original prompt?
```

The flow is a **round trip**, not just top-down dispatch. Level 2 both scopes (step 2) and verifies (step 4). Level 3 both initiates (step 1) and signs off (step 5).

### Why This Model (from Kitchener rationale)

1. **Corrects hallucination gap.** Level 2 creates a feedback loop (Chain-of-Verification). Level 1 doesn't just produce — Level 2 evaluates.
2. **Manages ambiguity.** Level 3 acts as a "Truth & Logic" filter — can pause the system when information conflicts rather than letting Level 1 spin.
3. **Separation of concerns.** Different model sizes per level: smaller/cheaper/local for Level 1 (high volume, specific tasks), more capable for Level 2/3 (sophisticated evaluation).

### Mapping to Prior ADMIN_DESIGN.md 3-Step Model

The earlier 3-step model (HO2 plans → HO1 executes → HO2 quality-gates) is the inner loop of the 5-step:

| ADMIN_DESIGN 3-step | Modified Kitchener 5-step | Note |
|---|---|---|
| (implied) | Step 1: Ideation (HO3) | Was missing — HO3 bookend |
| HO2 plans | Step 2: Scoping (HO2) | Same |
| HO1 executes | Step 3: Execution (HO1) | Same |
| HO2 quality-gates | Step 4: Verification (HO2) | Same |
| (implied) | Step 5: Synthesis (HO3) | Was missing — HO3 bookend |

**Build approach**: Start with the inner 3 steps (2→3→4). Add HO3 bookends (steps 1 and 5) when HO3 cognitive process is built.

### Orchestration Modes

The 5-step loop is the default **pipeline** mode. Future modes (all deferred):

| Mode | How | When |
|---|---|---|
| **Pipeline** (v1) | Sequential: one WO at a time through HO1 | Current — starting point |
| **Parallel** | Multiple HO1 WOs execute concurrently | When independent sub-tasks identified |
| **Hierarchical** | HO2 decomposes into sub-HO2 sessions | Complex multi-domain work |

### Degradation Behavior

If the Kitchener loop fails (HO2 unavailable, budget exhausted, unrecoverable error):
- **Degrade to direct LLM call** through LLM Gateway (backwards compatible with Session Host v1)
- Log degradation event to HO1m
- No silent failure — degradation is always recorded

---

## 2. The Three-Tier Cognitive Hierarchy

Mapped to Kitchener:

| Tier | Kitchener Level | Cognitive Role | Biology |
|---|---|---|---|
| **HO3** (codebase: `HOT/`) | Level 3: Strategist | Policy, principles, north stars, identity, long-horizon constraints | Stable value priors, executive goal structures |
| **HO2** (codebase: `HO2/`) | Level 2: Critic | Deliberative supervisor. Plans, arbitrates, retrieves, dispatches, verifies | Prefrontal metacognition |
| **HO1** (codebase: `HO1/`) | Level 1: Workers | Reactive executor. All LLM calls. Produces traces. Stateless. | Sensorimotor execution |

### Naming Note

**HOT = HO-Three** (shorthand). The codebase uses `HOT/` — this IS the Level 3 tier. No rename needed. Both "HOT" and "HO3" refer to the same tier. Design docs may use either term interchangeably.

---

## 3. Three Things Per Tier

Each HO layer is three distinct concepts. Using the wrong one causes conflation.

| Concept | What it is | Naming Convention |
|---|---|---|
| **Memory / Store** | Ledger entries, policies, traces stored at that tier | **HO1m**, **HO2m**, **HO3m** (m suffix = memory) |
| **Cognitive Process** | The computational actor that operates at that tier | **HO1 cognitive process**, **HO2 cognitive process**, **HO3 cognitive process** |
| **Layout / Directory** | Filesystem path where governed files live | `HO1/`, `HO2/`, `HOT/` (codebase paths) |

### Cognitive Process Roles

| Tier | Role | Characteristics |
|---|---|---|
| HO1 cognitive process | Reactive executor | Fires LLM calls via LLM Gateway. Produces canonical traces. Stateless beyond work order. Supports multi-round tool loops (if LLM responds with tool_use, HO1 loops until text response or budget exhaustion). |
| HO2 cognitive process | Deliberative supervisor | Plans, arbitrates competing memories, dispatches WOs to HO1, verifies results. Session-scoped. Handles attention (retrieval + salience weighting). |
| HO3 cognitive process | Policy evaluator | Maintains principles. Evaluates alignment. Sets constraints that flow down. Slow, stable. |

---

## 4. Agent Classes

| Class | What it is | Nature |
|---|---|---|
| **KERNEL.syntactic** | Deterministic infrastructure. Gates, hashing, integrity, auth, LLM Gateway. | Not an agent. Code that enforces invariants. Binary outcomes. |
| **KERNEL.semantic** | Conceptual term for LLM-based kernel capabilities. Currently: cross-cutting meta/learning agents. Future: any LLM-backed kernel service. | Infrastructure that serves the system, not users. Counterpart to KERNEL.syntactic. |
| **ADMIN** | System keeper. Governed delegate of the human administrator. | Full read. Writes only through governed methods. Cannot interact with resident agents directly. Kernel-level observer. See capability matrix below. |
| **RESIDENT** | User-facing cognitive agent. Does "real work" from user's perspective. | Own namespace. Sees world through attention envelopes. Doesn't know it's governed. |

### ADMIN Capability Matrix (from ADMIN_DESIGN.md)

| Capability | Scope |
|---|---|
| **CAP_READ_ALL** | Read any tier's ledger, registry, manifest, governed file |
| **CAP_AUDIT_WRITE** | Write observations, recommendations to HO2m/HO3m |
| **L-OBSERVE** | Ledger query across all tiers |
| **L-ANNOTATE** | Add audit annotations to ledger entries |

**ADMIN cannot**: Modify kernel code. Modify BUILDER artifacts. Self-promote permissions. Interact with RESIDENT agents or their sub-sessions directly. All writes go through governed work orders.

### KERNEL.semantic — What It Contains

KERNEL.semantic is not a specific service list. It is the category of **LLM-backed kernel capabilities** — anything the kernel does that requires an LLM, as opposed to KERNEL.syntactic (everything deterministic).

Current contents:
- **Cross-cutting meta agent** (Global Workspace / Observer) — reads across all tier ledgers, detects patterns, writes to meta learning ledger
- **Operational learning functions** — HO2-level adjustments within work orders

Future (deferred):
- Core Learning (long-horizon pattern extraction) — Stage 3+ research
- Any additional LLM-backed kernel services identified during build

### What Was Removed From KERNEL.semantic

These were originally listed as KERNEL.semantic services. All have been resolved:

| Original Service | Resolution |
|---|---|
| Prompt Router | Routing intelligence → absorbed into HO2 cognitive process dispatch. Logging/provider/budget → renamed to **LLM Gateway** (KERNEL.syntactic). |
| Attention Service | Absorbed into HO2 cognitive process. Attention = HO2's retrieval + salience weighting function. |
| Flow Runner | Superseded by HO2 cognitive process. HO2 IS the orchestrator. |
| Core Learning | Deferred to Stage 3+. Research problem. |

---

## 5. The Visibility / Syscall Model

Lower tiers CANNOT read higher tier state. Lower tiers CAN call higher tier services (syscalls).

| Tier | Sees | Receives From Above | Calls (syscalls) |
|---|---|---|---|
| **HO3** | All: HO3m + HO2m + HO1m + Meta ledger | — | — |
| **HO2** | HO2m + HO1m | Constraints from HO3 (pushed down) | HO3 services (e.g., policy lookup) |
| **HO1** | Only its work order context | Instructions from HO2 (dispatched) | HOT infrastructure: LLM Gateway, provider, ledger client |

**Principle**: Reading up is forbidden. Calling through is allowed. HO1 never reads HO3 governance state directly, but HO1 calls the LLM Gateway (which lives in HOT/) as a syscall. The service serves the request without exposing tier state.

---

## 6. Memory Architecture

### Four Ledgers

| Ledger | Tier | Contents | Visibility |
|---|---|---|---|
| **HO1m** | HO1 | Canonical episodic trace. Every LLM call, every tool execution, every work order result. Ultimate record. | HO1 (own work), HO2, HO3 |
| **HO2m** | HO2 | Work order orchestration. Arbitration outcomes. Escalation events. Meta-episodes. Session state. | HO2, HO3 |
| **HO3m** | HO3 (HOT) | Governance decisions. Principles. North stars. Long-horizon commitments. Policy updates. | HO3 only (pushed down as constraints) |
| **Meta Learning Ledger** | Stored in HOT, cross-cutting | Graph-indexed patterns. Structural credit assignment. Cross-tier learning artifacts. | KERNEL.semantic (cross-cutting meta agent) |

### Memory Principles

- **Agents don't remember, they READ.** No internal state between sessions. All persistent state = ledger queries.
- **Ledger is system truth.** Written FIRST in commit phase. Registries are derived.
- **Append-only.** No mutation. No deletion. History preserved.
- **Meta ledger is graph-indexed.** Enables relationship-based retrieval (Graph RAG), not just keyword search. Preserves hierarchy of intent across HO1→HO2→HO3.

### Memory Store Mapping (from GPT Discussion)

| Store | What | Tier | Nature |
|---|---|---|---|
| M0 | Sensor buffer (raw incoming utterance) | Transient | Ephemeral |
| M1 | Working memory (HO2 active state for this turn) | HO2 | Session-scoped |
| M2 | Episodic trace (HO1 canonical record) | HO1m | Persistent, immutable |
| M3 | Policy / identity memory (principles, north stars) | HO3m | Persistent, slow-changing |
| M4 | Meta-learning artifacts (cross-tier patterns) | Meta ledger | Persistent, graph-indexed |

---

## 7. Attention — HO2's Retrieval Function

Attention is NOT a standalone service. It is what the HO2 cognitive process does to prepare HO1's context.

### Retrieval Operations (Current — v1)

| Operation | What | Source |
|---|---|---|
| **Horizontal scan** | Recency, open loops, active work, last threads | HO2m (session/episodic state) |
| **Priority probe** | Salience anchors, human commitments, time-sensitive items, principles | HO3m (policy/identity) |

### Context Management Operations (Future — deferred)

KP2 defined four attention operations. Two are addressed by retrieval above. Two remain as future HO2 capabilities:

| Operation | KP2 Definition | Status |
|---|---|---|
| **Filter** | Decides what's relevant. Everything else invisible. | Addressed by horizontal scan + priority probe |
| **Promote** | Something became relevant mid-task. Bring into context. | Addressed by HO2 re-evaluation between WO steps |
| **Evict** | Context full. Least relevant leaves. | **Deferred** — requires context budget tracking in HO2 |
| **Interrupt** | Urgent: bypasses normal filtering (gate failure, integrity violation, user escalation) | **Deferred** — requires event-driven signaling into HO2 |

These are not critical for the initial Kitchener loop but become essential at scale when context budgets are tight and real-time signals need to preempt normal flow.

### Memory Arbitration

When multiple memory candidates compete (e.g., "hello" triggers three possible topics), HO2 runs **memory arbitration**:

1. Retrieve candidates from horizontal scan + priority probe
2. Score by: human/commitment weight (HO3), time sensitivity, recency (HO2)
3. Classify: must-mention vs ranked options
4. Choose response strategy: offer choice vs auto-resume vs escalate
5. All arbitration outcomes logged to HO2m

### Context Budget and Truncation

If assembled context exceeds the token budget for an HO1 work order:
- **Truncation priority**: frameworks > conversation history > metadata
- **Fail-closed default**: when in doubt, **include rather than exclude**. Missing context causes worse failures than excess context.
- Budget tracked by Token Budgeter (KERNEL.syntactic), enforced by HO2 before dispatch

### Design Constraints (from prior art analysis)

1. **No hardcoding.** Every threshold, pattern, weight = config-driven. #1 lesson from locked system.
2. **Config-driven templates.** Attention templates (YAML/JSON) per agent type, validated by KERNEL.syntactic.
3. **Auditable.** What was retrieved, what was excluded, and why — all recorded.
4. **Tier-aware.** Different tiers have different search patterns.
5. **Fail-closed.** Include rather than exclude. Missing context > excess context.

---

## 8. Infrastructure Components

### KERNEL.syntactic (Deterministic)

| Component | What | Where |
|---|---|---|
| **LLM Gateway** (was: Prompt Router) | Deterministic pipe for all LLM calls. Log→Send→Log→Count tokens. Routes between multiple providers (Anthropic, OpenAI, local). No cognitive judgment. | `HOT/kernel/` |
| **Provider(s)** | Pluggable LLM provider implementations. AnthropicProvider exists. | `HOT/kernel/` |
| **Gate Operations** | CRUD with auth enforcement. ID allocation by prefix. | `HOT/kernel/` |
| **Integrity / Merkle** | Hash verification, Merkle trees, file integrity. | `HOT/kernel/` |
| **Ledger Client** | Append-only event logging. Hash-chained entries. | `HOT/kernel/` |
| **Auth / Authz** | Pluggable auth (passthrough/HMAC). Role-based access. | `HOT/kernel/` |
| **Pristine Enforcement** | Path classification: PRISTINE, APPEND_ONLY, DERIVED, EXTERNAL. | `HOT/kernel/` |
| **Token Budgeter** | Token budget tracking per work order. | `HOT/kernel/` |
| **Schema Validator** | JSON Schema validation for all governed artifacts. | `HOT/kernel/` |

### KERNEL.semantic (LLM-backed)

| Component | What | Status |
|---|---|---|
| **Cross-cutting Meta Agent** | Global Workspace / Observer. Reads all tier ledgers. Detects cross-tier patterns. Writes to meta learning ledger. Structural credit assignment. | Design phase |
| **Operational Learning** | HO2-level: adjusting within a WO based on HO1 signals. | Built into HO2 cognitive process |
| **Core Learning** | Long-horizon pattern extraction that changes HO3 principles. | Stage 3+ deferred |

---

## 9. Learning Model — Three Timescales

| Timescale | Name | What | Where | When |
|---|---|---|---|---|
| **Fast** (seconds/minutes) | Operational Learning | HO2 adjusting within a work order. "That template failed, try another." | HO2 cognitive process, HO2m | Current — built into HO2 |
| **Medium** (hours/sessions) | Meta/Cross-cutting Learning | Global Workspace agent detecting patterns across WOs and tiers. Graph-indexed. | KERNEL.semantic meta agent, Meta Learning Ledger | Near-term — design phase |
| **Slow** (days/weeks+) | Core Learning | Long-horizon pattern extraction that changes HO3 principles. | Stage 3+ research | Deferred |

### How Each Timescale Uses the Ledgers

**Operational** (fast):
- `work_order_id + tier = HO1` → all worker events in this WO
- `framework_id + event_type = GATE_FAILED` → which framework keeps failing
- HO2 reads HO1m, adjusts dispatch strategy within the session

**Meta/Cross-cutting** (medium):
- `framework_id + outcome = failure` → all failures involving a framework, ever
- `related_artifacts contains SPEC-025` → how many events touch this spec
- Cross-cutting meta agent reads all ledgers, writes graph-indexed patterns to Meta Learning Ledger

**Core Learning** (slow — deferred):
- Pattern extraction across Meta Learning Ledger entries
- Proposes changes to HO3 principles (requires human approval)
- Weight ≠ authority firewall: emergence is automatic, adoption is deliberate

---

## 10. Architectural Invariants

1. **No direct LLM calls.** Every LLM call flows through the LLM Gateway (KERNEL.syntactic). Log, send, log, count. No exceptions.
2. **Every agent operates under a work order.** Scoped, budgeted, signed. No open-ended permissions.
3. **Agents don't remember — they READ.** No internal state between sessions. All persistent state = ledger queries + attention retrieval.
4. **Communication is contractual.** Versioned prompt contracts with JSON schemas. Every exchange recorded.
5. **Budgets are enforced, not advisory.** Token limits per work order. HO2 cognitive process enforces.
6. **Validation is structural.** KERNEL.syntactic validates schemas. Prompt contracts validate input/output. Governance is the architecture, not a separate agent.
7. **Separate cognitive stacks per agent class.** Each agent class (ADMIN, each RESIDENT) instantiates its own HO2 + HO1 cognitive processes. Shared code, isolated state. Different frameworks, different session state, different attention behavior. They share HO3 governance, KERNEL.syntactic, KERNEL.semantic, and the Meta Learning Ledger.

---

## 11. Cognitive Stacks — Shared Code, Isolated State

Each user-facing agent class gets its own Kitchener loop:

```
ADMIN Cognitive Stack:
    ADMIN-HO3 → uses shared HO3 governance + admin-specific frameworks
    ADMIN-HO2 → admin-specific attention, arbitration, dispatch
    ADMIN-HO1 → executes admin tool calls + LLM calls

DoPeJar Cognitive Stack:
    DPJ-HO3  → uses shared HO3 governance + DoPeJar-specific frameworks
    DPJ-HO2  → DoPeJar-specific attention, arbitration, dispatch
    DPJ-HO1  → executes DoPeJar LLM calls
```

**What's shared** (infrastructure):
- HO3 governance layer (principles, north stars — same for all)
- KERNEL.syntactic (LLM Gateway, gates, integrity, auth)
- KERNEL.semantic (meta agent reads all stacks)
- Meta Learning Ledger (cross-cutting)

**What's isolated** (per stack):
- HO2m session state
- HO1m execution traces
- Attention templates
- Framework configuration
- Work order context

**Build implication**: HO2 cognitive process is written ONCE as generic code. Each agent class instantiates its own copy with different config. Like a class vs instance.

---

## 12. Design Principles From CS Kernel Theory

Two classical kernel concepts map directly to the agentic model and inform the Kitchener dispatch design:

| Classical OS Kernel | Agentic Equivalent | How It Shows Up |
|---|---|---|
| **IPC** | Schema-enforced message passing | All tier-to-tier communication uses versioned prompt contracts with JSON schemas. HO2→HO1 dispatch = work orders. HO1→LLM = prompt contracts. No raw strings. |
| **Capabilities** | Claims-based authorization | Agent classes have fixed capability ceilings (ADMIN: CAP_READ_ALL + CAP_AUDIT_WRITE. RESIDENT: own namespace only). Tier + plane + package scoping. |

---

## 13. Prior Art Patterns (Reference)

From KERNEL_PHASE_2.md prior art survey. Still valid.

| Pattern | Source | Status |
|---|---|---|
| Prompts as versioned contracts | SPEC-019, SPEC-027 | Active — prompt contracts in design |
| Dual validation (syntactic → semantic) | SPEC-011, shaper | Active — KERNEL.syntactic then KERNEL.semantic. Reusable pattern: cheap/deterministic check first, expensive/LLM check second, both must pass. Applies to gate checks, signal detection, content validation. |
| Ledger as sole memory | Memory model doc | Active — invariant #3 |
| Work orders as mandates | Control_Plane specs | Active — the unit of dispatched work |
| Exchange recording | SPEC-027 | Active — LLM Gateway logs every call |
| Four boundaries (A/B/C/D) | SPEC-019 | Active — different trust per communication path |
| Capability matrix by class | CROSSCUTTING, FIREWALL | Active — agent classes have fixed capability ceilings |

Patterns NOT carried forward:
- Keyword-based altitude detection (too brittle)
- Locked system agent base class (too coupled — agents defined by frameworks, not inheritance)
- Hardcoded shaper prompts (everything governed, versioned, auditable)
- Altitude-based turn budgets (absorbed into HO2 cognitive process budget management)

---

## 14. Concrete Flows (Reference)

### Flow A: DoPeJar — "Hello" (competing memories)

```
[User] "hello"
  |
  v
[DoPeJar] wraps as percept
  |
  v
[DPJ-HO2 cognitive process] receives
  |
  |  WO#1 → classify speech-act + ambiguity
  v
[DPJ-HO1] (LLM call: classify)
  |--> {speech_act=reentry_greeting, ambiguity=high, search=enable}
  v
[DPJ-HO2]
  |  WO#2 → horizontal scan (HO2m: recency, open loops)
  v
[DPJ-HO1] (trace query + optional LLM compression)
  |--> HO2_candidates = [closet_design, control_plane]
  v
[DPJ-HO2]
  |  WO#3 → priority probe (HO3m: salience anchors)
  v
[DPJ-HO1] (policy query + optional LLM compression)
  |--> HO3_candidates = [daughter_dance]
  v
[DPJ-HO2]
  |  Arbitration: must-mention=daughter_dance, options=[closet, CP]
  |  Strategy: offer-choice
  |
  |  WO#4 → build final response
  v
[DPJ-HO1] (LLM call: generate response)
  |--> user-facing text
  v
[DoPeJar] → User
  |
[DPJ-HO1] appends canonical trace (WO#1-4 + arbitration)
[DPJ-HO2m] records arbitration meta-episode
```

### Flow B: ADMIN — "Show me all frameworks"

```
[User] "Admin: show me all frameworks"
  |
  v
[ADMIN] wraps as admin query
  |
  v
[ADMIN-HO2 cognitive process]
  |  Classify: read-only inspection
  |
  |  WO#1 → read framework registry
  v
[ADMIN-HO1] (tool call: read_file)
  |--> framework_ids + paths + versions
  |
  |  WO#2 → enumerate frameworks directory (verify)
  v
[ADMIN-HO1] (tool call: list_dir)
  |--> observed frameworks
  |
  |  WO#3 → summarize + format
  v
[ADMIN-HO1] (LLM call: format results)
  |--> formatted table + discrepancies
  v
[ADMIN-HO2] approves output
  v
[ADMIN] → User
  |
[ADMIN-HO1m] records tool calls + outputs
[ADMIN-HO2m] records admin query event
```

---

## 15. Deferred Decisions

| Decision | Why Deferred | When |
|---|---|---|
| **Core Learning** | Research problem. Requires training data + outcome ground truth. | Stage 3+ |
| **Graduated trust** | No trust model variation until real agent data exists. | After Stage 2 evidence |
| **Provider failover** | Single provider sufficient for current work. | When multi-provider needed |
| **Valence / Priority** | Can't define severity until real failure data. Basic salience weighting in HO2 attention is sufficient. | Stage 3+ |
| **Bottom-up signal emergence** | Theory is sound (documented in KP2). Requires meta learning ledger + real data. | After meta agent is operational |
| **Rich ledger entry schema** (~20 fields) | Current LedgerEntry uses generic metadata dict. Rich fields designed in KP2. Standardize as metadata keys when cognitive dispatch runs. | FMWK-008 metadata key standard |

---

## 16. What This Document Supersedes

| Document | Status | Disposition |
|---|---|---|
| `KERNEL_PHASE_2.md` | **ARCHIVED** | Historical reference. Theory sections (bio stack, CS comparison, prior art, signal emergence, ledger schema) remain valid. Stage model and KERNEL.semantic 4-services model superseded. |
| `ADMIN_DESIGN.md` cognitive dispatch section | **SUPERSEDED** | Kitchener 5-step loop replaces the flat HO2→HO1 dispatch model. Component registry and tier model still valid. |
| `Cognitive_hierarchy_prompt_flow_GPT_Discussion.md` | **ARCHIVED** | Source material. Key contributions: cognitive hierarchy alignment, memory arbitration model, DoPeJar/ADMIN flow examples, M0-M4 memory stores. |
| `The Three Things Per Tier.md` | **ABSORBED** | Content integrated into Section 3 of this document. |
| `KERNEL_PHASE_2_REVIEW.md` | **ABSORBED** | Review served its purpose. All findings integrated here. |
| Flow Runner (HANDOFF-5, PKG-FLOW-RUNNER-001) | **DEAD** | HO2 cognitive process is the orchestrator. No separate flow runner. |

---

## 17. Work Order Schema (Reference for FMWK-008)

From SEMANTIC_ARCHITECTURE_PLAN.md. This is the target schema for PKG-WORK-ORDER-001:

```
wo_id:          str           # WO-{uuid4_short}
type:           enum          # classify | retrieve | execute | synthesize | verify
tier_target:    enum          # HO1 | HO2
input_context:  dict          # assembled by HO2 attention
constraints:    dict          # token_budget, timeout, allowed_tools
parent_wo:      optional[str] # for sub-WOs in hierarchical dispatch
lifecycle:      enum          # CREATED → DISPATCHED → EXECUTING → COMPLETED | FAILED
```

Each step in the Kitchener loop produces one or more WOs. HO2 creates them, HO1 executes them, HO2 verifies results.

---

## 18. Critical Path — What's Next

```
DONE:  Bootstrap (16 packages, 8/8 gates, ADMIN first boot)
DONE:  Architecture grounded (this document)
NOW:   FMWK-008 (Work Order Protocol) — update with Kitchener loop + metadata keys
NEXT:  FMWK-009 (Tier Boundary) — formalize syscall model + budget enforcement from HO3
       FMWK-010 (Cognitive Stack) — formalize shared code / isolated state + HO2 session state structure
       FMWK-011 (Prompt Contracts) — formalize contract schema
       → HANDOFF-13 (PKG-WORK-ORDER-001) — the atom
       → HANDOFF-14/15 parallel (HO1 Executor + HO2 Supervisor as cognitive processes)
       → HANDOFF-16 (Session Host v2 rewire — modified Kitchener loop replaces flat loop)
       → HANDOFF-17 (PKG-SHELL-001 — Admin/DoPeJar shell UX, lower priority)
```

### Undispositioned Handoffs (review after design lock)

These were NOT DISPATCHED in prior plans. May map to new framework/package work:

| Handoff | Original Scope | Likely Disposition |
|---|---|---|
| HANDOFF-6 (Ledger Query) | Cross-tier ledger query API | May fold into KERNEL.semantic meta agent |
| HANDOFF-7 (Signal Detector) | Statistical signal detection | Maps to Meta/Cross-cutting Learning |
| HANDOFF-8 (Learning Loops) | Three learning loops | Maps to Section 9 learning model |

### Open Design Questions (resolve during framework writing)

| Question | From | Status |
|---|---|---|
| Aperture lifecycle (OPEN→CLOSING→CLOSED) | KP2 | Deferred — no implementation mapping yet. Captured in future framework. |
| How ADMIN manages RESIDENTs | ADMIN_DESIGN.md | Open — ADMIN observes but cannot interact directly. Management mechanism TBD. |
| Ledger efficiency / hash-anchored trace | Feb 12 session | Open — governance ledger gets summaries + trace_hash, detail in trace files. Not yet written into FMWK-008. |
| Agent identity model | KP2 | Implicit answer: work-order-as-identity. Formal decision needed. |
| Event-driven reactions (pub/sub) | KP2 | Stage 3+ — currently ledger is pull-only |
| Observability / metrics | KP2 | Stage 3+ — currently basic stats only |
