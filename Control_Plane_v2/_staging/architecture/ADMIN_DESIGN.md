# ADMIN Agent Design

**Status**: Current
**Created**: 2026-02-11
**Updated**: 2026-02-12
**Supersedes**: Session Host flat-loop model (Feb 11)
**Read after**: `SEMANTIC_ARCHITECTURE_PLAN.md`

---

## What ADMIN Is

ADMIN is a **governed chatbot interface** — a Claude-like experience for the Control Plane. It is the human admin's hands inside the governed world. Interactive, conversational, full visibility.

**ADMIN is NOT a batch-processing agent that receives work orders.** ADMIN's HO2 **creates** work orders and dispatches them to HO1 for execution. From the user's perspective, they type a message and get a response — the cognitive dispatch (HO2 planning, HO1 executing, work orders, prompt contracts) is invisible plumbing.

### The Experience

Human types a message. ADMIN sees everything in the Control Plane. ADMIN responds with insight, runs tools, manages residents, displays code, shows ledger history. Every turn is governed by work orders, prompt contracts, and ledger recording. The human stays in control.

Think: Claude Code, but governed. The governance is invisible from the user's perspective — it's the plumbing, not the product.

---

## What ADMIN Can See (Full Visibility)

- All kernel state (packages, gates, registries, schemas)
- All resident state (frameworks, deployments, configurations)
- Full ledger history (every event, every tier)
- Source code (read and display, LP-like commands)
- Package contents and provenance
- Gate status and integrity verification results

---

## What ADMIN Can Do

### Read Operations (CAP_READ_ALL)
- Read and display code from any governed file
- LP-like tracing commands (logic path through the codebase)
- Query ledger (by agent, session, work order, framework, outcome)
- List packages, frameworks, specs, registries
- Run gate checks and integrity verification
- Show system health (`am_i_intact()`, `what_am_i()`, `what_is_ungoverned()`)

### Write Operations (Resident Space Only)
- Deploy packages to resident tiers
- Create, configure, start, stop resident frameworks
- Manage resident agent lifecycle
- Write to ADMIN namespace / L-OBSERVE

