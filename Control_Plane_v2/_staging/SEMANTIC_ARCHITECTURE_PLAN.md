# Semantic Architecture Plan — Cognitive Dispatch Over Syntactic Infrastructure

**Date**: 2026-02-12
**Status**: DRAFT — pending user approval
**Scope**: 3 frameworks + 5 packages to lay HO2→HO1 cognitive dispatch over existing package infrastructure

---

## The Big Picture: Semantic Over Syntactic

What exists today is the **syntactic machine** — packages install, ledgers append, gates check checksums, files get owned. It works. It's governed. But it has no *understanding*. Session Host is a flat loop that forwards text to Claude and prints what comes back.

The semantic layer gives the machine **cognition** — intent, planning, dispatch, execution, quality. Same underlying infrastructure, but now the operations have *meaning*.

---

## Frameworks (policy in HOT — the "what" and "why")

### FMWK-008: Work Order Protocol
- Defines the work order as the atomic unit of cognitive dispatch
- Schema: `wo_id`, `type` (classify|execute|synthesize|tool_call), `tier_target` (HO1), `input_context`, `constraints`, `parent_wo` (for chaining)
- Lifecycle states: `planned → dispatched → executing → completed | failed`
- Ledger contract: every WO state transition gets a ledger entry
- Validation rules: WO must reference a session, must have bounded token budget, must specify tier

