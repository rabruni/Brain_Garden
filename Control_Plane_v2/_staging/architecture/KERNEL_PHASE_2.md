# Kernel Phase 2: From Trust Kernel to Governed Agents

**Status**: Planning — Stage 1 in progress, Stage 1.5 next
**Created**: 2026-02-10
**Origin**: Live conversation during CP_BOOTSTRAP fixes session

---

## Context

After completing the bootstrap rebuild (8 packages, 72 governed files, Layer 0-2 verified), we asked: *is the kernel actually complete?*

We evaluated from two disciplines — computer science and biology — and found three gaps that separate a **trust kernel** (what we have) from a **kernel for trusted self-aware intelligence** (what we need). Then we stress-tested the roadmap with adversarial analysis and refined it.

---

## Where We Actually Are (Honest Assessment)

We have a **package management system with integrity verification**. That's it.

- One plane active (HOT) with 72 governed files
- A ledger (memory)
- Gates (error detection) — enforced at install time only
- Auth exists but is bypassed (`--dev` mode only)
- No agents operate inside the system — developers (us) operate outside it
- The control plane doesn't control us — we control it

The "agentic" part of the system is a design goal, not a runtime reality.

---

## What the Kernel Has Today (Phase 1 — Complete)

| Area | Implementation | Status |
|---|---|---|
| Identity / AuthN | auth.py | Done |
| Authorization / claims | authz.py, install_auth.py | Done (wired in this session) |
| Integrity | hashing.py, merkle.py | Done |
| Provenance | provenance.py | Done |
| Audit / ledger | ledger_client.py | Done |
| Layout / topology | paths.py, layout.py, plane.py | Done |
| Gate enforcement | gate_check.py, preflight.py | Done |
| Schema validation | schema_validator.py | Done |
| Package lifecycle | packages.py, package_install.py | Done |

**72 files governed. 8 packages. 133 tests passing. G1-COMPLETE gate live.**

---

## The Biological Kernel Stack (Reference Framework)

| Layer | Biology | Structure | Control Plane Equivalent | Status |
|---|---|---|---|---|
| 0 | Boundary (self/non-self) | Immune system, MHC markers | Identity, authorization, file ownership | **Done** |
| 1 | Homeostasis (integrity) | Hypothalamus, autonomic NS | Hashing, integrity checks, gates | **Done** |
| 2 | Sensation + Routing | Thalamus | Layout/topology, attention routing | **Partial** — layout done, attention missing |
| 3 | Memory (multiple kinds) | Hippocampus, PFC, basal ganglia | Ledger (episodic), context (working), schemas (semantic) | **Partial** — ledger done, working memory unmanaged |
| 4 | Error detection | Anterior cingulate cortex | Gate enforcement, integrity verification | **Done** |
| 5 | Valence (what matters) | Dopaminergic system, amygdala | Policy, priority, scheduling | **Missing** |
| 6 | Self-model | Insular cortex, default mode network | Self-inspection, health model | **Primitive** |

### Key biological insight

Biology never trusts a single memory system. Episodic memory (hippocampus) is reconstructed from multiple sources through replay and consolidation. This matches our design principle: **"Agents don't REMEMBER, they READ"** — and it's what `rebuild_derived_registries.py` does (reconstruct state from evidence, not cache).

---

## The Three Kernel Gaps (CS + Biology Analysis)

### Gap 1: Attention Routing

**The problem**: Agents have limited context windows. Without kernel-level attention management, agents either see everything (overload) or see nothing useful (starvation).

**CS view**: Classical kernels manage memory (scarce resource). Agentic kernels must manage attention (context window = scarce resource).

**Biology view**: The thalamus routes all sensory input. It's a kernel-level filter — pre-conscious. The cortex never sees what the thalamus drops.

**Definition of attention in our kernel**: The mechanism that sits between the world (all files, all state, all history) and the agent (limited context window). Four operations:

| Operation | Biology | CS | What It Does |
|---|---|---|---|
| **Filter** | Thalamic gating | Page table | Decides what's relevant. Everything else invisible. |
| **Promote** | Reticular activating system | Page fault → page-in | Something became relevant mid-task. Bring into context. Costs budget. |
| **Evict** | Habituation | Page eviction (LRU) | Context full. Least relevant leaves. |
| **Interrupt** | Amygdala hijack | Hardware interrupt | Urgent: bypasses normal filtering. Gate failure, integrity violation, user escalation. |

**Five properties**: Budgeted, scoped by aperture, layered (structural/task/ambient), auditable, fail-closed (when in doubt, include rather than exclude).

**When it's needed**: Not now. Emerges at Stage 2 when an agent needs scoped context, becomes essential at Stage 3 for automated filtering.

### Gap 2: Self-Model

**The problem**: The kernel can verify individual files but cannot answer "what is my current state as a coherent system?"

**CS view**: Agentic kernels must handle non-determinism. Need to model own state to detect divergence.

**Biology view**: Insular cortex (interoception) + default mode network (self-referential processing). Without these, an organism reacts but doesn't know it's reacting.

**Refined design (after adversarial analysis)**: Not a new system — a thin composition layer over existing kernel tools. Three queries:

| Query | What It Does | Built From |
|---|---|---|
| `am_i_intact()` | Verify every governed file matches its declared hash | hashing.py + manifests from receipts |
| `what_am_i()` | Structured inventory: packages, versions, file counts, gate status | receipts + registries + ledger |
| `what_is_ungoverned()` | Files under governed paths that aren't package assets or known runtime artifacts | file_ownership.csv + runtime artifact allowlist |

**Explicitly deferred**: Temporal awareness, causal model, forward model (prediction), agent awareness, capacity model. All deferred until real usage data exists.

**When it's needed**: Now. This is G0B — the gate we skipped. Stage 1 deliverable.

### Gap 3: Valence / Priority

**The problem**: The kernel processes everything equally. No concept of "this matters more."

**CS view**: Not just scheduling but "what should the system care about right now."

**Biology view**: Dopaminergic system + amygdala. Approach or avoid? Without valence, nothing gets prioritized.

**When it's needed**: Stage 3 at earliest. Can't define severity until we have real data about what goes wrong.

---

## The Roadmap (Adversarially Tested)

### Initial 4-Stage Proposal

```
Stage 0: Boot → Stage 1: Kernel Running → Stage 2: First Semantic Agent → Stage 3: First Admin Agent
```

### Adversarial Findings (Reversed Cadence: Hurdles → Too Much → Not Enough)

**Hurdles found:**
- Auth wiring (InstallerClaims) isn't done — deferred from today's work
- No agent runtime exists — the Stage 1→2 jump is a category change, not a step
- "What IS an agent?" is undefined — identity, scope, context envelope all depend on this unanswered question
- "Semantic" is a property of the LLM, not the kernel — the kernel presents data, Claude brings interpretation
- No event infrastructure for Stage 3 (no pub/sub, no event bus)
- Stage 2 proof criteria require Stage 2 deliverables — circular testability

**Too much found:**
- Four stages hides three different projects (infrastructure, AI integration, operations) with cliff edges between them
- Stage 2 is either trivial (formalize what we already do) or enormous (autonomous agent runtime) — proposal didn't distinguish
- Stage 3 "admin agent" might just be a cron job + `am_i_intact()` — "agent" inflates the problem
- Context envelope is premature abstraction at 72 files
- Valence reappears at Stage 3 without being solved

**Not enough found:**
- No end state — what does the system look like after all stages?
- No failure modes — every stage has "done when" but not "what happens when it breaks"
- No governance of agents themselves — system governs files but not the intelligences operating on them
- Aperture model (OPEN→CLOSING→CLOSED) disappeared from the roadmap entirely
- No resource model — token costs, API budgets, operational expense
- No theory of agent trust — trust in hashes is binary, trust in recommendations is probabilistic

### Refined Roadmap

```
Stage 0: Boot                    → System exists                          DONE
Stage 1: Kernel Running          → System trusts itself                   IN PROGRESS
Stage 1.5: Agent Definition      → We know what an agent IS               NEXT
Stage 2: First Governed Agent    → One agent, one task, full governance   AFTER 1.5
Stage 3: TBD based on evidence   → Designed from what we learn in Stage 2
```

### Stage 0: Boot (DONE)

8 packages, 72 files, gates enforcing, ledger recording, `--dev` mode only. Clean-room verified by two independent agents.

### Stage 1: Kernel Running (IN PROGRESS)

**What it is**: The kernel can verify itself and enforce auth without developer bypass.

| Deliverable | Status |
|---|---|
| G0B gate (`am_i_intact()` as a gate check) | Builder agent working on self-verification |
| Auth wiring (InstallerClaims into package_install.py) | Designed, not wired |
| `rebuild_derived_registries.py` working | Path fixes done, not packaged |
| Self-verification (3 queries) | Builder agent Task 2 |
| Runtime artifact allowlist | Not started |

**Failure mode**: G0B fails → install blocked, report generated, user decides.

**Done when**: Clean install with auth enforced. Deliberate corruption caught by `am_i_intact()`. Orphan file caught by `what_is_ungoverned()`.

### Stage 1.5: Agent Definition (IN PROGRESS)

**What it is**: Answer the question we've been dodging — what is an agent in this system?

#### Agent Classes (Refined 2026-02-10, v2)

Not all classes are agents. The kernel classes are infrastructure — deterministic code and LLM-backed services. ADMIN and RESIDENT are the actual agents.

| Class | What It Is | Layer | Biology Analogy |
|---|---|---|---|
| **KERNEL.syntactic** | Deterministic code — the machinery. Not an agent. | Brainstem | Autonomic — runs without thinking |
| **KERNEL.semantic** | LLM-backed kernel services. Not an agent — infrastructure that agents route through. | Thalamus | Routes, filters, budgets — invisible to user |
| **ADMIN** | Admin's governed delegate. The only agent that sees everything. | Prefrontal | Executive function — manages the arena |
| **RESIDENT** | The cognitive brain. Everything else. | Cortex | Does the actual work |

#### KERNEL.syntactic (Not an Agent)

Deterministic code that enforces invariants. Hashes match or don't. Schemas conform or don't. Gates pass or fail. No LLM, no judgment, no ambiguity.

- **Trust**: Verifiable — output is binary
- **Context**: Manifests, schemas, registries, file system
- **Implements**: gate_check.py, package_install.py, hashing.py, preflight.py, schema_validator.py
- **Key constraint**: Must be fast. Every agent operation hits this layer first.

