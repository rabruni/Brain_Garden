# FMWK-010: Cognitive Stack Governance

## Purpose

FMWK-010 formalizes **Invariant #7** from KERNEL_PHASE_2_v2.md (v2 Section 10: Architectural Invariants):

> "Separate cognitive stacks per agent class. Each agent class (ADMIN, each RESIDENT) instantiates its own HO2 + HO1 cognitive processes. Shared code, isolated state. Different frameworks, different session state, different attention behavior. They share HO3 governance, KERNEL.syntactic, KERNEL.semantic, and the Meta Learning Ledger."

This framework defines **what is shared** (infrastructure accessible to all stacks), **what is isolated** (state unique to each stack), and **how stacks are instantiated** (factory pattern -- generic code, per-agent config).

Without this framework, builders risk creating a single shared HO2 instance that conflates ADMIN and RESIDENT state, or attention templates designed for one agent class bleeding into another. FMWK-010 makes the shared/isolated boundary a governed, enforceable rule.

## Scope

**FMWK-010 governs:**
- The boundary between shared infrastructure and isolated per-stack state
- The stack instantiation model (factory pattern)
- Session state structure for HO2m
- Directory isolation rules for per-stack files
- Attention template binding to stacks via the `applies_to` selector
- Cross-stack visibility rules
- Stack lifecycle (creation and teardown)

**FMWK-010 does NOT govern:**
- What HO2/HO1 cognitive processes do at runtime (HANDOFF-14: PKG-HO1-EXECUTOR-001, HANDOFF-15: PKG-HO2-SUPERVISOR-001)
- Tier boundary enforcement, visibility matrix, or syscall model (FMWK-009: Tier Boundary)
- Work order schema or lifecycle (FMWK-008A: Work Order Protocol)
- Prompt contract schema (FMWK-011: Prompt Contracts)
- Cross-agent-class communication (not needed -- stacks are isolated by design)

---

## 1. Shared Infrastructure

> Source: v2 Section 11 (Cognitive Stacks -- Shared Code, Isolated State), v2 Section 10 Invariant #7

All cognitive stacks share the following infrastructure. These components are NOT instantiated per stack -- they exist once and serve all stacks equally.

| # | Shared Component | What It Is | v2 Source |
|---|------------------|------------|-----------|
| S1 | **HO3 governance layer** | Principles, north stars, identity, long-horizon constraints. Same for all agent classes. | v2 Section 11: "HO3 governance layer (principles, north stars -- same for all)" |
| S2 | **KERNEL.syntactic** | Deterministic infrastructure: LLM Gateway, Gate Operations, Integrity/Merkle, Ledger Client, Auth/Authz, Pristine Enforcement, Token Budgeter, Schema Validator. All live in `HOT/kernel/`. | v2 Section 11: "KERNEL.syntactic (LLM Gateway, gates, integrity, auth)"; enumerated in v2 Section 8 (Infrastructure Components) |
| S3 | **KERNEL.semantic** | LLM-backed kernel capabilities. Currently: cross-cutting meta agent (Global Workspace/Observer) that reads all stacks. | v2 Section 11: "KERNEL.semantic (meta agent reads all stacks)" |
| S4 | **Meta Learning Ledger** | Graph-indexed, stored in HOT, cross-cutting. Structural credit assignment and cross-tier learning artifacts. | v2 Section 11: "Meta Learning Ledger (cross-cutting)"; v2 Section 6 (Memory Architecture) |

### Why These Are Shared

These four components are system-level infrastructure. They do not carry per-agent state:

- **HO3 governance** sets the same principles and constraints for all agent classes. An ADMIN stack and a RESIDENT stack operate under the same governance rules.
- **KERNEL.syntactic** is deterministic code. All stacks call the same LLM Gateway, the same ledger client. The isolation is in *state*, not in *code* (v2 Section 11 build implication).
- **KERNEL.semantic** meta agent reads *across* all stacks by design -- it needs cross-stack visibility to detect cross-tier patterns (v2 Section 4: Agent Classes, KERNEL.semantic definition).
- **Meta Learning Ledger** captures patterns that span stacks. Isolating it would defeat its purpose.

---

## 2. Isolated State

> Source: v2 Section 11 (Cognitive Stacks -- Shared Code, Isolated State), v2 Section 10 Invariant #7

