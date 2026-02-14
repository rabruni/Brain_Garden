# Semantic Architecture Plan — Cognitive Dispatch Over Syntactic Infrastructure

**Date**: 2026-02-12
**Status**: DRAFT — pending user approval
**Scope**: 4 frameworks + 5 packages to lay HO2→HO1 cognitive dispatch over existing package infrastructure

---

## The Big Picture: Semantic Over Syntactic

What exists today is the **syntactic machine** — packages install, ledgers append, gates check checksums, files get owned. It works. It's governed. But it has no *understanding*. Session Host is a flat loop that forwards text to Claude and prints what comes back.

The semantic layer gives the machine **cognition** — intent, planning, dispatch, execution, quality. Same underlying infrastructure, but now the operations have *meaning*.

### Path IS Boundary Enforcement

Code lives where it belongs in the tier hierarchy. The filesystem enforces who can access what:

| Directory | Who reads it | What lives there |
|-----------|-------------|-----------------|
| `HOT/kernel/` | Everyone (policy is shared) | Ledger client, gate ops, integrity, auth, work order model, prompt contracts |
| `HO2/kernel/` | HO2 agents (any cognitive stack) | Supervisor, attention, WO planning, context assembly |
| `HO1/kernel/` | HO1 agents (any cognitive stack) | Executor, prompt contract runner, tool dispatch |

Both ADMIN and RESIDENT stacks use the SAME `HO2/kernel/` and `HO1/kernel/` code. Different behavior comes from configuration and context, not different code.

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
- **Path enforcement**: HO2 code in `HO2/kernel/`, HO1 code in `HO1/kernel/`, shared contracts in `HOT/kernel/`

### FMWK-010: Cognitive Stack Specification
- Defines what a "cognitive stack" is: one HO2 agent + one or more HO1 executors + their ledgers
- ADMIN gets one stack at boot. RESIDENTs get stacks via Flow Runner (later).
- Stack lifecycle: create → active → suspended → teardown
- Stack isolation: each stack has its own HO2 session ledger and HO1 worker ledgers
- Defines the contract between Session Host (outer shell) and HO2 (inner brain)
- **Shared code, isolated state**: all stacks use `HO2/kernel/` and `HO1/kernel/`, differ by config and session

### FMWK-011: Prompt Contract Protocol
- Defines how LLM prompts are governed — no raw strings, contracts only
- Contract structure: ID, boundary, input schema, output schema, prompt template, validation rules
- HO1 executor loads contracts by ID, renders templates with `{{variable}}` syntax, validates I/O
- Every LLM call is auditable: contract ID + rendered prompt + validated output → ledger entry
- Reference implementation: `AI_ARCH/Control_Plane/lib/prompt_executor.py`

---

## Packages (implementation — the "how")

### Package 1: PKG-WORK-ORDER-001 (Layer 2 — foundation)
- **Installs to**: `HOT/kernel/` (shared contract, both tiers need it)
- `work_order.py` — WorkOrder dataclass, state machine, validation
- `wo_ledger.py` — WO-specific ledger entries (planned, dispatched, completed, failed)
- `wo_schema.json` — JSON schema for work order documents
- Tests: create WO, validate transitions, reject invalid state changes, ledger integration
- *This is the atom. Everything else depends on it.*

### Package 2: PKG-HO1-EXECUTOR-001 (Layer 3 — reactive/execution tier)
- **Installs to**: `HO1/kernel/`
- `ho1_executor.py` — Takes a WorkOrder, executes it, returns result
  - `type: classify` → LLM call via prompt contract
  - `type: tool_call` → Execute registered tool, return structured result
  - `type: synthesize` → LLM call via prompt contract
  - `type: execute` → General LLM call via prompt contract
- `prompt_contract_runner.py` — Loads contracts by ID, renders, validates I/O (based on FMWK-011)
- **Multi-round tool loop lives HERE** — if LLM responds with tool_use, HO1 loops until text response or budget exhaustion
- Writes every action to HO1 worker.jsonl (the canonical execution trace)
- Uses AnthropicProvider, Token Budgeter, prompt contracts
- *This is where ALL LLM calls happen. Every call governed by a contract. The single source of execution truth.*