#### KERNEL.semantic (Not an Agent — Kernel Services)

LLM-backed services that all agents depend on. No agent calls an LLM directly — everything routes through this layer. This makes governance, budgeting, and audit automatic rather than opt-in.

**Critical design point**: Each prompt is **single-shot**. Context is fully assembled before the prompt reaches the router. The router doesn't interpret, classify, or transform — it logs, sends, logs, returns. The intelligence is in context assembly (Attention), not routing.

Four services:

| Service | What It Does | Why It's Kernel | Stage |
|---|---|---|---|
| **Prompt Router** | Dumb logging gateway. Receives fully-assembled prompt + contract reference. Logs to ledger. Sends to provider. Logs response. Returns. That's it. | Single choke point makes governance and audit automatic. | **Stage 2** |
| **Attention** | Builds context envelopes — decides what an agent sees. This is where the real intelligence lives. Context is managed this deep in the kernel. | Context scoping is a security boundary, not a convenience. | Hand-curated Stage 2, automated Stage 3+ |
| **Flow Runner** | Orchestrates multi-step agent workflows. Enforces turn budgets. Stops agents that exceed their mandate. | Budget enforcement must be kernel-level or agents will ignore it. | Single-step Stage 2, orchestration Stage 3+ |
| **Core Learning** | Extracts patterns from exchange recordings. Feeds back into attention heuristics. | System-wide learning must be centralized or each agent diverges. | **Stage 3+** (research problem) |

- **Provider**: Pluggable — Anthropic, OpenAI, local models. Shared token budgets across all agents.
- **Key constraint**: No direct LLM calls. Period. Every prompt/response pair is recorded (contract ID, input, output, tokens, identity, boundary).

**Why not Shaper?** Prior art included a governance inspection agent (shaper) as a kernel service. It was a good experiment — worked well — but too hardcoded to be a kernel primitive. Removed. The problem it solved is better addressed by well-designed prompt contracts + KERNEL.syntactic schema validation. If the output schema is right, syntactic validation catches structural violations. Semantic quality is assessed by the consumer of the output, not a second LLM call validating the first.

#### ADMIN (Agent — Admin's Delegate)

The admin's hands inside the governed world. Operates under work orders like every other agent, but with asymmetric permissions.

- **Reads**: Everything — kernel state, resident state, ledger, logs, exchange recordings, gate status
- **Writes**: Resident space only — deploys packages, creates/configures/starts/stops residents, manages resident frameworks
- **Cannot write**: Kernel space. ADMIN inspects the engine but doesn't modify it.
- **Trust**: Trusted delegate. Acts on admin's behalf under signed work orders. Every action traced to a mandate.
- **Examples**: System health (am_i_intact), orphan detection, log inspection, resident deployment, intervene on failed validation, capacity planning
- **Key insight**: ADMIN is not a hole in the firewall — it's a watchtower outside the walls. Full visibility, scoped authority.

#### RESIDENT (Agent — The Cognitive Brain)

Everything else. Defined entirely by non-kernel frameworks. Domain-specific. The only class that does "real work" from the user's perspective.

- **Reads**: Own namespace only. Sees the world through attention envelopes built by KERNEL.semantic.
- **Writes**: Own namespace only. Output goes through prompt contracts — structured, schema-validated, recorded.
- **Cannot see**: Kernel internals, other residents' state (unless ADMIN grants access via framework config).
- **Trust**: Governed by mandate + contract enforcement. ADMIN manages lifecycle. KERNEL.semantic routes prompts. KERNEL.syntactic validates structure. The full stack sits beneath every resident action.
- **Consumer shape**: One agent interface (e.g., DoPeJar)
- **Enterprise shape**: Many agents for different domains
- **Key insight**: A resident doesn't know it's governed. It invokes prompt contracts and gets responses — the governance is invisible from inside.

#### Architectural Invariants

1. **No direct LLM calls.** Every prompt goes through the prompt router. No exceptions.
2. **Every agent operates under a work order.** Scoped, budgeted, signed. No open-ended permissions.
3. **Agents don't remember.** No internal state between sessions. All persistent state = ledger queries + attention envelopes.
4. **Communication is contractual.** Versioned prompt contracts with JSON schemas, not raw strings. Every exchange recorded.
5. **Budgets are enforced, not advisory.** Turn limits per altitude. Token limits per work order. Flow runner stops agents that exceed.
6. **Validation is structural.** KERNEL.syntactic validates schemas. Prompt contracts validate input/output. No separate "governance agent" — governance is the architecture itself.

#### The Stack

```
RESIDENT          — does the work (cortex)
    ↑ managed by
ADMIN             — manages the arena (prefrontal)
    ↑ routes through
KERNEL.semantic   — 4 LLM kernel services (thalamus)
    ↑ enforced by
KERNEL.syntactic  — deterministic code (brainstem)
```

#### Remaining Questions (narrowed by prior art)

| # | Question | Prior Art Answer | Still Open? |
|---|---|---|---|
| 1 | How does an agent authenticate? | Same auth system, agent identity = signed work order origin | **Mostly answered** — need to decide: separate agent identity model or work-order-as-identity? |
| 2 | What is a mandate? | Work order: scope, budget, authorization, tool permissions, I/O schemas | **Answered** — formalize the work order schema |
| 3 | What is context? | Attention envelope: structured, auditable, scoped by aperture | **Answered** — design the envelope schema |
| 4 | Aperture lifecycle? | OPEN→CLOSING→CLOSED | **Still open** — no prior art on implementation |
| 5 | How do you trust output? | Contract enforcement (schema) + consumer assessment. No separate validator. | **Answered** — shaper removal clarifies this |
| 6 | Token budgeting? | Altitude-based turn budgets + per-work-order token limits | **Answered** — design the budget model |