Each cognitive stack maintains the following state in isolation. No stack can access another stack's isolated state (with the exception of KERNEL.semantic's cross-cutting read access -- see Section 7).

| # | Isolated Component | What It Is | v2 Source |
|---|-------------------|------------|-----------|
| I1 | **HO2m session state** | Work order orchestration, arbitration outcomes, escalation events, meta-episodes, session state for this stack's HO2 cognitive process. | v2 Section 11: "HO2m session state"; v2 Section 6 (Memory Architecture): HO2m contents |
| I2 | **HO1m execution traces** | Canonical episodic trace for this stack's HO1 cognitive process. Every LLM call, tool execution, and work order result. | v2 Section 11: "HO1m execution traces"; v2 Section 6: HO1m contents |
| I3 | **Attention templates** | Config-driven templates that control how this stack's HO2 cognitive process assembles context. Bound via the `applies_to` selector. | v2 Section 11: "Attention templates"; v2 Section 7 (Attention -- HO2's Retrieval Function): design constraint #2 |
| I4 | **Framework configuration** | Per-agent framework settings. Different agent classes may have different framework configurations even when referencing the same framework IDs. | v2 Section 11: "Framework configuration" |
| I5 | **Work order context** | The assembled input context, constraints, and results for work orders dispatched within this stack. | v2 Section 11: "Work order context"; v2 Section 17 (Work Order Schema) |

### Isolation Means State Isolation, Not Code Isolation

The HO2 cognitive process code is written ONCE as generic code. Each agent class instantiates its own copy with different config. Like a class vs instance (v2 Section 11, build implication).

All stacks call the same KERNEL.syntactic services (LLM Gateway, Ledger Client, etc.). What is isolated is the session state, traces, templates, and context -- not the code paths through shared infrastructure.

### Completeness Check

The shared list (S1-S4) and isolated list (I1-I5) are:
- **Mutually exclusive**: No component appears in both lists.
- **Collectively exhaustive**: Every component mentioned in v2 Section 11 and Invariant #7 appears in exactly one list.

---

## 3. Stack Instantiation Model

> Source: v2 Section 11 (Cognitive Stacks -- Shared Code, Isolated State), build implication

### The Factory Pattern

Each cognitive stack is created by instantiating the same generic HO2 + HO1 cognitive process code with agent-class-specific configuration:

```
CognitiveStack = factory(
    agent_class:    "ADMIN" | "RESIDENT:<name>",
    config: {
        attention_templates:  [ATT-ADMIN-001, ...]  or  [ATT-DPJ-001, ...],
        framework_config:     {per-agent framework overrides},
        ho2m_path:            "HO2/ledger/<agent_class>/workorder.jsonl",
        ho1m_path:            "HO1/ledger/<agent_class>/worker.jsonl",
        session_id:           "SES-<uuid>",
        budget_ceiling:       <tokens allocated by HO3>
    }
)
```

### What the Factory Produces

For each agent class, the factory produces:

| Component | What | Lifecycle |
|-----------|------|-----------|
| HO2 cognitive process instance | Deliberative supervisor: plans, arbitrates, dispatches, verifies | Session-scoped |
| HO1 cognitive process instance | Reactive executor: fires LLM calls, produces traces | Work-order-scoped (stateless beyond WO) |
| HO2m partition | Isolated ledger partition for this stack's orchestration state | Persistent, append-only |
| HO1m partition | Isolated ledger partition for this stack's execution traces | Persistent, append-only |
| Attention template set | Bound templates selected by `applies_to.agent_class` | Loaded at stack creation, reloaded on config change |

### What the Factory Does NOT Prescribe

FMWK-010 defines WHAT is shared vs isolated and THAT the factory pattern is used. It does NOT prescribe:
- The factory's API signature or return type
- Internal data structures of HO2 or HO1 cognitive processes
- Runtime threading or concurrency model

These are implementation details belonging to HANDOFF-15 (PKG-HO2-SUPERVISOR-001).

### Concrete Example: Two Stacks

> Source: v2 Section 11 stack diagrams, v2 Section 14 (Concrete Flows)