### FMWK-009: Tier Boundary Contract
- Governs what data crosses tier boundaries and how
- HOT → HO2: frameworks, policies, north stars (read-only from HO2's perspective)
- HO2 → HO1: work orders (structured, bounded, one-shot)
- HO1 → HO2: work order results (structured, must include cost/tokens/status)
- HO2 → HOT: governance events (ledger writes for audit)
- No skip-level: HO1 never reads HOT directly. HO2 assembles what HO1 needs.

### FMWK-010: Cognitive Stack Specification
- Defines what a "cognitive stack" is: one HO2 agent + one or more HO1 executors + their ledgers
- ADMIN gets one stack at boot. RESIDENTs get stacks via Flow Runner (later).
- Stack lifecycle: create → active → suspended → teardown
- Stack isolation: each stack has its own HO2 session ledger and HO1 worker ledgers
- Defines the contract between Session Host (outer shell) and HO2 (inner brain)

---

## Packages (implementation — the "how")

### Package 1: PKG-WORK-ORDER-001 (Layer 2 — foundation)
- `work_order.py` — WorkOrder dataclass, state machine, validation
- `wo_ledger.py` — WO-specific ledger entries (planned, dispatched, completed, failed)
- `wo_schema.json` — JSON schema for work order documents
- Tests: create WO, validate transitions, reject invalid state changes, ledger integration
- *This is the atom. Everything else depends on it.*

### Package 2: PKG-HO1-EXECUTOR-001 (Layer 3 — reactive/execution tier)
- `ho1_executor.py` — Takes a WorkOrder, executes it, returns result
  - `type: classify` → LLM call with classification prompt
  - `type: tool_call` → Execute registered tool, return structured result
  - `type: synthesize` → LLM call with synthesis/formatting prompt
  - `type: execute` → General LLM call with full context
- **Multi-round tool loop lives HERE** — if LLM responds with tool_use, HO1 loops until text response or budget exhaustion
- Writes every action to HO1 worker.jsonl (the canonical execution trace)
- Uses AnthropicProvider, Token Budgeter, existing tools
- *This is where ALL LLM calls happen. The single source of execution truth.*

### Package 3: PKG-HO2-SUPERVISOR-001 (Layer 3 — deliberative/supervisory tier)
- `ho2_supervisor.py` — The meta-cognitive controller
  - Receives user intent + assembled context from attention
  - **Plans**: decomposes intent into ordered work orders
  - **Dispatches**: sends WOs to HO1 executor, collects results
  - **Merges**: combines WO results into coherent response
  - **Gates**: quality check before returning to user (good enough? retry? escalate?)
- Writes to HO2 workorder.jsonl (session-scoped supervisory ledger)
- Implements orchestration modes (pipeline first):
  - **Pipeline** (v1): sequential WO chain — classify → tool → synthesize → done
  - Parallel, Voting, Hierarchical — future packages
- *This is the brain. It doesn't call LLMs itself — it tells HO1 what to do.*

### Package 4: PKG-SESSION-HOST-002 (Layer 3 — rewire the outer shell)
- Modifies `session_host.py` — keeps CLI I/O loop, REPLACES inner dispatch
- Old: `user_input → prompt_router → provider → response`
- New: `user_input → attention(context) → ho2_supervisor(intent, context) → [WO chain via HO1] → response`
- Session Host becomes a thin shell: read input, call HO2, print output
- Error handling: if HO2 fails, degrade to direct LLM call (backwards compat)
- *The surgery. Outer shell stays, guts get replaced.*

### Package 5: PKG-ATTENTION-002 (Layer 3 — context assembly redesign)
- Redesigns attention to be **tier-aware and config-driven**
- HO2 context assembly: frameworks from HOT, session history, package registry, recent governance
- HO1 context assembly: work order details + relevant subset (not everything)
- Config file: `attention_config.json` — defines what each tier sees, token budgets per tier
- Halting: if context exceeds budget, attention truncates by priority (frameworks > history > metadata)
- *This feeds the cognitive loop. Without good context, the brain is blind.*

---

## Dependency Graph

```
FMWK-008 (Work Order Protocol)
FMWK-009 (Tier Boundary Contract)
FMWK-010 (Cognitive Stack Spec)
    │
    ▼
PKG-WORK-ORDER-001          ← the atom, everything depends on this
    │
    ├──────────────┐
    ▼              ▼
PKG-HO1-EXECUTOR  PKG-ATTENTION-002   ← can build in parallel
    │              │
    └──────┬───────┘
           ▼
    PKG-HO2-SUPERVISOR      ← needs both HO1 + attention
           │
           ▼
    PKG-SESSION-HOST-002     ← the final rewire
```

## Handoff Sequence

| Order | Handoff | Package | Depends On | Why This Order |
|-------|---------|---------|------------|----------------|
| 1 | HANDOFF-13 | PKG-WORK-ORDER-001 | HANDOFF-12 (tiers exist) | Atom first. WO model used by everything. |
| 2a | HANDOFF-14 | PKG-HO1-EXECUTOR-001 | HANDOFF-13 | Needs WO model. Can parallel with 2b. |
| 2b | HANDOFF-15 | PKG-ATTENTION-002 | HANDOFF-13 | Needs WO model for tier-aware context. Can parallel with 2a. |
| 3 | HANDOFF-16 | PKG-HO2-SUPERVISOR-001 | HANDOFF-14 + 15 | Needs HO1 to dispatch to, attention for context. |
| 4 | HANDOFF-17 | PKG-SESSION-HOST-002 | HANDOFF-16 | The final rewire. Everything else must work first. |

Handoffs 14 and 15 can run in **parallel** (Gemini + Codex, or two Gemini sessions).

## The "Hello" Flow After All This

```
User: "Hello"
  → Session Host (outer shell, unchanged)
  → Attention assembles HO2 context: frameworks, session history, tools
  → HO2 Supervisor receives ("Hello", context)
    → HO2 plans: [WO-001: classify intent]
    → Dispatches WO-001 to HO1
      → HO1 Executor: LLM call #1 "Classify: Hello"     ← worker.jsonl
      → Returns: {type: "greeting", confidence: 0.95}
    → HO2 receives classification
    → HO2 plans: [WO-002: generate greeting response]
    → Dispatches WO-002 to HO1
      → HO1 Executor: LLM call #2 "Respond to greeting"  ← worker.jsonl
      → Returns: {text: "Hello! How can I help..."}
    → HO2 quality gate: pass                              ← workorder.jsonl
    → HO2 returns final text
  → Session Host prints to user
```

## DoPeJar Lineage

This architecture descends from the DoPeJar cognitive partner design:
- 4 HRM layers (Altitude, Reasoning, Focus, Learning) → tier selection, HO2, governance, future
- Memory Bus (Working Set, Shared Reference, Episodic Trace, Semantic Synthesis) → HO1, HOT, ledgers, HOT distilled
- "Reasoning Proposes, Focus Approves" → HO2 proposes, HOT governance approves
- 4 orchestration modes (Pipeline, Parallel, Voting, Hierarchical) → WO dispatch patterns

---

*This document is the specification for CP_2.1 Phase 3: Cognitive Architecture.*