**Checklist** (from biology/CS framework): Does the agent definition account for boundary (identity ✓), attention (context ✓), memory (ledger — agents don't remember ✓), error detection (contract validation ✓), and valence (priority — still missing)?

**Done when**: We can describe a specific agent doing a specific task, and every remaining question has a concrete answer.

#### Adversarial Analysis of Agent Definition (3-pass)

**Pass 1 — Not Enough:**

- **No error recovery model.** Prompt router returns garbage — then what? Attention builds wrong envelope — then what? Flow runner exceeds budget — it stops the agent, but what happens to partial work? No rollback semantics for agent operations, only for package installs.
- **No versioning of kernel semantic services.** Prompt router v1 vs v2 — how do we upgrade? These are LLM-backed services, not files. The package system governs files. What governs service behavior?
- **No health model for the semantic layer.** `am_i_intact()` checks file hashes. But "is the prompt router routing correctly?" is a semantic question that hashing can't answer.
- **No LLM provider failure model.** If the API goes down, every agent stops. No fallback, no degraded mode, no queue-and-retry.
- **Core Learning is hand-waved.** "Extracts patterns" and "feeds back into routing" — through what mechanism? This is a research problem dressed as a bullet point.
- **No graduated trust.** A brand-new resident and a battle-tested resident have identical trust profiles. No way to earn trust through track record.
- **Who governs the prompt router's own LLM calls?** The router calls the LLM to classify prompts by altitude. That call itself crosses boundary A. Who governs it? Infinite regress risk.
- **ADMIN's work order origin.** Who creates ADMIN's work orders? If it's the human admin, that's boundary C — but we haven't defined how human→agent mandates work.
- **No valence.** Acknowledged as missing. But without it, the flow runner has no basis for prioritization when multiple agents compete for budget.

**Pass 2 — Too Much:**

- **Four kernel semantic services for Stage 2.** We said "one agent, one task." Do we really need a prompt router, attention service, flow runner, AND core learning to support one agent doing one thing? Core Learning is definitely premature. Flow Runner might be. Even Attention could be hand-curated for Stage 2.
- **Exchange recording for every call.** Full input/output/tokens/identity for every LLM interaction. At scale, the ledger becomes enormous. Is this really needed from day one, or should recording granularity be configurable?
- **Four boundaries (A/B/C/D).** Stage 2 has one agent. It crosses boundary A (agent→LLM). Boundaries B, C, D are future. Designing for all four now is premature.
- **Altitude-based routing.** For Stage 2, we might have... one altitude. One agent, one task, one prompt type. The routing layer is overhead until there are multiple prompt types to route between.
- **"No direct LLM calls — period."** This is an invariant we can't enforce yet. There's no runtime to enforce it in. It's an aspiration masquerading as an architectural constraint. At Stage 2, the "enforcement" is: we only write one agent, and we write it to use the router. That's convention, not enforcement.
- **JSON schema contracts for everything.** Heavyweight for Stage 2. A single agent with a single task probably needs one contract, not a contract framework.

**Pass 3 — Hurdles:**

- **Enforcing "no direct LLM calls" requires a runtime.** Without a process boundary or SDK that makes the router the only available LLM interface, this is just a rule developers can ignore. The kernel governs files — it doesn't govern runtime behavior yet.
- **The prompt router needs to exist before any agent can.** But the router is itself an LLM-backed service. Bootstrapping problem: who routes the router's own prompts? Need a bootstrap path where the router's own calls are unrouted (direct) until the system is stable.
- **Attention envelopes require knowing what's relevant.** For Stage 2, humans curate context. But the Attention service is supposed to do this automatically. The gap between "human picks the files" and "service builds the envelope" is the entire AI problem.
- **Work order schema doesn't exist.** We said mandates = work orders, but haven't defined the schema. Can't build agents until this exists.
- **Flow Runner assumes multi-step workflows.** Stage 2 is one step. The runner is infrastructure for Stage 3+, not Stage 2.
- **ADMIN bootstrapping.** ADMIN manages residents. But who creates ADMIN? A human runs a script? A package install? ADMIN can't self-create because it needs to exist to manage its own deployment.

#### Adversarial Synthesis

The agent definition is architecturally sound but **over-specified for Stage 2 and under-specified for Stage 3+.**

**What to build for Stage 2 (minimum viable kernel semantic layer):**
1. Prompt Router — dumb logging, one provider, basic recording.
2. Work Order schema — the mandate format. Required before anything else.
3. One agent (probably ADMIN) doing one task under one work order.

**What to defer:**
- Attention service → hand-curated context for Stage 2, automated later
- Flow Runner → single-step only at Stage 2, orchestration later
- Core Learning → research problem, not Stage 2
- Altitude routing → one altitude at Stage 2
- Graduated trust → no trust model variation until we have data
- Provider failover → single provider at Stage 2

**What to resolve before Stage 2:**
- Work order schema (must exist)
- Prompt router bootstrap path (the router is dumb logging — no self-referential problem)
- ADMIN creation mechanism (how does the first agent get deployed?)
- Prompt router as the only LLM interface (convention at Stage 2, enforced later)

---

### Existing Infrastructure Inventory (What's Already Built)

**Why this section exists**: We've built further than where the clean bootstrap currently stands. Prior agent sessions built extensive kernel infrastructure that exists in the repo (conflated, but functional). Phase 2 should use what works, not rebuild it. This inventory maps existing code to agent needs.

#### Infrastructure That Supports Agents (Already Built)

| Agent Need | Existing Component | File | Lines | What It Does |
|---|---|---|---|---|
| **Mandate lifecycle** | LedgerFactory | ledger_factory.py | 617 | Full work order lifecycle: create WO instance with cross-tier hash linkage, WO_STARTED → SESSION_SPAWNED → gate events → SESSION_END → WO_EXEC_COMPLETE. This IS the mandate infrastructure. |
| **Event recording** | LedgerClient | ledger_client.py | 1063 | Hash-chained append-only log (SPEC-025). Merkle verification. Segment rotation (256MB/daily). Per-segment indexes. Query API: by submission, event type, range, recent. |
| **Execution isolation** | IsolatedWorkspace | workspace.py | 200+ | Ephemeral temp directories for work order execution. Quarantine on failure. Context manager pattern. |
| **Progress tracking** | CursorManager | cursor.py | 150 | Monotonic cursor per ledger — "where did I leave off." Enables incremental processing. Agent can resume by reading from cursor. |
| **Write boundaries** | Pristine enforcement | pristine.py | 350+ | Path classification: PRISTINE (read-only), APPEND_ONLY (ledger), DERIVED (mutable), EXTERNAL. Mode-aware: normal/install/bootstrap. This IS the agent permission model for file access. |
| **Integrity verification** | IntegrityChecker | integrity.py | 300+ | Three-check validation: registry↔filesystem, content↔hash, merkle root. This IS `am_i_intact()`. |
| **Supply chain** | Provenance/Attestation | provenance.py | 300+ | Attestation with 6 ledger event types. Builder info, source info, package digest. |
| **Artifact lifecycle** | GateOperations | gate_operations.py | 500+ | CRUD with auth enforcement. ID allocation by prefix. Supports: FMWK, SPEC, PROMPT, AGENT, SCRIPT, etc. |
| **State snapshots** | Version management | cp_version_*.py | 300+ | Checkpoint (registry snapshot + merkle root + package list). Rollback. |
| **Cross-tier linking** | GENESIS chain verification | ledger_client.py | — | Child ledger GENESIS references parent's last entry hash. HOT→HO2→HO1 verified cryptographically. |
| **Identity/Auth** | auth + authz + install_auth | kernel/ | — | Pluggable auth (passthrough/HMAC). Role-based access. InstallerClaims with plane/tier/env scoping. |
| **Tier manifests** | TierManifest | tier_manifest.py | 204 | Tier configuration per directory. Status lifecycle: active→archived→closed. |
| **Output formatting** | ResultReporter | output.py | 66 | Structured OK/FAIL/WARN reporting with category grouping. |
| **Registry operations** | registry.py | registry.py | 300+ | CRUD + lookup across tier-aware registries. Find by ID/name, aggregate stats. |
| **ID allocation** | id_allocator.py | id_allocator.py | 149 | Sequential ID allocation by prefix (FMWK-xxx, SPEC-xxx, PROMPT-xxx, AGENT-xxx). |

#### Event Types Already Defined

The ledger already models the full agent execution lifecycle:

```
HOT tier:     WO_APPROVED → (cross-tier hash link)
HO2 tier:     GENESIS → WO_STARTED → SESSION_SPAWNED → WO_EXEC_COMPLETE
HO1 tier:     GENESIS → SESSION_START → GATE_PASSED/FAILED → SESSION_END
```

Plus: INSTALL_STARTED/INSTALLED/INSTALL_FAILED, ATTESTATION_* (6 types), GATE_PASSED/FAILED.

Each entry is hash-chained, timestamped, UUID-identified (LED-{hex8}), with metadata dict for context.

#### Ledger Tier Model (Already Wired)

| Tier | Ledger Name | Purpose | Instance Model |
|---|---|---|---|
| HOT | governance.jsonl | Executive decisions: approvals, policy, system events | Single ledger |
| HO2 | workorder.jsonl | Work order execution tracking | Per-WO instances under `work_orders/{wo_id}/` |
| HO1 | worker.jsonl | Session-level execution detail | Per-session instances under `sessions/{session_id}/` |

Cross-tier: child GENESIS → parent last hash. Verifiable chain from HO1 session → HO2 work order → HOT approval.

#### What's NOT Built (The Actual Gaps)

| Gap | What's Needed | Needed For |
|---|---|---|
| **Prompt Router** | Dumb logging gateway: receive prompt, log, send to LLM, log response, return. Single-shot. | Stage 2 — the only new LLM-touching code |
| **Work Order schema** | JSON schema for mandates: scope, budget, authorization, I/O schemas, tool permissions | Stage 2 — must exist before any agent runs |
| **Prompt Contract schema** | JSON schema for prompt contracts: ID, version, input/output schemas, boundary | Stage 2 — defines the prompt router's interface |
| **Exchange recording format** | Ledger entry metadata fields for prompt exchanges: contract ref, input hash, output, tokens, identity | Stage 2 — extends existing LedgerEntry metadata |
| **Agent identity model** | How agents authenticate. Work-order-as-identity? Separate agent credentials? | Stage 2 — decide before first agent |
| **Context assembly** | Building attention envelopes from governed state. Hand-curated at Stage 2, automated later. | Hand-curated Stage 2, service Stage 3+ |
| **Multi-step orchestration** | Flow runner for multi-step workflows with budget enforcement. | Stage 3+ |
| **Pattern learning** | Extract patterns from exchange recordings, feed back into attention. | Stage 3+ (research) |
| **Event-driven reactions** | Pub/sub or event bus. Currently ledger is pull-only. | Stage 3+ |
| **Observability/metrics** | Centralized telemetry. Currently basic stats only. | Stage 3+ |
| **Scheduler/daemon** | Background process for continuous monitoring. Currently all request-driven. | Stage 3+ |

#### Key Insight

**The gap between "kernel" and "first governed agent" is much smaller than it appeared.** The ledger factory already implements work order lifecycle with cross-tier hash linkage. The workspace provides execution isolation. The pristine enforcer provides write boundaries. The integrity checker provides self-verification. The cursor manager provides resumability.

What's missing is: **something that reads a work order and executes it by sending a single-shot prompt through a dumb logging router.** That's one new script, three new schemas, and wiring to existing infrastructure.

---

### Stage 2: First Governed Agent (AFTER 1.5)

**What it is**: One agent, doing one real task, inside full governance. Not an "agent runtime" — one agent, built clean and simple on existing infrastructure.

#### What Gets Built (New)

| Deliverable | Type | Description |
|---|---|---|
| **Work order schema** | JSON Schema (spec-governed) | Mandate format: scope, budget, authorization, I/O schemas, tool permissions. Registered as a spec. |
| **Prompt contract schema** | JSON Schema (spec-governed) | Contract format: ID, version, input/output schemas, boundary. Registered as a spec. |
| **Prompt router** | Script (HOT/scripts/) | Dumb logging gateway. Receives assembled prompt + contract ref. Logs to ledger. Calls LLM provider. Logs response. Returns. Single-shot only. |
| **One prompt contract** | Config (governed) | The specific contract for the Stage 2 task — probably: "evaluate this package install for governance compliance." |
| **One ADMIN agent** | Script (governed) | Reads work order. Assembles context (hand-curated for Stage 2). Sends prompt through router. Returns structured result. Logs to ledger. |

#### What Gets Reused (Existing)

| Existing Component | How Stage 2 Uses It |
|---|---|
| LedgerFactory | Creates WO instance (HO2) linked to HOT approval. Writes WO_STARTED, SESSION_SPAWNED, WO_EXEC_COMPLETE. |
| LedgerClient | Records all events: work order lifecycle + exchange recording (prompt/response logged as ledger entries). |
| IsolatedWorkspace | Agent executes inside ephemeral workspace. Quarantined on failure. |
| Pristine enforcement | Agent respects PRISTINE/APPEND_ONLY/DERIVED boundaries. Reads governed files, appends to ledger, writes to DERIVED only. |
| IntegrityChecker | The actual task: agent runs `am_i_intact()` (or similar) and reports findings through a prompt contract. |
| Auth/Authz | Agent authenticates. Not `--dev`. Work order is the authorization. |
| GateOperations | Agent result registered as a governed artifact (ID-allocated, tracked). |
| CursorManager | Agent can read ledger incrementally (from where it last left off). |

#### The Flow (Concrete)

```
Human                           HOT ledger                    HO2 ledger
──────                          ──────────                    ──────────
1. Creates work order      →    WO_APPROVED (signed)
2. Launches agent script   →                             →   GENESIS (linked to HOT)
                                                              WO_STARTED
3. Agent reads WO scope
4. Agent assembles context       (hand-curated: manifests, registries, recent ledger entries)
5. Agent builds prompt           (from contract template + context)
6. Prompt router logs       →                             →   EXCHANGE_SENT (contract ref, input hash)
7. Router sends to LLM          (single-shot, Anthropic API)
8. Router logs response     →                             →   EXCHANGE_RECEIVED (output, tokens)
9. Agent formats result
10. Agent writes result     →                             →   WO_EXEC_COMPLETE (result status, output hash)
11. Human reviews result         (advisory — human approves/denies)
```

Every step is recorded. The full decision chain is auditable: who approved the work order (HOT), what the agent saw (context hash), what it asked (prompt logged), what the LLM said (response logged), what the agent concluded (result).

#### Scope Boundaries

- **One agent**: ADMIN class
- **One task**: Evaluate system integrity (runs am_i_intact + reports)
- **One contract**: Structured input (system state) → structured output (integrity report + recommendation)
- **One provider**: Anthropic (pluggable interface, but one implementation)
- **Hand-curated context**: Human picks which files/state to include. No automated attention.
- **Single-step**: No multi-step workflows. One prompt, one response, done.
- **Advisory output**: Human reviews and acts. Agent doesn't execute changes.

#### Done When

1. Agent runs under a signed work order (not `--dev`)
2. Full lifecycle recorded in ledger (WO_APPROVED → WO_STARTED → EXCHANGE_SENT → EXCHANGE_RECEIVED → WO_EXEC_COMPLETE)
3. Agent correctly evaluates a real governance question
4. Full decision chain auditable from ledger entries alone
5. Deliberate corruption detected and reported through the prompt contract
6. Context is traceable (what the agent saw is recorded, not just what it decided)

#### What Emerges Here

- The thalamus problem becomes real — what context does the agent actually need?
- We'll learn what the attention service should automate (from hand-curated evidence)
- We'll learn whether one prompt contract is enough or if the task naturally decomposes
- We'll learn the real cost model (tokens per evaluation, latency, ledger growth rate)

### Stage 3: TBD

Designed from evidence gathered in Stage 2. Not designed in advance.

After Stage 2, we'll know:
- What context the agent actually needed (→ informs attention service design)
- What it got wrong and why (→ informs trust model)
- Whether continuous monitoring needs intelligence or a script (→ informs admin design)
- What "severity" means in practice (→ informs valence)
- How fast the ledger grows with exchange recording (→ informs rotation/archival)
- Whether one prompt contract sufficed or if the task decomposed (→ informs flow runner)

---

## CS Kernel Comparison (Reference)

| Classical OS Kernel | Agentic Systems Kernel | Key Difference |
|---|---|---|
| Process isolation | Agent sandboxing | Agents are stochastic, not deterministic |
| Memory management | Attention management | Context window is the scarce resource, not RAM |
| Scheduling | Orchestration + valence | Not just "who runs first" but "what matters now" |
| IPC | Schema-enforced message passing | Agents communicate through contracts, not raw bytes |
| Capabilities | Claims-based authorization | Tier + plane + package scoping, not just read/write/execute |
| Interrupt dispatch | Event routing | Ledger events, gate failures, escalation triggers |

### What agentic kernels need that classical kernels don't

- **Non-determinism management** — same input can diverge. Kernel must handle that without losing trust.
- **Provenance chains** — not just "is this binary signed" but "which agent produced this, through what reasoning, under what authority"
- **Resource accounting** — agents consume expensive external resources (tokens, API calls). Kernel must track and budget.
- **Self-inspection** — the system must answer "what is my current state?" from evidence, not from cache.

---

## Conversation Record

### 2026-02-10 — Session 1: CP_BOOTSTRAP Fixes + Kernel Completeness Analysis

**What we did:**
1. Fixed HO3 references in 4 schema/config files (package_manifest.json, framework.schema.json, spec.schema.json, layout.json)
2. Fixed install_auth.py DEFAULT_PLANES from `{"hot", "first", "second"}` to `{"hot", "ho2", "ho1"}`
3. Rebuilt KERNEL-001 cascade: manifest hash, tar.gz, seed_registry.json (both copies), GENESIS-000.tar.gz, CP_BOOTSTRAP.tar.gz
4. Clean-room verified Layer 0+1 bootstrap (3 packages, all gates green)

**Then we asked**: Is the kernel complete?

**Analysis method**: Evaluated from two disciplines — computer science (OS kernel theory, agentic systems) and biology (neuroscience of self-aware intelligence).

**Finding**: The kernel is a complete **trust infrastructure** (identity, integrity, provenance, audit, gates, schemas). Three capabilities are missing for a **kernel for trusted self-aware intelligence**: attention routing, self-model, valence/priority.

### 2026-02-10 — Session 1 (continued): Roadmap Development

**Key realization**: We don't have an agentic system yet. We have a package management system with integrity verification. The "agents" are developers (us) operating outside the system in `--dev` mode.

**Self-model refined**: Through adversarial analysis (not enough / too much / hurdles), stripped the self-model from 6 queries to 3. Identified that it's not a Phase 2 capability — it's G0B, the gate we skipped. Builder agent is already working on self-verification.

**Roadmap developed**: Initial 4-stage proposal (Boot → Kernel Running → Semantic Agent → Admin Agent). Tested adversarially in reverse order (Hurdles → Too Much → Not Enough).

**Critical finding from reversed adversarial cadence**: The gap between Stage 1 (infrastructure) and Stage 2 (agents) is a category change, not a step. We can't design Stage 2 without first answering "what is an agent in this system?" Added Stage 1.5 (Agent Definition) as a design-only milestone.

**Refined roadmap**: Stage 0 (done) → Stage 1: Kernel Running (in progress) → Stage 1.5: Agent Definition (next) → Stage 2: First Governed Agent → Stage 3: TBD from evidence.

**Key quote**: "We stop designing Stages 2-3 in detail until we've answered 'what is an agent' and have real data from a real agent doing a real task. Everything else is speculation."

**Builder agent handoff**: Created briefing (`_staging/AGENT_PROMPT_builder_qa.md`) and trust test (`_staging/BUILDER_AGENT_HANDOFF.md`). Builder agent passed all 4 trust test steps — clean install, hash verification using kernel tools, boundary understanding, cascade knowledge. Cleared to proceed with Bug A (stray manifest), Bug B (test failure), and self-verification (Task 2).

**Staging cleanup**: Removed stale `_staging/ledger/`, `/tmp/cp_bootstrap_inspect/`, `/tmp/cp_clean_test/`, `CP_GEN_0.tar.gz` (superseded by CP_BOOTSTRAP.tar.gz).

---

## Outstanding Questions

| # | Question | Status | Answer |
|---|---|---|---|
| Q1 | Can the kernel verify itself? | **Answered** | Partially. G1 chain yes, hash verification yes, receipts 7/8, ledger consistent. **G0B ownership FAILS** — file_ownership.csv only tracks KERNEL-001's 22 files; other 50 files are orphans to the ownership system. |
| Q2 | Should G0B run at every install or on-demand? | **Answered** | Both. Lightweight at install time (pre-install: verify existing files are intact). Full on-demand via CLI (am_i_intact, what_am_i, what_is_ungoverned). |
| Q3 | How do we wire InstallerClaims? | **Answered** | In KERNEL-001's package_install.py main() — state-gated. `--dev` bypasses auth; when HMAC secret exists, InstallerClaims activates. No file replacement. |
| Q4 | What is an agent in this system? | Open | Stage 1.5 — next planning session |
| Q5 | What does the end state look like? | Open | Vision conversation needed |
| Q6 | How do we govern agents, not just files? | Open | After Q4 |
| Q7 | What's the resource/cost model? | Open | After Stage 2 |

## Design Decision: Install Lifecycle (2026-02-10)

### The Missing Phase

The install pipeline had pre-flight (gates) and execute (copy) but no **post-flight / validation / commit** phase. This meant:
- file_ownership.csv never updated after install (only genesis_bootstrap writes it)
- No verification that copied files match the archive
- INSTALLED written to ledger before proving the install succeeded
- No rollback mechanism for failed post-install validation

### Corrected Lifecycle

```
Pre-install              Execute              Validate              Commit
─────────────            ─────────────        ─────────────         ─────────────
G0B (system intact?)     Backup overwrites     Re-hash installed     Write INSTALLED to ledger
G0A (declared?)          Extract to workspace  files vs manifest       (FIRST — system truth,
G1  (chain valid?)       Copy files to root                             full asset detail)
G1-COMPLETE (wired?)                                                  Append file_ownership.csv
G5  (signature?)                                                        (append-only, history)
Auth (claims valid?)                           ON FAILURE:            Write receipt
                                               Rollback all files       (convenience snapshot)
                                               Write INSTALL_FAILED
                                               Clean state guaranteed
```

Key principles:
- **Ledger is system truth** — written FIRST in commit phase, contains full asset detail (same info as receipt). Read by many consumers; receipts are not.
- **INSTALLED is not written until validation passes.** The ledger becomes truthful — INSTALLED means "verified installed," not "probably installed."
- **file_ownership.csv is append-only** — never overwrite or remove entries. Uses `replaced_date` and `superseded_by` columns for complete history and audit trail.
- **Receipt is a convenience snapshot** — written last, not system truth.

### State-Gated Design (No File Replacement)

**Critical decision**: package_install.py and gate_check.py are NOT replaced by later packages. All capabilities ship in KERNEL-001/VOCABULARY-001 from the start, dormant until system state activates them:

| Capability | Ships In | Activation Gate |
|---|---|---|
| G0B (system integrity) | KERNEL-001 | Receipts exist in HOT/installed/ |
| G1-COMPLETE (framework completeness) | KERNEL-001 + VOCABULARY-001 | `try: import FrameworkCompletenessValidator` (ImportError = skip) |
| InstallerClaims auth | KERNEL-001 | `--dev` absent + HMAC secret configured |
| G5 (signature) | KERNEL-001 | Signing keys exist |

**Consequence**: GOVERNANCE-UPGRADE-001 no longer replaces any files. It ships only `test_framework_completeness.py` (1 asset). The file replacement pattern is eliminated — no package ever overwrites another package's files for the purpose of "upgrading" behavior.

**Why**: File replacement breaks provenance (who wrote this version?), makes the ledger ambiguous (which version was "installed"?), and is a category error — behavior should be state-gated, not file-gated.

### file_ownership.csv Schema

```
file_path, package_id, sha256, classification, installed_date, replaced_date, superseded_by
```

- New file → row with installed_date, empty replaced_date/superseded_by
- Ownership transfer (file moves from pkg A → pkg B) → new row for B + supersession row for A (replaced_date set, superseded_by = pkg B)
- Latest entry per file_path = current owner
- Full history preserved — never delete rows

### Rollback Design

If post-install validation fails:
1. Restore any files that were overwritten (from backup taken before copy)
2. Remove all newly copied files (tracked in installed_files list)
3. Clean up empty directories (stop at plane_root)
4. Write INSTALL_FAILED to ledger with validation details
5. Clean up workspace + backup dir
6. System is in the same state as before the install attempt

No half-installs. No orphaned files. Pristine.

### Builder Handoff

Full handoff: `_staging/BUILDER_HANDOFF_2_install_lifecycle.md`
- Phase 1: Upgrade KERNEL-001's package_install.py (9 changes)
- Phase 2: Merge G1-COMPLETE into VOCABULARY-001's gate_check.py
- Phase 3: Restructure GOVERNANCE-UPGRADE-001 (remove replacement assets)
- Phase 4: Rebuild cascade (KERNEL-001 → seed_registry → GENESIS-000 → VOCABULARY-001 → GOVERNANCE-UPGRADE-001 → CP_BOOTSTRAP)

---

## Prior Art & Reference Architecture (2026-02-10)

**Purpose**: Survey of our own prior design work across `AI_ARCH/`, `Brain_Garden/playground/docs/`, and the locked system. We are NOT adopting these implementations — we are rebuilding from scratch. This section captures patterns worth carrying forward.

### Agent Architecture (from AI_ARCH + docs/)

**BaseAgent contract** (`AI_ARCH/_locked_system_flattened/agents/base/agent.py`):
Every agent has: `name`, `description`, `capabilities` (list), `prompt_config` (routing rules). The base class enforces four mandatory behaviors:
1. Route all prompts through the prompt router (no direct LLM calls)
2. Scope context via attention envelopes (never raw file dumps)
3. Record all results to ledger (every action auditable)
4. Respect context boundaries (read/write permissions per class)

**Capability matrix** (`docs/CROSSCUTTING.md`, `AGENTS_STRICT_RULES.md`):

| Capability | KERNEL.syntactic | KERNEL.semantic | ADMIN | RESIDENT |
|---|---|---|---|---|
| Direct LLM calls | No | Yes (is the router) | Through router | Through router |
| Read kernel state | Yes | Yes | Yes (read all) | No |
| Write kernel state | Yes (own files) | No | No | No |
| Read resident state | No | Routing metadata only | Yes (read all) | Own namespace |
| Write resident state | No | No | Yes | Own namespace |
| Ledger write | Events only | Routing decisions | Observations | Work results |

**Firewall model** (`CP-FIREWALL-001_builder_vs_built.md`):
Three walls, not one. KERNEL writes kernel space. ADMIN reads everything, writes resident space only. RESIDENT reads/writes own namespace only. ADMIN is not a hole in the firewall — it's a watchtower outside the walls.

### Memory Model (from docs/MEMORY_MODEL_HO_TIERS.md)

Core principle: **"Agents don't REMEMBER, they READ."**

- No agent maintains internal state between sessions
- All persistent state lives in the ledger (append-only, immutable)
- Registries are **derived** — reconstructed from ledger + receipts on demand
- Anti-drift by design: if a registry diverges from the ledger, the registry is wrong, not the ledger
- This is why `rebuild_derived_registries.py` exists: it's the reconciliation mechanism

**Implication for Stage 2**: When an agent needs to "remember" a prior decision, it reads the ledger. Working memory = context window contents. Long-term memory = ledger queries. No other memory exists.

### Mandates as Work Orders (from AI_ARCH/Control_Plane/)

In prior art, agent mandates are formalized as **work orders** (WO-xxx):
- `scope`: What the agent is authorized to do (specific actions, not general permissions)
- `authorization`: Who approved this work, with cryptographic attestation
- `budget`: Token/turn limits for this specific task
- `tool_permissions`: Which tools/scripts the agent can invoke
- `input_schema` / `output_schema`: What it receives, what it must produce

Work orders are **recorded in the ledger** before execution begins. The agent can't do anything not in its work order. This is the answer to "what is a mandate?" — it's a signed, budgeted, scoped authorization document.

### The Shaper (from AI_ARCH/shaper/ + SPEC-011)

The shaper is a governance inspection agent — it evaluates whether prompts, outputs, and agent behaviors comply with governance rules.

**Altitude model** (from `shaper/router.py`):
Prompts are classified by altitude — how abstract vs. concrete:

| Altitude | Scope | Turn Budget | Keywords (detection) |
|---|---|---|---|
| L4 (Vision) | Why — goals, values, direction | 4 turns | vision, mission, purpose, north star, values |
| L3 (Design) | What — architecture, decisions | 3 turns | design, architecture, structure, plan, strategy |
| L2 (Implementation) | How — code, configuration | 2 turns | implement, build, code, configure, wire |
| L1 (Execution) | Now — specific actions | 1 turn | run, execute, deploy, install, fix |

**Key pattern**: Higher altitude = more turns allowed (more thinking time for abstract questions). Lower altitude = fewer turns (concrete actions should be quick). This is a budgeting mechanism disguised as routing.

**Shaper's 6 registered prompts** (PROMPT-001 through 006):
1. Evaluate governance compliance of a proposed change
2. Evaluate prompt contract adherence
3. Evaluate framework boundary respect
4. Evaluate resource budget compliance
5. Evaluate provenance chain integrity
6. Generate governance report

**Decision model**: Returns APPROVED/DENIED with structured reasoning (evidence, rule citations, confidence).

### Prompt Contract Framework (from SPEC-019 + SPEC-027)

**Core idea**: Prompts are not strings — they are versioned API contracts.

**Contract structure**:
- `prompt_id`: Unique identifier (PROMPT-xxx)
- `version`: Semantic version
- `input_schema`: JSON Schema defining what the prompt accepts
- `output_schema`: JSON Schema defining what the prompt must return
- `boundary`: Which boundary this prompt crosses (A, B, C, or D)
- `turn_budget`: Maximum turns for this interaction
- `required_context`: What attention envelope items are mandatory

**Four boundaries**:

| Boundary | Between | Example |
|---|---|---|
| A | LLM ↔ System | Agent sends prompt to Claude API, gets structured response |
| B | Agent ↔ Agent | ADMIN asks RESIDENT for status report |
| C | Human ↔ Agent | User gives instruction to ADMIN |
| D | System ↔ External | System calls external API or reads external resource |

**Exchange recording**: Every prompt/response pair is logged with:
- Prompt contract ID and version
- Input (redacted if sensitive)
- Output (full)
- Boundary crossed
- Token usage
- Timestamp
- Agent identity

**Implication**: The ledger records not just "agent did X" but "agent sent PROMPT-003 v1.2 across boundary A with input Y and got output Z using N tokens."

### Dual Validation Pattern (from SPEC-011 + shaper)

**Rule-based first (cheap), LLM second (semantic). Both must pass.**

```
Input → Syntactic validation (schema, types, bounds)
      → IF PASS → Semantic validation (LLM: does this make sense?)
      → IF BOTH PASS → Proceed
      → IF EITHER FAILS → Deny with structured reason
```

This maps directly to our KERNEL.syntactic / KERNEL.semantic split:
- KERNEL.syntactic does the cheap check first (gate_check, preflight, schema_validator)
- KERNEL.semantic does the expensive check second (only if cheap check passed)
- Both must pass before any action proceeds

### Three-Layer Cognitive Stack (from AI_ARCH/_locked_system_flattened/ARCHITECTURE.md)

```
Layer 3: Cognitive (RESIDENT agents — domain work)
    ↑ managed by
Layer 2: Administrative (ADMIN — lifecycle, monitoring, deployment)
    ↑ governed by
Layer 1: Infrastructure (KERNEL — deterministic + semantic services)
```

This confirms our four-class stack but adds the insight that **KERNEL is one layer with two sub-layers** (syntactic infrastructure + semantic services), not two separate layers.

### Patterns to Carry Forward

| Pattern | Source | Why It Matters |
|---|---|---|
| Prompts as versioned contracts | SPEC-019, SPEC-027 | Makes agent communication auditable and reproducible |
| Altitude-based routing + budgeting | Shaper router | Natural budgeting: abstract questions get more turns, concrete actions get fewer |
| Dual validation (syntactic → semantic) | SPEC-011, shaper | Cost-efficient: cheap checks first, expensive LLM only when needed |
| Ledger as sole memory | Memory model doc | Anti-drift: agents reconstruct, never cache. Registries are derived. |
| Work orders as mandates | Control_Plane specs | Scoped, budgeted, signed authorization — not open-ended permissions |
| Exchange recording | SPEC-027 | Full audit trail: prompt contract + input + output + tokens + identity |
| Four boundaries (A/B/C/D) | SPEC-019 | Different trust models for different communication paths |
| Capability matrix by class | CROSSCUTTING, FIREWALL | Not role-based — class-based. Each class has a fixed capability ceiling. |
| Turn budgets per altitude | Shaper router | Prevents runaway agents: bounded computation per abstraction level |

### What We're NOT Carrying Forward

- **Keyword-based altitude detection**: Too brittle. We'll need something better for routing.
- **Specific prompt IDs (PROMPT-001 etc.)**: These are from a different system. Our prompts will be registered through our own framework/spec system.
- **The locked system's agent base class**: Too coupled to their implementation. Our agents will be defined by frameworks, not inheritance.
- **Hardcoded shaper prompts**: Shaper's evaluation prompts should be governed like any other prompt — registered, versioned, auditable.

### 2026-02-10 — Session 2: Prior Art Research + Agent Definition

**What we did:**
1. Defined all four agent classes through 1-by-1 conversation (correcting initial misconceptions)
2. Surveyed prior architecture work across AI_ARCH/ and Brain_Garden/playground/docs/
3. Found extensive prior art: agent architecture, memory model, shaper router, prompt contracts, firewall design, crosscutting capabilities
4. Recorded findings as reference material (above) — not adoption, anchoring

**Key corrections during agent definition:**
- KERNEL.syntactic is NOT an agent — it's deterministic code (brainstem)
- KERNEL.semantic is NOT a governance evaluator — it's LLM-backed kernel services (prompt router, attention, flow runner, core learning). Shaper removed — good experiment, too hardcoded for kernel.
- ADMIN is NOT just advisory — full read everywhere, can manage residents, deploy packages, inspect logs
- RESIDENT is everything else — defined by non-kernel frameworks, the cognitive brain

**Key finding from prior art**: Most of the Stage 1.5 questions have prior art answers:
- "What is a mandate?" → Work orders (scoped, budgeted, signed)
- "What is context?" → Attention envelopes (structured, auditable, scoped by aperture)
- "How do you trust output?" → Dual validation (syntactic then semantic, both must pass)
- "Token budgeting?" → Altitude-based turn budgets + per-mandate limits

**Remaining for Stage 1.5**: Aperture lifecycle (OPEN→CLOSING→CLOSED in practice), agent identity model (separate from user identity?), and the specific question of which KERNEL.semantic services to build first for Stage 2.

### 2026-02-10 — Session 2 (continued): Infrastructure Inventory + Stage 2 Grounding

**What we did:**
1. Surveyed all existing kernel infrastructure: ledger_client.py (1063 lines), ledger_factory.py (617 lines), workspace.py, cursor.py, pristine.py, integrity.py, provenance.py, gate_operations.py, version management, registry operations
2. Discovered the gap to Stage 2 is much smaller than assumed — LedgerFactory already implements full work order lifecycle with cross-tier hash linkage
3. Inventoried 14 existing components that directly support agent operations
4. Identified 5 actual gaps: prompt router, work order schema, prompt contract schema, exchange recording format, agent identity model
5. Rewrote Stage 2 to be grounded in existing infrastructure: what gets built (new) vs. what gets reused (existing)
6. Defined concrete 11-step agent execution flow wired to existing ledger factory, workspace, pristine, and integrity infrastructure

**Key refinements:**
- Prompt router confirmed as dumb logging (not smart routing). Each prompt is single-shot. Context is fully assembled before it hits the router. Router just: log → send → log → return.
- Shaper confirmed removed from kernel services. Good experiment, too hardcoded.
- Core Learning deferred to Stage 3+ (research problem, not kernel primitive)
- Existing LedgerFactory work order lifecycle (WO_APPROVED → WO_STARTED → SESSION_SPAWNED → WO_EXEC_COMPLETE) IS the mandate infrastructure. Don't rebuild it.

**Critical context**: Prior agent sessions built this infrastructure but environments crack when agents drift. The clean bootstrap rebuild creates a stable foundation. Phase 2 must build ON existing work, not around it. Keep it clean and simple.

---

## The Memory Model Reframe (2026-02-10)

### HOT = Highest Order Thought

The tiers are not filesystem directories or execution scopes. They are **layers of memory** in an agentic cognitive framework:

| Tier | Memory Type | Cognitive Analog | Characteristics |
|---|---|---|---|
| **HO1** | Fast / working | Sensory buffer | One-shot, volatile, task-scoped. Single prompt, single response, done. |
| **HO2** | Session / episodic | Working memory | Work order duration. Context maintained across steps. Sequences HO1 tasks. |
| **HOT** | Meta / abstract | Declarative / semantic | Governance, long-term decisions, the "slow" thinking. Highest Order Thought. |

Chained HOT→HO2→HO1. Information flows down (abstract→concrete) during execution, and back up during consolidation/learning. The ledger chains aren't just audit trails — they're **memory consolidation pathways.**

Agents don't REMEMBER, they READ — the memory isn't inside the agent, it's the tier structure itself. An agent is a process that reads from memory, does work, and writes back to memory.

### Tier-Agent Interaction

- **HO1 agent**: One agent, one contract, one shot. Stateless worker.
- **HO2 agent**: Work order-scoped orchestrator. Exists for the WO duration. Sequences many HO1 agents.
- **HOT**: Kernel infrastructure (KERNEL.syntactic + KERNEL.semantic). Not agents — the machinery.

The **Flow Runner** (KERNEL.semantic) reads framework definitions and instantiates agents at the right tier. Frameworks define agents — the flow runner brings them to life. An HO2 agent doesn't create itself; the flow runner reads the framework and creates it.

### DoPeJar Flow (Concrete Example)

```
Human: "I need a job done"
    ↓
DoPeJar (RESIDENT, user-facing)
    │  Attention service reads memory: HOT → HO2 → HO1 ledgers
    │  "What is this related to? Is it new?"
    │  Each tier layer = a piece of the story
    │  Searches may be horizontal (across a tier) or vertical (across tiers)
    ↓
"This relates to your sim racing app"  ← behavior defined by frameworks
    │  User confirms
    ↓
Framework registry lookup → which dev frameworks fit?
    │  Prompt through router → prioritized list
    │  User approves
    ↓
Work order created → approved at HOT → sent to HO2
    ↓
Flow Runner (KERNEL.semantic) reads WO + framework definitions
    │  Instantiates HO2 agent from framework
    ↓
HO2 agent runs the work order
    │  May decompose into sub-HO2 jobs
    │  Sequences HO1 single-shot agents
    │  Each HO1: one contract, one prompt, done
```

DoPeJar doesn't have raw ledger access. It gets context through the **attention service** (KERNEL.semantic), which builds curated envelopes from all tiers. This preserves the firewall model while giving DoPeJar what it needs.

---

## Attention: The Biggest Gap (Deep Dive)

**Status**: Unsolved. The single biggest design gap. Prior art exists (7 working models in the locked system, plus HRM neural architecture patterns). The model has not been decided.

### Prior Art: Locked System Attention Pipeline

Source: `AI_ARCH/_locked_system_flattened/`

The locked system implements attention as a **10-layer pipeline**, not a single mechanism. Seven distinct models stacked:

| # | Layer | Mechanism | What Worked | What Was Hardcoded |
|---|---|---|---|---|
| 1 | Signal Detection | Regex → gate proposals | Fast first-pass triage | Regex patterns as constants |
| 2 | Emotional Telemetry | Confidence/frustration/urgency scoring | Routes by cognitive state | Signal keys as string literals |
| 3 | Signal→Gate Mapping | Converts signals to gate proposals | Clean separation | — |
| 4 | **Perception Agent** | **Fresh LLM call** on conversation history | **Chinese Wall: prevents context pollution** | Prompt hardcoded |
| 5 | **HRM Agent** | Reads ONLY perception output | **Blocked-topic registry with cooldowns** | Cooldown count (5) hardcoded |
| 6 | Lane Windowing | Active/paused lanes with bookmarks | **Elegant temporal scoping** | Lane types as enum |
| 7 | Memory Tiers | Working/Shared/Episodic/Semantic | **Compartment-based access policies** | Policies hardcoded |
| 8 | Altitude Depth | L1-L5 response control | **Prevents over/under-explanation** | Char thresholds (200-3000) hardcoded |
| 9 | Stance Constraints | Sensemaking/Execution/Evaluation state machine | **Behavioral gating** | Transitions hardcoded |
| 10 | Prompt Precedence | Three-tier immutable core laws | **Governance floor** | — |

Key files:
- `front_door/signals.py` — signal detection
- `the_assist/core/perception_agent.py` — Chinese Wall perception (fresh LLM call)
- `the_assist/core/hrm_agent.py` — strategic adjustment
- `lanes/gates.py` — lane windowing
- `core/memory_bus.py` — tiered memory
- `core/execution/executor.py` — altitude depth
- `slow_loop/gates.py` — stance constraints
- `core/execution/prompt_compiler.py` — prompt precedence

#### What Worked (Carry Forward)

1. **Chinese Walls**: Perception agent makes a FRESH API call — analyzes conversation from outside, no context pollution from prior state. This IS the single-shot pattern. Validates our prompt router design.
2. **Tiered memory compartments**: Working/Shared/Episodic/Semantic with different read/write policies. Prevents cross-contamination. Maps to our HO1/HO2/HOT model.
3. **Lane windowing**: Temporal scoping — one lane active, paused lanes preserve bookmarks. Elegant for multi-project context.
4. **Altitude**: Response depth scales with question abstraction. Prevents over-engineering simple questions.
5. **Prompt precedence**: Immutable core laws at highest tier. Governance floor that can't be overridden.

#### What Burned Us (Do Not Repeat)

**Nearly every layer has hardcoded values.** Regex patterns, topic saturation at "5+ mentions", altitude char limits (200/600/1200/2000/3000), cooldown counts (5 exchanges), lane types as enums, gate transitions embedded in methods, emotional signal keys as string literals, write gate thresholds (0.3/0.4/0.5/0.6).

**This is the primary pain point.** Hardcoded attention parameters are easy to write, work initially, then become impossible to tune or extend. Every one of these should have been config-driven from day one.

### Prior Art: HRM Neural Architecture

Source: `HRM_Test/models/hrm/hrm_act_v1.py`, `HRM_Test/models/layers.py`

The HRM is a 27M-param recurrent neural network for abstract reasoning (ARC puzzles, Sudoku, Mazes). Two modules — H (slow/abstract) and L (fast/detailed) — interact through a nested cycle:

```
For each H_cycle (default: 2):              ← HOT-level reasoning pass
    For each L_cycle (default: 2):          ← HO1-level detail passes
        z_L = L_level(z_L, z_H + input)    ← L refines using H's abstract view + raw input
    z_H = H_level(z_H, z_L)                ← H updates from refined details
```

Then a **Q-learning halting head** decides: stop or continue?

```python
q_logits = self.q_head(z_H[:, 0])          # [q_halt, q_continue]
halted = q_halt_logits > q_continue_logits  # Learned stopping criterion
```

#### Six Patterns That Map to Our System

**1. Dual-stream state separation.**
H and L maintain separate representations. H doesn't see raw input — it sees L's refined output. L sees H's abstract guidance + raw input. This IS the HOT/HO1 relationship.

**2. Asymmetric information flow.**
L attends to `z_H + input_embeddings` (abstract context + raw data). H attends only to `z_L` (refined details). HOT→HO1: guidance flows down. HO1→HOT: evidence flows up. Different function in each direction.

**3. Nested refinement, not single-pass.**
Multiple L cycles per H cycle. Agent equivalent: multiple HO1 single-shot tasks inform one HO2 step, which informs HOT-level state. The brain doesn't process once — it cycles.

**4. Learned halting (ACT).**
Q-learning head predicts "is the current solution sufficient?" vs "what's the value of continuing?" This is the **attention budget problem solved adaptively**. Not a fixed turn count — a learned decision about when you have enough context. Trained with exploration (ε-greedy, `halt_exploration_prob=0.1`) to prevent premature stopping.

**5. Task conditioning via puzzle embeddings.**
Task-specific meta-tokens prepended to the sequence without changing architecture. Agent equivalent: work order metadata / framework type prepended to context. Same mechanism, different tasks. No architectural change needed per task type.

**6. Carry state persists, then resets.**
z_H and z_L accumulate reasoning across iterations. When the halting flag fires, they reset to clean state for the next query. Agent equivalent: HO2 session state persists across HO1 tasks, resets when work order completes.

#### Memory Tier Mapping

| HRM | Locked System | Our System | Nature |
|---|---|---|---|
| z_H (high-level state) | Semantic memory | HOT | Abstract, slow, persistent |
| (no direct analog) | Episodic memory | HO2 | Session-scoped, contextual |
| z_L (low-level state) | Working memory | HO1 | Fast, volatile, task-scoped |
| input_embeddings | Shared memory | Raw input | Current stimulus |

HO2 is the piece HRM doesn't have — the session layer between abstract and fast. This is what makes the agent system richer than the neural model.

### Synthesis: What Attention IS in This System

Attention is not one mechanism. It's a **pipeline of decisions**:

| Decision | Question | Vertical/Horizontal |
|---|---|---|
| **Tier selection** | Which memory tiers to read from? | Vertical (HOT? HO2? HO1? All?) |
| **Horizontal search** | Within a tier, what's relevant? | Horizontal (search across a tier's breadth — meta, cross-project, cross-domain) |
| **Structuring** | How to organize selected context in the window? | Neither — it's assembly |
| **Halting** | Do I have enough context? | Adaptive (not fixed budget) |