### Package 3: PKG-HO2-SUPERVISOR-001 (Layer 3 — deliberative/supervisory tier)
- **Installs to**: `HO2/kernel/`
- `ho2_supervisor.py` — The meta-cognitive controller
  - Receives user intent + assembled context
  - **Plans**: decomposes intent into ordered work orders
  - **Dispatches**: sends WOs to HO1 executor, collects results
  - **Merges**: combines WO results into coherent response
  - **Gates**: quality check before returning to user (good enough? retry? escalate?)
- `attention.py` — Context assembly, folded into HO2 (not standalone)
  - Assembles HO2's own context: frameworks from HOT, session history, package registry
  - Assembles per-WO context for HO1: work order details + relevant subset (narrow, focused)
  - Config-driven: `attention_config.json` defines what each tier sees, token budgets
  - Halting: if context exceeds budget, truncates by priority (frameworks > history > metadata)
- Writes to HO2 workorder.jsonl (session-scoped supervisory ledger)
- Implements orchestration modes (pipeline first):
  - **Pipeline** (v1): sequential WO chain — classify → tool → synthesize → done
  - Parallel, Voting, Hierarchical — future packages
- *This is the brain. Attention is its eyes. It doesn't call LLMs itself — it tells HO1 what to do.*

### Package 4: PKG-SESSION-HOST-002 (Layer 3 — rewire the outer shell)
- **Installs to**: `HOT/kernel/` (it's the entry point, tier-neutral)
- Modifies `session_host.py` — keeps CLI I/O loop, REPLACES inner dispatch
- Old: `user_input → prompt_router → provider → response`
- New: `user_input → ho2_supervisor(intent) → [WO chain via HO1] → response`
- Session Host becomes a thin shell: read input, call HO2, print output
- Error handling: if HO2 fails, degrade to direct LLM call (backwards compat)
- *The surgery. Outer shell stays, guts get replaced.*

### Package 5: PKG-SHELL-001 (Layer 3 — rich CLI UX, lower priority)
- **Installs to**: `HOT/admin/` or `HOT/shell/`
- Brings in the locked system's CLI capabilities from `AI_ARCH/_locked_system_flattened/`
- Vim-style commands (`:help`, `:state`, `:quit`, `:trust`, `:learn`, `:signals`)
- iMessage-style chat UI with markdown rendering
- Activity/token tracking, session logging
- Multi-agent hot-swapping
- Universal outer shell that any cognitive stack (ADMIN, DoPeJar, future RESIDENTs) plugs into
- **Lower priority** — dispatch must work first. This is UX polish on a working cognitive loop.

---

## Dependency Graph

```
FMWK-008 (Work Order Protocol)
FMWK-009 (Tier Boundary Contract)
FMWK-010 (Cognitive Stack Spec)
FMWK-011 (Prompt Contract Protocol)
    │
    ▼
PKG-WORK-ORDER-001              ← the atom (HOT/kernel/)
    │
    ├──────────────┐
    ▼              ▼
PKG-HO1-EXECUTOR  PKG-HO2-SUPERVISOR   ← can build in parallel
(HO1/kernel/)     (HO2/kernel/)          (attention folded into HO2)
    │              │
    └──────┬───────┘
           ▼
    PKG-SESSION-HOST-002         ← the final rewire (HOT/kernel/)
           │
           ▼
    PKG-SHELL-001                ← UX layer (lower priority)
```

## Handoff Sequence

| Order | Handoff | Package | Installs To | Depends On | Why This Order |
|-------|---------|---------|-------------|------------|----------------|
| 1 | HANDOFF-13 | PKG-WORK-ORDER-001 | HOT/kernel/ | HANDOFF-12A (pristine fix) | Atom first. Shared contract. |
| 2a | HANDOFF-14 | PKG-HO1-EXECUTOR-001 | HO1/kernel/ | HANDOFF-13 | Needs WO model + prompt contracts. Can parallel with 2b. |
| 2b | HANDOFF-15 | PKG-HO2-SUPERVISOR-001 | HO2/kernel/ | HANDOFF-13 | Needs WO model. Attention folded in. Can parallel with 2a. |
| 3 | HANDOFF-16 | PKG-SESSION-HOST-002 | HOT/kernel/ | HANDOFF-14 + 15 | The final rewire. Both tiers must work first. |
| 4 | HANDOFF-17 | PKG-SHELL-001 | HOT/shell/ | HANDOFF-16 | UX polish. Lower priority. |

Handoffs 14 and 15 can run in **parallel** (Gemini + Codex, or two Gemini sessions).

## File Layout After All Packages

```
cp_root/
├── HOT/
│   ├── kernel/
│   │   ├── ledger_client.py        ← existing
│   │   ├── gate_operations.py      ← existing
│   │   ├── work_order.py           ← PKG-WORK-ORDER-001
│   │   ├── wo_ledger.py            ← PKG-WORK-ORDER-001
│   │   ├── session_host.py         ← PKG-SESSION-HOST-002 (rewired)
│   │   └── ...
│   ├── config/
│   │   ├── layout.json             ← existing
│   │   └── wo_schema.json          ← PKG-WORK-ORDER-001
│   ├── admin/                      ← existing (ADMIN entry point)
│   ├── prompts/
│   │   ├── contracts/              ← prompt contract .md files
│   │   └── schemas/                ← contract I/O schemas
│   └── ledger/governance.jsonl     ← existing (HOT governance)
│
├── HO2/
│   ├── kernel/
│   │   ├── ho2_supervisor.py       ← PKG-HO2-SUPERVISOR-001
│   │   ├── attention.py            ← PKG-HO2-SUPERVISOR-001 (folded in)
│   │   └── attention_config.json   ← context assembly config
│   ├── ledger/
│   │   ├── governance.jsonl        ← tier GENESIS (boot_materialize)
│   │   └── workorder.jsonl         ← session-scoped WO log
│   └── sessions/                   ← per-session state
│
├── HO1/
│   ├── kernel/
│   │   ├── ho1_executor.py         ← PKG-HO1-EXECUTOR-001
│   │   └── prompt_contract_runner.py ← PKG-HO1-EXECUTOR-001
│   ├── ledger/
│   │   ├── governance.jsonl        ← tier GENESIS (boot_materialize)
│   │   └── worker.jsonl            ← execution trace
│   └── sessions/                   ← per-session state
```

## The "Hello" Flow After All This

```
User: "Hello"
  → Session Host (thin shell in HOT/kernel/)
  → HO2 Supervisor (HO2/kernel/) assembles own context via attention
    → HO2 plans: [WO-001: classify intent]
    → Dispatches WO-001 to HO1
      → HO1 Executor (HO1/kernel/): loads classify contract     ← FMWK-011
      → LLM call #1 via contract                                ← worker.jsonl
      → Returns: {type: "greeting", confidence: 0.95}
    → HO2 receives classification
    → HO2 plans: [WO-002: generate greeting response]
    → Dispatches WO-002 to HO1
      → HO1 Executor: loads greeting contract                   ← FMWK-011
      → LLM call #2 via contract                                ← worker.jsonl
      → Returns: {text: "Hello! How can I help..."}
    → HO2 quality gate: pass                                    ← workorder.jsonl
    → HO2 returns final text
  → Session Host prints to user
```

## DoPeJar Lineage

This architecture descends from the DoPeJar cognitive partner design:
- 4 HRM layers (Altitude, Reasoning, Focus, Learning) → tier selection, HO2, governance, future
- Memory Bus (Working Set, Shared Reference, Episodic Trace, Semantic Synthesis) → HO1, HOT, ledgers, HOT distilled
- "Reasoning Proposes, Focus Approves" → HO2 proposes, HOT governance approves
- 4 orchestration modes (Pipeline, Parallel, Voting, Hierarchical) → WO dispatch patterns
- **PKG-SHELL-001** inherits the locked system's universal CLI — the same shell serves ADMIN today and DoPeJar tomorrow

---

*This document is the specification for CP_2.1 Phase 3: Cognitive Architecture.*