### Forbidden
- Modify kernel space (ADMIN inspects the engine, doesn't modify it)
- Modify BUILDER (the Control Plane's own code)
- Self-promote or self-modify

### Tools (Implemented in main.py)

| Tool | What it does | Status |
|------|-------------|--------|
| `gate_check` | Run gate verification (single or all) | Done |
| `read_file` | Read any governed file (path-sandboxed to cp_root) | Done |
| `query_ledger` | Query governance ledger by event type | Done |
| `list_packages` | List installed packages | Done |

---

## What ADMIN Is NOT

| Wrong Mental Model | Correct Model |
|-------------------|---------------|
| Batch processor that receives work orders | Interactive chatbot whose HO2 *creates* work orders |
| Constrained agent that can only do a few things | Full agentic platform — a critical user experience |
| Cron job running `am_i_intact()` | Governed Claude Code for the Control Plane |
| A hole in the firewall | A watchtower outside the walls |

---

## Cognitive Dispatch (Replaces Flat Session Host)

### What changed

Session Host v1 (Feb 11) was a **flat loop**: attention → prompt router → Claude → tools → response. Every LLM call was a single unstructured pass. No planning, no work orders, no tier separation.

Session Host v2 (Feb 12, SEMANTIC_ARCHITECTURE_PLAN.md) replaces the inner loop with **HO2→HO1 cognitive dispatch**. The outer shell (CLI, I/O) stays. The guts get replaced.

### The Flow

```
Human types "show me all frameworks"
    ↓
Session Host (thin shell — HOT/kernel/session_host.py)
  Reads input. Passes raw text to HO2. Knows nothing else.
    ↓
HO2 Supervisor (HO2/kernel/ho2_supervisor.py)
  Assembles own context via Attention (reads HOTm + HO2m).
  Plans: what work orders do I need?
  Decision: [WO-001: classify intent] → [WO-002: tool call] → [WO-003: synthesize]
    ↓
HO1 Executor (HO1/kernel/ho1_executor.py) — executes each WO:
  WO-001 (classify): loads prompt contract → LLM call through HOT prompt router
    → returns: {intent: "list_frameworks", confidence: 0.95}
  WO-002 (tool_call): executes list_packages tool
    → returns: {packages: ["PKG-KERNEL-001", ...]}
  WO-003 (synthesize): loads greeting contract → LLM call through HOT prompt router
    → returns: {text: "Here are the 17 installed frameworks..."}
    ↓
HO2 Supervisor receives all results
  Quality gate: reviews WO-003 output → PASS
  Returns final text to Session Host
    ↓
Session Host prints response to human
```

### Session Host v1 vs v2

| Session Host v1 (flat loop — current) | Session Host v2 (cognitive dispatch — planned) |
|---------------------------------------|-----------------------------------------------|
| Assembles context itself | HO2 Supervisor + Attention assembles context |
| One LLM call per turn | Multiple work orders per turn (classify → tool → synthesize) |
| Tool use is single-round | HO1 Executor has multi-round tool loop per WO |
| No planning | HO2 plans work order chains |
| No quality gate | HO2 reviews results before returning |
| All logic in one file | Session Host = thin shell, HO2 = brain, HO1 = hands |

### What happened to Flow Runner?

**Absorbed.** Flow Runner (HANDOFF-5) was designed as a "single-shot batch executor" — a 9-step pipeline. The semantic architecture replaced it:
- HO2 Supervisor = orchestrates work orders (plans, dispatches, merges, quality gates)
- HO1 Executor = executes work orders (multi-round tool loop, prompt contracts, budget enforcement)

Together, HO2 + HO1 ARE the agent runtime that Flow Runner was supposed to be. HANDOFF-5 is SUPERSEDED.

### How LLM calls flow

All LLM calls are initiated by HO1 and flow through HOT infrastructure:

```
HO1 Executor → HOT/prompt_router (validate, log DISPATCH)
             → HOT/anthropic_provider (API wire)
             → LLM
             → HOT/anthropic_provider (parse response)
             → HOT/prompt_router (log EXCHANGE, debit budget)
             → HO1 Executor
```

HOT is the medium through which all cognition flows. HO1 never calls the LLM directly — it goes through HOT's prompt router, which logs everything.

---

## Component Registry

| Component | Package | Installs To | Status |
|-----------|---------|-------------|--------|
| Prompt Router | PKG-PROMPT-ROUTER-001 | HOT/kernel/ | Done |
| Token Budgeter | PKG-TOKEN-BUDGETER-001 | HOT/kernel/ | Done |
| Anthropic Provider | PKG-ANTHROPIC-PROVIDER-001 | HOT/kernel/ | Done |
| Attention Service | PKG-ATTENTION-001 | HOT/kernel/ (folding into HO2) | Done (redesign planned) |
| Session Host v1 | PKG-SESSION-HOST-001 | HOT/kernel/ | Done (to be rewired) |
| ADMIN Entry Point | PKG-ADMIN-001 | HOT/admin/ | Done |
| Boot Materialize | PKG-BOOT-MATERIALIZE-001 | HOT/scripts/ | Done |
| **Work Order Model** | PKG-WORK-ORDER-001 | HOT/kernel/ | **Planned** (HANDOFF-13) |
| **HO1 Executor** | PKG-HO1-EXECUTOR-001 | HO1/kernel/ | **Planned** (HANDOFF-14) |
| **HO2 Supervisor** | PKG-HO2-SUPERVISOR-001 | HO2/kernel/ | **Planned** (HANDOFF-15) |
| **Session Host v2** | PKG-SESSION-HOST-002 | HOT/kernel/ | **Planned** (HANDOFF-16) |
| **Shell UX** | PKG-SHELL-001 | HOT/shell/ | **Planned** (HANDOFF-17, lower priority) |
| Ledger Query | — | — | NOT DISPATCHED (HANDOFF-6) |
| Signal Detector | — | — | NOT DISPATCHED (HANDOFF-7) |
| Learning Loops | — | — | NOT DISPATCHED (HANDOFF-8) |

---

## Firewall Boundaries (from CP-FIREWALL-001 v1.1.0)

```
BUILDER (Control Plane kernel)
    │
    │  ADMIN reads everything, writes resident space only
    │  "A watchtower outside the walls"
    │
    ├── CAP_READ_ALL — read all tiers
    ├── CAP_AUDIT_WRITE — write to ADMIN namespace only
    ├── L-OBSERVE — log observations
    │
    │  FORBIDDEN:
    ├── Modify BUILDER
    ├── Modify BUILT
    └── Invoke other agents directly
```

---

## Critical Path

```
DONE:  17 packages, 8/8 gates, ADMIN first boot (talks to Claude)
DONE:  HANDOFF-12 + 12A (boot materialize + pristine fix)
NOW:   FMWK-008 (Work Order Protocol) — draft under review
NEXT:  FMWK-009, 010, 011 → HANDOFF-13 (PKG-WORK-ORDER-001)
       → HANDOFF-14/15 parallel (HO1 Executor + HO2 Supervisor)
       → HANDOFF-16 (Session Host rewire)
       → HANDOFF-17 (Shell UX — lower priority)
```

---

## Design Questions

### Answered

| # | Question | Answer |
|---|----------|--------|
| 1 | How does ADMIN authenticate? | `--dev` mode for now. Future: signed work orders. |
| 2 | Where does session state live? | HO2/ledger/workorder.jsonl — defined by FMWK-008. |
| 3 | Which tools first? | Done: read_file, query_ledger, gate_check, list_packages (main.py). |
| 4 | Tool use loop? | Lives in HO1 Executor — multi-round, budget-bounded, per-WO. |
| 5 | Boundary enforcement? | Per-WO constraints: token_budget, tools_allowed, prompt_contract_id (FMWK-008). |

### Open

| # | Question | Context |
|---|----------|---------|
| 6 | Aperture model integration? | OPEN→CLOSING→CLOSED defined in theory but no implementation mapping yet. |
| 7 | How does ADMIN manage RESIDENTs? | Packages create RESIDENTs. ADMIN monitors, doesn't dispatch to them. Flow Runner role absorbed. |
| 8 | Ledger efficiency? | FMWK-008 dual-ledger model under review — hash-anchored trace proposed. |

---

## Prior Art

| Document | Location | Status |
|----------|----------|--------|
| Agent class definition | `architecture/KERNEL_PHASE_2.md` lines 230-239 | Reference (Feb 10) |
| Semantic architecture plan | `architecture/SEMANTIC_ARCHITECTURE_PLAN.md` | Current (Feb 12) |
| Work order protocol | `FMWK-008_Work_Order_Protocol/work_order_protocol.md` | Draft (Feb 12) |
| Locked system shell | `~/AI_ARCH/_locked_system_flattened/shell/main.py` | Reference UX |
| Locked system CLI | `~/AI_ARCH/_locked_system_flattened/cli/main.py` | Reference UX |