Searches at HOT and HO2 may be **horizontal/meta in nature** — not drilling down, but searching across. A governance decision might check multiple policy areas at HOT level. A work order might reference multiple active projects at HO2 level. This is analogous to H's self-attention in HRM (each position attends to all positions at the same tier).

The attention service function: `(who, what, memory_tiers) → envelope`

- **who**: agent identity + class + framework
- **what**: current task / work order / user request
- **memory_tiers**: the full HOT→HO2→HO1 ledger stack
- **envelope**: curated context that fits in a context window

### Design Constraints (From Evidence)

1. **No hardcoding.** Every threshold, pattern, weight, and policy must be config-driven. This is the #1 lesson from the locked system. Validated across 7 layers of prior art.
2. **Pipeline, not function.** Attention is staged — multiple layers of selection that narrow iteratively. Not one call that picks everything.
3. **Adaptive budget.** Not fixed turn counts or token limits. The system should learn (or at least be configurable about) when it has enough context. HRM's Q-head halting is the reference pattern.
4. **Chinese Walls.** Each attention stage should be a clean single-shot evaluation. No context pollution from prior stages' internal state. Validates the prompt router design.
5. **Tier-aware.** Different tiers have different search patterns. HOT: horizontal/meta. HO2: session/temporal. HO1: task/immediate. The attention pipeline must know which tier it's reading and what kind of search applies.
6. **Auditable.** What was selected, what was excluded, and why — all recorded. The attention envelope itself is a governed artifact.