```
ADMIN Cognitive Stack:
    ADMIN-HO3 --> uses shared HO3 governance + admin-specific frameworks
    ADMIN-HO2 --> admin-specific attention, arbitration, dispatch
    ADMIN-HO1 --> executes admin tool calls + LLM calls

DoPeJar Cognitive Stack:
    DPJ-HO3  --> uses shared HO3 governance + DoPeJar-specific frameworks
    DPJ-HO2  --> DoPeJar-specific attention, arbitration, dispatch
    DPJ-HO1  --> executes DoPeJar LLM calls
```

Both stacks share HO3 governance, KERNEL.syntactic, KERNEL.semantic, and the Meta Learning Ledger. Each has its own HO2m, HO1m, attention templates, framework config, and WO context.

---

## 4. Session State Structure

> Source: v2 Section 6 (Memory Architecture), v2 Section 7 (Attention -- HO2's Retrieval Function), v2 Section 3 (Three Things Per Tier)

HO2m is the per-stack session state ledger for the HO2 cognitive process. It is session-scoped (v2 Section 3: HO2 cognitive process is "session-scoped") and append-only (v2 Section 6: Memory Principles).

### HO2m Fields

Each HO2m entry contains the following information. These are logical fields -- physical storage follows the ledger entry metadata schema from FMWK-008A.

| Field | Type | Description | v2 Source |
|-------|------|-------------|-----------|
| `session_id` | string | Unique session identifier. Format: `SES-<uuid>`. | v2 Section 17: every WO references a session_id |
| `agent_class` | string | Which agent class owns this session. `"ADMIN"` or `"RESIDENT:<name>"`. | v2 Section 4 (Agent Classes), v2 Section 11 |
| `work_order_log` | array | Ordered list of WO IDs dispatched in this session, with lifecycle state. | v2 Section 6: HO2m contains "Work order orchestration" |
| `arbitration_outcomes` | array | Memory arbitration results: candidates scored, must-mention vs options, strategy chosen. | v2 Section 7: "All arbitration outcomes logged to HO2m"; v2 Section 6: HO2m contains "Arbitration outcomes" |
| `escalation_events` | array | Events where HO2 escalated (verification failure, budget exhaustion, unrecoverable error). | v2 Section 6: HO2m contains "Escalation events" |
| `meta_episodes` | array | Higher-order observations about the session (e.g., "user changed topics 3 times"). | v2 Section 6: HO2m contains "Meta-episodes" |
| `attention_state` | object | Current attention context: what was retrieved, what was excluded, and why. | v2 Section 7: attention design constraint #3 ("Auditable") |
| `active_templates` | array | Template IDs currently bound to this stack. | v2 Section 7: design constraint #2 ("Config-driven templates") |

### Working Memory (M1)

> Source: v2 Section 6 (Memory Store Mapping)

M1 is the working memory for the current turn -- the HO2 cognitive process's active state. It is ephemeral within the session (not persisted across sessions). M1 maps to HO2m's session-scoped entries.

| Store | What | Tier | Nature |
|-------|------|------|--------|
| M1 | Working memory (HO2 active state for this turn) | HO2 | Session-scoped |

### Persistence Rule

HO2m entries are append-only and persistent within a session. Between sessions, HO2m is queryable (agents READ, they don't remember -- v2 Section 6, Memory Principles, Invariant #3). The HO2 cognitive process has no internal state between sessions; all persistent state is ledger queries.

---

## 5. Directory Isolation

> Source: v2 Section 3 (Three Things Per Tier), layout.json (PKG-LAYOUT-002)

Each stack's isolated state lives in agent-class-scoped subdirectories within the tier layout defined by `layout.json`.

### Tier Directory Structure (from layout.json)

The base tier directories are:

| Tier | Path | v2 Source |
|------|------|-----------|
| HO3 (HOT) | `HOT/` | v2 Section 2: "HO3 (codebase: `HOT/`)" |
| HO2 | `HO2/` | v2 Section 2: "HO2 (codebase: `HO2/`)" |
| HO1 | `HO1/` | v2 Section 2: "HO1 (codebase: `HO1/`)" |

Standard subdirectories per tier (from `layout.json` `tier_dirs`): `registries/`, `installed/`, `ledger/`, `packages_store/`, `scripts/`, `tests/`, `spec_packs/`.

### Per-Stack Isolation Within Tiers

Each agent class gets a scoped partition within the tier ledger directories:

```
HO2/
  ledger/
    ADMIN/
      workorder.jsonl          # ADMIN stack's HO2m
    RESIDENT_DoPeJar/
      workorder.jsonl          # DoPeJar stack's HO2m

HO1/
  ledger/
    ADMIN/
      worker.jsonl             # ADMIN stack's HO1m
    RESIDENT_DoPeJar/
      worker.jsonl             # DoPeJar stack's HO1m
```

### Shared Infrastructure Paths

Shared components live in `HOT/` (the HO3 tier directory):

| Component | Path | Source |
|-----------|------|--------|
| KERNEL.syntactic | `HOT/kernel/` | v2 Section 8 (Infrastructure Components) |
| HO3 governance | `HOT/ledger/governance.jsonl` | layout.json `ledger_files.governance` |
| Meta Learning Ledger | `HOT/ledger/meta_learning.jsonl` | v2 Section 6: "Stored in HOT, cross-cutting" |
| Schemas | `HOT/schemas/` | layout.json `hot_dirs.schemas` |
| Config | `HOT/config/` | layout.json `hot_dirs.config` |

### Path IS Boundary

> Source: v2 Section 3 (Three Things Per Tier), FMWK-009 (Tier Boundary) design principle #3

Code lives where it belongs. Directory structure enforces tier membership. Per-stack state lives in agent-class-scoped subdirectories. FMWK-009 defines the enforcement mechanism (path convention + gate checks); FMWK-010 defines the per-stack directory structure within that mechanism.

---

## 6. Attention Template Binding

> Source: v2 Section 7 (Attention -- HO2's Retrieval Function), v2 Section 11 (Cognitive Stacks), `attention_template.schema.json` (PKG-PHASE2-SCHEMAS-001)

Attention templates are the primary mechanism by which the same HO2 cognitive process code produces different behavior for different agent classes. Templates are isolated per stack (I3 in Section 2) and bound via the `applies_to` selector.

### The `applies_to` Selector

> Source: `attention_template.schema.json`, properties.applies_to

The `applies_to` field in `attention_template.schema.json` is an object with three optional selector properties:

| Property | Type | Values | Purpose |
|----------|------|--------|---------|
| `agent_class` | array of string | `"KERNEL.syntactic"`, `"KERNEL.semantic"`, `"ADMIN"`, `"RESIDENT"` | Which agent classes this template applies to |
| `framework_id` | array of string | Pattern: `^FMWK-[A-Z0-9-]+$` | Which specific frameworks this template applies to |
| `tier` | array of string | `"hot"`, `"ho2"`, `"ho1"` | Which tiers this template is active in |

### Binding Rules

1. **At stack creation**, the factory queries all available attention templates and selects those whose `applies_to.agent_class` includes the stack's agent class.
2. **Multiple selectors are conjunctive.** If a template specifies both `agent_class: ["ADMIN"]` and `tier: ["ho2"]`, it applies only to the ADMIN stack's HO2 cognitive process.
3. **Templates are loaded, not copied.** The template definitions live in `HOT/schemas/` (shared). The *binding* -- which templates are active for a given stack -- is part of the stack's isolated state.
4. **No hardcoding.** Every threshold, pattern, and weight in a template is config-driven (v2 Section 7, design constraint #1).

### Example: ADMIN vs DoPeJar Templates

```json
{
  "template_id": "ATT-ADMIN-001",
  "applies_to": {
    "agent_class": ["ADMIN"],
    "tier": ["ho2"]
  },
  "pipeline": [
    {"stage": "tier_select", "type": "tier_select", "config": {"tiers": ["hot", "ho2", "ho1"]}},
    {"stage": "registry_scan", "type": "registry_query", "config": {"target": "frameworks_registry.csv"}}
  ]
}
```

```json
{
  "template_id": "ATT-DPJ-001",
  "applies_to": {
    "agent_class": ["RESIDENT"],
    "tier": ["ho2"]
  },
  "pipeline": [
    {"stage": "horizontal_scan", "type": "horizontal_search", "config": {"source": "ho2m", "limit": 10}},
    {"stage": "priority_probe", "type": "ledger_query", "config": {"source": "ho3m", "filter": "salience_anchors"}}
  ]
}
```

ADMIN's template scans registries (system inspection). DoPeJar's template performs horizontal scan + priority probe (user-facing memory arbitration). Same HO2 code, different behavior via config.

### Template Validation

Templates are validated by KERNEL.syntactic (Schema Validator) against `attention_template.schema.json` at template load time. Invalid templates fail-closed -- the stack does not start with an invalid template.

---

## 7. Cross-Stack Visibility

> Source: v2 Section 5 (The Visibility / Syscall Model), v2 Section 4 (Agent Classes), v2 Section 11 (Cognitive Stacks)

### Visibility Rules

| Observer | Can See | Cannot See | v2 Source |
|----------|---------|------------|-----------|
| ADMIN stack | Own HO2m, own HO1m | Any RESIDENT stack's HO2m or HO1m | v2 Section 4: "Cannot interact with resident agents directly" |
| RESIDENT stack | Own HO2m, own HO1m | ADMIN stack's HO2m or HO1m; any other RESIDENT stack's HO2m or HO1m | v2 Section 4: "Own namespace" |
| KERNEL.semantic (meta agent) | All stacks' HO2m and HO1m | N/A -- cross-cutting read access by design | v2 Section 11: "KERNEL.semantic (meta agent reads all stacks)"; v2 Section 4: "reads across all tier ledgers" |
| HO3 governance | All stacks' HO2m and HO1m | N/A -- highest tier sees all | v2 Section 5: "HO3 sees All: HO3m + HO2m + HO1m + Meta ledger" |

### Key Constraints

1. **ADMIN cannot see RESIDENT state.** ADMIN has CAP_READ_ALL for *tier-level* ledgers, registries, manifests, and governed files (v2 Section 4, ADMIN Capability Matrix). But ADMIN's cognitive stack cannot access a RESIDENT stack's isolated session state. ADMIN observes the system through its own cognitive stack.

2. **RESIDENT cannot see ADMIN state.** Each RESIDENT stack operates in its own namespace. It sees the world through its own attention envelopes (v2 Section 4: RESIDENT definition).

3. **No cross-RESIDENT visibility.** If multiple RESIDENT stacks exist, they cannot see each other's state.

4. **KERNEL.semantic is the only cross-stack reader.** The cross-cutting meta agent reads across all stacks to detect patterns and write to the Meta Learning Ledger. This is infrastructure-level read access, not agent-level communication.

### Relationship to FMWK-009

Cross-stack visibility is enforced through the same tier boundary mechanism that FMWK-009 governs. FMWK-010 defines the per-stack isolation *rules*. FMWK-009 defines the enforcement *mechanism* (path convention, gate checks, syscall wrappers). If a gap in enforcement is discovered, it should be flagged to FMWK-009 -- not filled by FMWK-010.

---

## 8. Stack Lifecycle

> Source: v2 Section 6 (Memory Architecture, Memory Principles), v2 Section 3 (Three Things Per Tier), v2 Section 10 Invariant #3

### Lifecycle Phases

| Phase | Trigger | What Happens |
|-------|---------|--------------|
| **Creation** | Session start or agent class activation | Factory instantiates HO2 + HO1 cognitive processes. Attention templates loaded via `applies_to` selector. HO2m partition initialized. Session ID assigned. |
| **Active** | User interaction within session | HO2 cognitive process plans, dispatches WOs to HO1, verifies results. HO2m and HO1m accumulate entries. Attention templates drive context assembly. |
| **Teardown** | Session end or explicit deactivation | Cognitive process instances released. HO2m and HO1m entries remain (append-only, persistent). No state deleted. |
| **Recovery** | New session for same agent class | New stack instance created. HO2 cognitive process reads prior HO2m and HO1m entries via ledger queries. No internal state carried over. |

### Invariant #3 Compliance

> "Agents don't remember -- they READ. No internal state between sessions. All persistent state = ledger queries + attention retrieval." (v2 Section 10)

Stack teardown does NOT delete ledger entries. When a new session begins for the same agent class, the new HO2 cognitive process instance reads previous HO2m entries to reconstruct context. The stack itself is ephemeral; the ledger is persistent.

### Degradation During Active Phase

> Source: v2 Section 1 (Grounding Model), degradation behavior

If the Kitchener loop fails during the active phase (HO2 unavailable, budget exhausted, unrecoverable error):
- Degrade to direct LLM call through LLM Gateway (backwards compatible with Session Host v1)
- Log degradation event to HO1m
- No silent failure -- degradation is always recorded

---

## 9. Implementation Mapping

> Source: v2 Section 18 (Critical Path -- What's Next), FMWK-010 handoff spec Section 5

FMWK-010 is a governance framework. It defines rules that are implemented by packages on the critical path.

| FMWK-010 Rule | Implementing Package | Handoff |
|----------------|---------------------|---------|
| Stack instantiation (factory pattern) | PKG-HO2-SUPERVISOR-001 | HANDOFF-15 |
| HO2 cognitive process behavior | PKG-HO2-SUPERVISOR-001 | HANDOFF-15 |
| HO1 cognitive process behavior | PKG-HO1-EXECUTOR-001 | HANDOFF-14 |
| Session state structure (HO2m) | PKG-HO2-SUPERVISOR-001 | HANDOFF-15 |
| HO1m trace format | PKG-HO1-EXECUTOR-001 | HANDOFF-14 |
| Attention template loading + binding | PKG-HO2-SUPERVISOR-001 | HANDOFF-15 |
| Session Host integration | PKG-SESSION-HOST-V2 | HANDOFF-16 |
| Work order schema | PKG-WORK-ORDER-001 | HANDOFF-13 |

### Existing Infrastructure (already built)

These shared components already exist and will be consumed by cognitive stacks:

| Component | Package | Status |
|-----------|---------|--------|
| LLM Gateway | PKG-GATEWAY-001 | Exists (AnthropicProvider wired) |
| Ledger Client | PKG-KERNEL-001 | Exists |
| Gate Operations | PKG-KERNEL-001 | Exists |
| Auth/Authz | PKG-KERNEL-001 | Exists |
| Schema Validator | PKG-SCHEMA-VALIDATOR-001 | Exists |
| Attention Template Schema | PKG-PHASE2-SCHEMAS-001 | Exists |
| Layout Config | PKG-LAYOUT-002 | Exists |

### Concrete Flow Example: Two Stacks in Action

> Source: v2 Section 14 (Concrete Flows), Flow A (DoPeJar) and Flow B (ADMIN)

The following demonstrates how two cognitive stacks operate independently with isolated state while sharing infrastructure.

**Flow A -- DoPeJar stack processing "hello"** (v2 Section 14, Flow A):

```
[User] "hello"
  |
  v
[DoPeJar] wraps as percept
  |
  v
[DPJ-HO2 cognitive process] receives              <-- DoPeJar stack's HO2 instance
  |
  |  WO#1 --> classify speech-act + ambiguity
  v
[DPJ-HO1] (LLM call: classify)                    <-- DoPeJar stack's HO1 instance
  |--> {speech_act=reentry_greeting, ambiguity=high, search=enable}
  v
[DPJ-HO2]
  |  WO#2 --> horizontal scan (HO2m: recency, open loops)
  v
[DPJ-HO1] (trace query + optional LLM compression)
  |--> HO2_candidates = [closet_design, control_plane]
  v
[DPJ-HO2]
  |  WO#3 --> priority probe (HO3m: salience anchors)
  v
[DPJ-HO1] (policy query + optional LLM compression)
  |--> HO3_candidates = [daughter_dance]
  v
[DPJ-HO2]
  |  Arbitration: must-mention=daughter_dance, options=[closet, CP]
  |  Strategy: offer-choice
  |
  |  WO#4 --> build final response
  v
[DPJ-HO1] (LLM call: generate response)
  |--> user-facing text
  v
[DoPeJar] --> User
  |
[DPJ-HO1] appends canonical trace (WO#1-4 + arbitration)   <-- isolated HO1m
[DPJ-HO2m] records arbitration meta-episode                  <-- isolated HO2m
```

**Flow B -- ADMIN stack processing "show me all frameworks"** (v2 Section 14, Flow B):

```
[User] "Admin: show me all frameworks"
  |
  v
[ADMIN] wraps as admin query
  |
  v
[ADMIN-HO2 cognitive process]                      <-- ADMIN stack's HO2 instance
  |  Classify: read-only inspection
  |
  |  WO#1 --> read framework registry
  v
[ADMIN-HO1] (tool call: read_file)                 <-- ADMIN stack's HO1 instance
  |--> framework_ids + paths + versions
  |
  |  WO#2 --> enumerate frameworks directory (verify)
  v
[ADMIN-HO1] (tool call: list_dir)
  |--> observed frameworks
  |
  |  WO#3 --> summarize + format
  v
[ADMIN-HO1] (LLM call: format results)
  |--> formatted table + discrepancies
  v
[ADMIN-HO2] approves output
  v
[ADMIN] --> User
  |
[ADMIN-HO1m] records tool calls + outputs           <-- isolated HO1m
[ADMIN-HO2m] records admin query event               <-- isolated HO2m
```

**Key observation**: Both flows use the same KERNEL.syntactic infrastructure (LLM Gateway for LLM calls, Ledger Client for trace writes). But DPJ-HO2m and ADMIN-HO2m are completely separate. DPJ-HO1m and ADMIN-HO1m are completely separate. The ADMIN stack cannot see DoPeJar's arbitration outcomes, and DoPeJar cannot see ADMIN's framework query results.

---

## 10. Relationship to Tier Boundaries

> Source: FMWK-009 (Tier Boundary) handoff spec, v2 Section 5 (The Visibility / Syscall Model)

### How FMWK-010 and FMWK-009 Interact

FMWK-010 (Cognitive Stack) and FMWK-009 (Tier Boundary) are complementary frameworks that address different dimensions of isolation:

| Dimension | FMWK-009 Governs | FMWK-010 Governs |
|-----------|-------------------|-------------------|
| **Vertical isolation** (between tiers) | What HO1 can see vs HO2 vs HO3. Syscall model. Import restrictions. | -- (defers to FMWK-009) |
| **Horizontal isolation** (between stacks) | -- (not its scope) | What ADMIN stack can see vs RESIDENT stack. Per-stack state boundaries. |
| **Budget enforcement** | HO3 --> HO2 --> HO1 budget hierarchy | Per-stack budget ceiling (allocated at stack creation) |
| **Path convention** | Tier-level: `HO1/` vs `HO2/` vs `HOT/` | Stack-level: `HO2/ledger/ADMIN/` vs `HO2/ledger/RESIDENT_DoPeJar/` |

### Dependency Direction

FMWK-010 depends on FMWK-009. The per-stack isolation rules in FMWK-010 are built on top of the tier boundary enforcement in FMWK-009:

1. **Visibility**: FMWK-009 enforces "reading up = forbidden." FMWK-010 adds "reading across stacks = forbidden" within the same tier.
2. **Syscalls**: FMWK-009 defines the enumerated syscalls (LLM_GATEWAY_CALL, LEDGER_WRITE, LEDGER_READ, etc.). FMWK-010 ensures each stack's syscalls operate on that stack's isolated state partitions.
3. **Gate checks**: FMWK-009 defines gate checks for cross-tier imports. FMWK-010 relies on those same gates plus per-stack path scoping to prevent cross-stack access.

### Gap Flagging Protocol

If FMWK-010 discovers a scenario where per-stack isolation requires a tier boundary rule that FMWK-009 does not cover, FMWK-010 flags the gap rather than filling it. The gap is recorded here and communicated to the FMWK-009 builder.

**Currently identified gaps**: None. FMWK-009's visibility matrix and syscall model are sufficient for the per-stack isolation rules defined in FMWK-010.

---

## Conformance

Any package that instantiates cognitive stacks MUST conform to FMWK-010:

1. **MUST** maintain the shared/isolated boundary as defined in Sections 1 and 2.
2. **MUST** use the factory pattern for stack instantiation (Section 3).
3. **MUST** populate HO2m with the fields defined in Section 4.
4. **MUST** store per-stack state in agent-class-scoped directories (Section 5).
5. **MUST** bind attention templates via the `applies_to` selector (Section 6).
6. **MUST** enforce cross-stack visibility rules (Section 7).
7. **MUST** follow stack lifecycle phases (Section 8).
8. **MUST NOT** allow one stack to read another stack's isolated state (except KERNEL.semantic meta agent).
9. **MUST NOT** carry internal state between sessions (Invariant #3).
10. **MUST NOT** create shared HO2 or HO1 instances that serve multiple agent classes.

## Status

| Field | Value |
|-------|-------|
| Framework ID | FMWK-010 |
| Version | 1.0.0 |
| Status | Draft |
| Design Authority | `_staging/architecture/KERNEL_PHASE_2_v2.md` |
| Created | 2026-02-14 |
| Author | Builder Agent (FMWK-010) |
