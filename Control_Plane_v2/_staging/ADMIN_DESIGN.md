# ADMIN Agent Design

**Status**: In Progress
**Created**: 2026-02-11
**Origin**: Live conversation during exchange recording / router testing session

---

## What ADMIN Is

ADMIN is a **governed chatbot interface** — a Claude-like experience for the Control Plane. It is the human admin's hands inside the governed world. Interactive, conversational, full visibility.

**ADMIN is NOT a batch-processing agent that receives work orders and executes them.** That mental model is exactly where things broke last time. ADMIN is a full agentic platform, not a constrained agent that can only do a few things. This is a critical user experience.

### The Experience

Human types a message. ADMIN sees everything in the Control Plane. ADMIN responds with insight, runs tools, manages residents, displays code, shows ledger history. Every turn is logged as an EXCHANGE in the ledger. The human stays in control.

Think: Claude Code, but governed. The governance is invisible from the user's perspective — it's the plumbing, not the product.

---

## What ADMIN Can See (Full Visibility)

- All kernel state (packages, gates, registries, schemas)
- All resident state (frameworks, deployments, configurations)
- Full ledger history (every EXCHANGE, every event, prompt + response text)
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

### Reference: Script Toolbox
From `docs/ADMIN_AGENT_SCRIPT_REF.md` — the existing script inventory that becomes ADMIN's tool set:
- Package lifecycle: `pkgutil.py`, `package_install.py`, `package_uninstall.py`
- Gates & integrity: `gate_check.py`, `integrity_check.py`
- Ledger & work orders: `trace.py`, `ledger_tier.py`, `apply_work_order.py`
- Plane/version: `cp_version_checkpoint.py`, `cp_version_list.py`, `cp_version_rollback.py`
- Registry: `rebuild_derived_registries.py`, `quarantine_orphans.py`

---

## What ADMIN Is NOT

| Wrong Mental Model | Correct Model |
|-------------------|---------------|
| Batch processor that receives work orders | Interactive chatbot with full CP visibility |
| Constrained agent that can only do a few things | Full agentic platform — a critical user experience |
| Cron job running `am_i_intact()` | Governed Claude Code for the Control Plane |
| A hole in the firewall | A watchtower outside the walls |

---

## Session Host (Replaces Flow Runner H5)

The Flow Runner (H5 v1) was designed as a **single-shot batch executor** — a 9-step pipeline that reads a work order, runs it, and exits. That's wrong for ADMIN.

ADMIN needs a **Session Host**: a governed chat loop.

```
Human types message
    ↓
Session Host receives input
    ↓
Attention service assembles context
  (ledger history, relevant files, system state)
    ↓
Prompt assembled with context + user message
    ↓
Prompt through router (logged as EXCHANGE — with prompt + response text)
    ↓
Claude responds (may include tool calls)
    ↓
Tools execute (read files, query ledger, run gates, etc.)
    ↓
Response displayed to human
    ↓
Loop back to top
```

Every turn: context assembled, prompt through router, response logged, tools executed. The router's EXCHANGE record captures the full conversation — prompt text, response text, outcome, cost. The ledger IS the session's memory.

### Session Host vs Flow Runner

| Flow Runner (H5 v1 — wrong) | Session Host (what we need) |
|------------------------------|----------------------------|
| Single-shot batch executor | Multi-turn chat loop |
| Reads WO, runs steps, exits | Hosts agent while it lives |
| No tool use loop | Tool use loop (Claude calls tools, tools execute, repeat) |
| No agent lifecycle | Creates agent's world, enforces boundaries, tears down on exit |
| 9-step pipeline | Governed chat loop with attention + routing |

### Key Design Decision
**Design ADMIN first, then build the Session Host around what ADMIN actually needs.** Don't build an abstract "flow runner" and hope ADMIN fits into it. That's backwards and it's where we went wrong before.

---

## Friendly Names (Translation Table)

| ID | Friendly Name | What It Is |
|----|--------------|------------|
| H3 | Prompt Router | Dumb logging gateway — log, send, log, return |
| H4 | Attention Service | Builds context envelopes — decides what an agent sees |
| H5 | Session Host | Governed chat loop (NOT "Flow Runner") |
| H6 | Ledger Query | Search and retrieve from the ledger |
| H7 | Signal Detector | Statistical + semantic anomaly detection |
| H8 | Learning Loops | HO2 operational, HOT governance, Meta self-evaluating |
| H9/9A | Anthropic Provider | Official SDK provider for Claude API |
| H10 | Exchange Recording | One EXCHANGE record per LLM call with prompt + response |

---

## UX Reference: Locked System

The locked system (`~/AI_ARCH/_locked_system_flattened/`) has the reference implementation:
- `shell/main.py` — Interactive shell with tool use
- `cli/main.py` — CLI entry point
- `cli/chat_ui.py` — Chat UI rendering

ADMIN should feel like this: type a message, get a response, tools execute transparently, full conversation visible. But governed — every exchange through the router, every tool call logged, budgets enforced, boundaries respected.

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

## Critical Path to First ADMIN Boot

```
DONE:  Router (H3) → Budgeter (H3) → Provider (H9/9A) → Schemas
NOW:   Exchange Recording (H10) — dispatched to agent
NEXT:  Validate Attention (H4)
THEN:  Design Session Host around ADMIN's actual needs
THEN:  Build ADMIN's tool set as governed tools
THEN:  First ADMIN boot — human types, ADMIN responds, everything logged
```

---

## Open Design Questions

1. **How does ADMIN authenticate the human?** Work order signed by whom? Or is ADMIN always running in `--dev` mode initially?
2. **Where does ADMIN's session state live?** HO2 tier — but the mechanics aren't designed. Session ledger? Session directory?
3. **Which tools does ADMIN get first?** Prioritize for first boot: read files, query ledger, run gates, LP commands?
4. **How does ADMIN's tool use loop work?** Claude's tool_use API? Or a custom tool dispatch? The provider already returns `content_blocks` with tool use support (AnthropicResponse).
5. **How does the Session Host enforce boundaries?** Budget limits per session? Tool permission lists? Aperture model (OPEN/CLOSING/CLOSED)?

---

## Prior Art Documents

| Document | Location | What It Contains |
|----------|----------|-----------------|
| ADMIN agent class definition | `KERNEL_PHASE_2.md` lines 230-239 | Reads everything, writes resident only, watchtower metaphor |
| Firewall spec | `docs/CP-FIREWALL-001_builder_vs_built.md` | CAP_READ_ALL, CAP_AUDIT_WRITE, forbidden operations |
| Script toolbox | `docs/ADMIN_AGENT_SCRIPT_REF.md` | Every script ADMIN can call |
| OS-level separation | `docs/TODO_ADMIN_SEPARATION.md` | Separate unix user, separate directories |
| Agent index | `docs/AGENT_INDEX.md` | CPInspector API, evidence pointers |
| Locked system shell | `~/AI_ARCH/_locked_system_flattened/shell/main.py` | Reference UX implementation |
| Locked system CLI | `~/AI_ARCH/_locked_system_flattened/cli/main.py` | CLI entry point reference |