### For Stage 2 (Simple Start, No Hardcoding)

Stage 2 attention is hand-curated but **structured as config, not code**:

- A **query template** per agent type (YAML/JSON, not hardcoded in Python)
- Template specifies: which tiers to read, what event types, how many recent entries, what registries
- The "attention service" for Stage 2: read the template, execute the queries, format the results, hand to the agent
- No regex patterns. No magic numbers. No hardcoded thresholds.
- When we automate attention in Stage 3+, we replace the template with learned selection — but the interface stays the same

This way Stage 2 is simple but the door to adaptive attention is architecturally open.

### Adversarial Analysis of Attention Model (3-pass)

**Pass 1 — Not Enough:**

- **No learning mechanism.** Config-driven templates are better than hardcoding, but they're still static. How does the system learn which context selections lead to good agent outcomes? HRM learns halting through Q-values. We have no equivalent feedback loop.
- **No failure model for attention.** What happens when the attention service builds an envelope that's missing critical context? The agent produces a bad result, but how does anyone know the attention was the problem vs. the agent's reasoning? No way to distinguish "bad context" from "bad inference."
- **No cost model.** Reading from three tiers of ledger isn't free — ledger queries have latency, especially as ledgers grow. No modeling of attention cost or any way to trade off thoroughness vs. speed.
- **No eviction strategy.** The original Gap 1 analysis defined four operations: Filter, Promote, Evict, Interrupt. The current design addresses Filter (tier selection + horizontal search) but Evict (context full, what leaves?) and Interrupt (urgent, bypass normal filtering) are undefined.
- **No attention versioning.** When we change an attention template, prior agent runs used the old template. How do we audit "what attention model produced this result"? The envelope is logged, but the template version isn't.
- **No cross-agent attention.** What if ADMIN's attention envelope should include information about what a RESIDENT recently did? The tier model is vertical (HOT→HO2→HO1) but agent awareness is horizontal. No mechanism for one agent's attention to reference another agent's state.
- **Horizontal search is described but not specified.** "Search across a tier's breadth" — how? Full scan? Indexed? LLM-guided? The HOT ledger could be enormous. Searching horizontally across years of governance decisions isn't the same as searching across recent HO1 sessions.

**Pass 2 — Too Much:**

- **10-layer pipeline is over-engineered for Stage 2.** The locked system's 10 layers evolved over time. Starting with 10 layers is premature. Stage 2 needs: read template, run queries, format results. Three steps, not ten.
- **Adaptive halting is premature.** HRM's Q-head halting requires training data (correct vs. incorrect solutions) and gradient-based learning. We have no training pipeline and no ground truth for "correct attention." Fixed-but-configurable budgets are fine for Stage 2.
- **Tier-aware search patterns add complexity.** "HOT searches are horizontal/meta, HO1 searches are task/immediate" — this is elegant but adds a search-type dimension to every attention query. For Stage 2, all searches are the same: read recent entries matching event type filters.
- **Auditable envelopes as governed artifacts.** Logging what was selected is important, but making the envelope a full governed artifact (ID-allocated, spec-governed, framework-registered) is heavyweight. For Stage 2, log the envelope contents in the ledger entry metadata.
- **Chinese Walls between attention stages.** Valuable at scale, but for Stage 2 with one attention template and one agent, there's only one stage. Chinese Walls are a Stage 3+ concern.

**Pass 3 — Hurdles:**

- **Config-driven templates need a schema.** If attention templates are YAML/JSON, they need a defined schema. What fields are required? What tier names are valid? What event types can be queried? Without a schema, templates are just unvalidated strings — the same fragility as hardcoding, just moved to config.
- **Ledger query performance at scale.** The current LedgerClient has `read_recent()`, `read_by_event_type()`, `read_by_submission()`. Are these fast enough when ledgers have thousands of entries? The index system helps for submission lookups, but event-type filtering appears to be a full scan.
- **Template authoring.** Who writes the attention templates? The framework author? The admin? The user? If templates are per-agent-type, they need to be governed (versioned, auditable, part of a framework). This adds to the Stage 2 schema work.
- **HO2 horizontal search requires knowing what exists.** To search across active work orders at HO2, you need an index of work orders. `LedgerFactory.list_instances()` exists but returns filesystem paths, not a queryable index. For horizontal attention, we need richer indexing.
- **The "enough context" problem remains unsolved.** We said "adaptive, not fixed" but didn't say HOW. For Stage 2, the answer is "the template defines a fixed set of queries" — which is a fixed budget with extra steps. Genuinely adaptive attention is a research problem (HRM needed gradient-based training to learn it).

### Adversarial Synthesis: Attention

**The honest picture:**
- The attention pipeline design is correct in architecture (staged, tier-aware, config-driven, auditable)
- It is over-specified for Stage 2 and under-specified for Stage 3+
- The biggest risk is not the design — it's **premature complexity.** The locked system's 10 layers didn't start as 10 layers; they accumulated. We should start with 1 layer (template-driven query) and add layers only when evidence demands them

**For Stage 2:**
1. Attention template schema (YAML/JSON, validated by KERNEL.syntactic)
2. One template per agent type (hand-curated, governed as framework config)
3. Template executor: read template → run ledger queries → format → return envelope
4. Envelope logged in ledger entry metadata (not a separate governed artifact)
5. Template version recorded with envelope (for audit)

**For Stage 3+ (evidence-driven):**
- Which queries actually mattered? (→ informs template refinement)
- What was missing from envelopes? (→ informs additional queries)
- How fast are ledger queries at scale? (→ informs indexing needs)
- Do different agent types need fundamentally different attention? (→ informs pipeline stages)
- Can we learn halting? (→ only if we have ground truth for "good enough context")

### 2026-02-10 — Session 2 (continued): Attention Deep Dive

**What we did:**
1. Explored locked system attention models: found 7 distinct approaches stacked in a 10-layer pipeline
2. Explored HRM neural architecture: found H/L nested cycle, asymmetric attention, learned halting (ACT), carry state
3. Mapped HRM's dual-stream architecture to our HOT/HO1 memory tiers
4. Reframed tiers as layers of memory (fast/session/abstract), not filesystem directories
5. Established HOT = Highest Order Thought (the name's meaning)
6. Confirmed attention is a pipeline of decisions (tier selection → horizontal search → structuring → halting)
7. Established design constraints: no hardcoding, pipeline not function, adaptive budget, Chinese Walls, tier-aware, auditable
8. Ran 3-pass adversarial: correct architecture but over-specified for Stage 2, biggest risk is premature complexity

**Key findings:**
- Chinese Walls (fresh LLM call, no context pollution) validates our single-shot prompt router design
- H/L cycle IS the HOT/HO1 interaction: abstract guidance down, refined evidence up, cyclic
- HO2 is what HRM doesn't have — the session layer that makes agents richer than neural models
- Hardcoding is the #1 lesson from prior art: every pain point traces to a hardcoded value
- HOT/HO2 searches may be horizontal/meta (across a tier's breadth, not just drilling down)
- For Stage 2: config-driven templates, one per agent type, template executor, envelope in ledger metadata
- Adaptive halting deferred — requires training data we don't have

---

## Bottom-Up Signal Emergence (Concept — 2026-02-10)

### The Idea

Attention is not assigned only top-down. It also **emerges bottom-up** from repeated, useful activity.

Lower layers (HO1, HO2) do real work and generate many small signals — events in the ledger. At first, any single signal is weak (a neuron firing once). Over time, when:
- The same signals **recur**
- They appear in **multiple contexts**
- They are associated with **meaningful outcomes**
- They prove **useful for solving problems**

...those signals effectively get stronger. As they strengthen, higher layers pay more attention to them, route more activity through them, and are more likely to treat them as important.

**The critical firewall**: Weight ≠ authority. A signal can become very loud through bottom-up accumulation, but it takes a **deliberate higher-layer decision** to formalize it into policy or rule. Weight is a suggestion to pay attention, not a command to change governance. Adoption, when it happens, is a governed act — recorded in the ledger, traceable, reversible.

### Why This Matters for Attention

The attention pipeline currently has only top-down selection (templates say what to read). This adds **bottom-up salience** — the ledger itself tells the attention service "these patterns are getting louder." The attention envelope can then include both:
- What the template requested (top-down)
- What the signal weights suggest is important (bottom-up)

This is the missing bidirectional flow. The HRM's H/L cycle has it (H guides L, L informs H). The thalamocortical loop has it. Our attention pipeline needs it.

### Analogies

| System | Bottom-Up Signal | Weight Mechanism | Deliberate Adoption? |
|---|---|---|---|
| Hebbian learning | Neurons fire together | Synaptic strengthening | No — automatic (no firewall) |
| Global Workspace Theory | Broadly shared activity | Cross-region activation | Partially — competition for access |
| Common law | Individual case rulings | Precedent accumulates | **Yes** — higher courts formally adopt/overturn |
| Immune system | Antigen encounters | Clonal expansion | **Yes** — APC presentation required before full response |
| PageRank | Links from other pages | Authority propagation | **Yes** — Google can manually intervene |
| Linux kernel patches | Patches submitted | Discussion + testing traction | **Yes** — maintainers deliberately merge |
| RFC process | Implementations in the wild | Adoption + interop testing | **Yes** — IETF formalizes what works |

### What's Familiar vs. Unusual

**Familiar**: Bottom-up signal propagation (Hebbian), frequency as importance proxy (TF-IDF, PageRank), deliberate adoption at higher layers (common law, RFC), bidirectional hierarchy (thalamocortical loops).

**Unusual in combination**: The **deliberate firewall between weight and authority** applied to an **append-only ledger with governance tiers**. Most learning systems are either fully automatic (neural nets update weights without review) or fully manual (traditional governance declares from above). This is a hybrid: learning is automatic, adoption is deliberate. The ledger becomes simultaneously: immutable record (what happened), signal source (what patterns are emerging), and governance input (what should higher layers consider).

### Risks

1. **Gaming** — an agent could generate events to inflate a pattern. Mitigate by weighting signal by source diversity, not just frequency.
2. **Recency bias** — recent patterns seem strong because recent. Need temporal decay or normalization.
3. **Correlation ≠ causation** — co-occurring patterns aren't necessarily meaningful. Need outcome correlation, not just recurrence.
4. **Weight computation cost** — pattern detection across growing ledgers. Mitigate with incremental processing (CursorManager).
5. **Higher-layer fatigue** — too many weighted signals flood governance. Need prioritization of the signals themselves.
6. **Slow poison** — dangerous pattern accumulates gradually below alert threshold. Need rate-of-change detection, not just absolute weight.
7. **Adoption bottleneck** — governance can't review signals fast enough. Need prioritized presentation.
8. **Defining "meaningful outcome"** — requires valence (Gap 3). Without it, only recurrence and spread are measurable, not outcome quality.

### Where This Does NOT Exist

- Standard databases (all rows equal weight)
- Traditional event logs (events appended equally, no emergence)
- Standard neural networks (weight updates fully automatic, no governance firewall)
- Blockchain (all transactions equal weight, consensus is about validity not importance)

### Ledger Entry Schema for Loop Traversal

For the learning/meta/governance loops to work, every ledger entry must carry enough context that you don't have to chase references across files to answer "where did this come from and what else is related?"

#### Provenance Chain (trace any event to its origin)

| Field | What It Is | Why |
|---|---|---|
| `agent_id` | Which agent produced this event | "Agent X keeps failing" |
| `agent_class` | KERNEL.syntactic / .semantic / ADMIN / RESIDENT | Filter by class for pattern comparison |
| `framework_id` | Framework defining agent behavior | **Deep provenance** — traces signal to the framework that shaped the agent |
| `package_id` | Package whose code was executing | Traces to governed code — "every failure involves PKG-KERNEL-001 v1.0" |
| `work_order_id` | Under what mandate | Groups by authorization chain — the "why this happened" link |
| `session_id` | Within what session | Groups within an HO1 execution |

Full thread per event: **event → agent → framework → package → work order → session.** Any detected pattern traces all the way back.

**These fields double as natural indexes.** Query by framework_id = all events involving that framework, across all tiers, all time. Query by package_id = every event touching that package's code. Provenance IS the index.

#### Relational Links (what connects to what)

| Field | What It Is | Why |
|---|---|---|
| `parent_event_id` | Event that triggered this one | Tree traversal in either direction (up or down the chain) |
| `root_event_id` | Original trigger at top of chain | Shortcut: HO1 event → straight to HOT approval without walking the tree |
| `related_artifacts` | File paths / spec IDs / framework IDs touched | **Horizontal linking** — "these 3 events in different WOs all touch the same spec." Required for spread detection. |

`parent_event_id` gives a tree. `root_event_id` gives a shortcut. Together: bottom-up (what triggered this?) and top-down (what did this produce?). `related_artifacts` enables horizontal search across events at the same tier.

#### Context Fingerprint (what did the agent see and say?)

| Field | What It Is | Why |
|---|---|---|
| `context_hash` | Hash of the attention envelope used | Reproducibility — "what was the agent looking at when it decided?" |
| `context_sources` | Which tiers/queries contributed to envelope | Diagnoses attention failures — "did the agent see HOT governance or only HO1 data?" |
| `prompt_contract_id` | Which contract was invoked | Links to contract definition — "every failure uses CONTRACT-007, is the contract wrong?" |
| `prompt` | The actual prompt sent (or hash + retrievable reference) | **The full record.** What was asked, exactly. Required for the learning loops to evaluate whether the question was right, not just the answer. |
| `response` | The LLM response (or hash + reference) | What came back. Combined with prompt, enables full replay and post-hoc evaluation. |
| `tokens_used` | Token count for this exchange | Cost tracking + budget enforcement. Enables the resource model. |

The prompt and response are the most important fields for learning. Without them, you can see that an agent succeeded or failed, but not WHY. With them, the meta loop can evaluate: was the prompt well-formed? Was the context right? Was the response reasonable given the context? This is what makes post-hoc learning possible.

#### Outcome Linkage (did it work?)

| Field | What It Is | Why |
|---|---|---|
| `outcome` | success / failure / partial / pending | Raw result. Learning loops correlate patterns with outcomes. |
| `outcome_event_id` | Link to the event that determined outcome | Connects work to conclusion. SESSION_START → SESSION_END. WO_STARTED → WO_EXEC_COMPLETE. |

#### Scope Tags (search and classification)

| Field | What It Is | Why |
|---|---|---|
| `tier` | HOT / HO2 / HO1 | Filter by tier. Loops operate differently per tier. |
| `domain` | Area of work (framework-defined, optional) | Horizontal grouping — "all events related to sim racing" across WOs and agents. |
| `event_category` | governance / operational / diagnostic / signal | Noise filtering — operational loop skips governance events, meta loop reads signal events only. |

#### How Each Loop Uses These Fields

**HO2 operational loop** (fast, within one WO):
- `work_order_id + tier = HO1` → all worker events in this WO
- `framework_id + event_type = GATE_FAILED` → which framework keeps failing
- `parent_event_id` → walk up to WO-level decisions

**HOT governance loop** (slow, cross-WO):
- `framework_id + outcome = failure` → all failures involving a framework, ever
- `related_artifacts contains SPEC-025` → how many events touch this spec
- `package_id` → is kernel code involved in a pattern

**Meta loop** (slowest, self-evaluating):
- `event_category = signal + outcome_event_id IS NOT NULL` → signals with tracked outcomes
- `SIGNAL_ADOPTED events + their outcome_event_ids` → did adoptions improve outcomes
- `root_event_id` → trace any outcome to original trigger
- `prompt + response` on correlated events → evaluate whether the questions were right, not just the answers

#### Open Questions

1. **Weight on regular events vs. only on signal events?** Regular events carry provenance + context. Weight observations (`SIGNAL_OBSERVED`) carry computed weight + pattern description. Weight lives in the signal layer, not on raw events.
2. **Policy epoch markers?** When governance adopts a signal (changes a rule/template), should there be a `policy_epoch` counter that increments? Enables clean before/after queries: "all events in epoch 3 vs epoch 4" rather than timestamp ranges.

### Three Learning Loops (Summary)

```
Loop 1 — HO2 Operational (fast, per-WO)
    Pattern detection WITHIN a work order
    Reactive: HO2 adjusts sequencing based on HO1 signals
    Example: stop sending work to a failing template, try another

Loop 2 — HOT Governance (slow, cross-WO)
    Weight observations accumulate across many WOs
    ADMIN investigates, recommends policy/template changes
    Human reviews and approves → SIGNAL_ADOPTED (deliberate)

Loop 3 — Meta (slowest, self-referential)
    Tracks effectiveness of Loop 2 decisions
    "We adopted policy X based on signal Y. Did outcomes improve?"
    Reinforces or weakens signal→adoption pathways
    Guardrail: only humans can change discrimination parameters
```

**Signal vs. noise discrimination**: Dual detection (statistical first, semantic second). Statistical detector runs continuously and cheaply (KERNEL.syntactic — frequency, spread, anomaly from baseline). Semantic detector runs only when statistical detector flags something (KERNEL.semantic — LLM evaluates whether the anomaly is meaningful in context). Both must flag the same pattern for weight to increase significantly. Config-driven thresholds throughout — no hardcoding.

### 2026-02-10 — Session 2 (final): Signal Emergence + Ledger Schema

**What we did:**
1. Introduced bottom-up signal emergence concept: attention emerges from repeated, useful activity, not just top-down declaration
2. Analyzed through 5 lenses: own words, comparisons (neuroscience + CS + governance), familiar vs novel, risks, concrete examples
3. Identified the key novelty: deliberate firewall between weight (emergent) and authority (governed) applied to an append-only ledger
4. Designed three learning loops: HO2 operational (fast), HOT governance (slow), Meta (self-evaluating)
5. Defined dual detection for signal/noise: statistical first (cheap), semantic second (expensive), both must agree
6. Designed ledger entry schema with 6 field groups: provenance chain, relational links, context fingerprint (including prompt + response), outcome linkage, scope tags
7. Established that provenance fields ARE the indexes — no separate index structures needed, just richer per-entry metadata
8. Identified the prompt and response as the most important fields for learning loops — enables "was the question right, not just the answer"
