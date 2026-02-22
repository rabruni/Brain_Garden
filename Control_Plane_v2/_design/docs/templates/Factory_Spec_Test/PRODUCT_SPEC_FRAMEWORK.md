# Product Spec Framework

**Status:** Draft | **Created:** 2026-02-22 | **Author:** Ray + Claude (Cowork session)
**Purpose:** Define the complete set of deliverables required to fully specify a component before decomposing it into agent-executable handoffs.

**Design Sources:** Extracted from GitHub Spec Kit (specify→plan→tasks workflow), StrongDM Dark Factory pattern (holdout scenarios), Kiro (GIVEN/WHEN/THEN acceptance), and DoPeJar's own build process (DTT, dependency surface analysis, governance gates).

---

## Why This Framework Exists

The gap between "we know what this component should do" and "an agent can build it without us chasing issues for days" is filled by seven deliverables. Each one answers a different question. Together they constitute a **complete product spec** — sufficient to decompose into handoffs and sufficient to verify the result.

The framework is **extraction-first**: most content already exists in design documents. The work is consolidation and gap-finding, not invention. When a deliverable cannot be completed from existing design docs, that gap IS the finding — it becomes a Forced Clarification (Deliverable 6) that must be resolved before handoff decomposition begins.

**Process flow:**

```
Design Documents                    Product Spec (7 deliverables)           Build Sequence
─────────────────                   ──────────────────────────────          ──────────────
KERNEL_PHASE_2_v2.md    ──┐
STATE_OF_DOPEJAR.md     ──┼──▶  Extract ──▶ D1 through D7 ──▶ Resolve ──▶ Handoff decomposition
DESIGN_PHILOSOPHY.md    ──┘         ▲              │           D6 gaps         │
                                    │              ▼                           ▼
                              Repeatable      Gap Analysis               H-0: Shared contracts
                              per component   surfaces what              H-1: Thinnest working pipe
                                              design docs                H-2+: Layered capabilities
                                              don't answer
```

---

## The Seven Deliverables

### D1: Component Identity

**Question it answers:** What is this thing, and where does it live in the system?

**What it contains:**

- **Name and ID.** The component name, its package ID (if known), and any aliases or prior names. Include the lineage — if this replaces or supersedes a prior component, state that explicitly.
- **Tier placement.** Which tier does this component execute in (HOT/HO2/HO1)? What is its kernel classification (KERNEL.syntactic, KERNEL.semantic, non-kernel)?
- **Cognitive role.** What is this component's role in the Kitchener hierarchy? Is it a strategist, critic, worker, or infrastructure? One sentence.
- **One-paragraph purpose.** What does this component do, stated without implementation details. The test: could a new team member read this paragraph and correctly explain the component's job to someone else?
- **What it is NOT.** Explicit negative boundaries. "HO1 is not a session manager. HO1 does not decide what to do — it does what it's told." These prevent scope creep during handoff execution.

**How it's produced:** Extracted from `KERNEL_PHASE_2_v2.md` (tier model, cognitive roles), `STATE_OF_DOPEJAR.md` (component inventory, layer assignments), and `DESIGN_PHILOSOPHY.md` (classification axes). If the component is new, its identity must be consistent with these documents or explicitly noted as an extension.

**Acceptance criteria:**

- [ ] Tier placement matches the tier model in KERNEL_PHASE_2_v2.md Section 2
- [ ] Kernel classification matches the taxonomy in DESIGN_PHILOSOPHY.md Section 5
- [ ] Purpose paragraph uses no implementation terms (no class names, no file paths, no method signatures)
- [ ] "What it is NOT" contains at least 3 explicit negative boundaries
- [ ] If superseding a prior component, lineage is stated with the old package ID

**Definition of done:** A reviewer who has never seen this component can read D1 and correctly answer: "What tier does it run in? What does it do? What does it NOT do?" without consulting any other document.

---

### D2: User Stories and Scenarios

**Question it answers:** What does this component do from the perspective of its callers?

**What it contains:**

- **Primary scenarios.** 3-7 concrete scenarios written in GIVEN/WHEN/THEN format. Each scenario describes one interaction path through the component, from the caller's perspective. The caller is NOT a human user — it is whatever system component invokes this one (e.g., for HO1, the caller is HO2).
- **Edge case scenarios.** 2-4 scenarios covering failure modes, boundary conditions, and degradation paths. These are where bugs hide.
- **Scenario source tracing.** Each scenario must reference the design document section it was extracted from (e.g., "Derived from KERNEL_PHASE_2_v2.md Section 14, Flow A: DoPeJar 'Hello'"). If a scenario has no source, it must be flagged as new design (not extraction) and justified.

**Format per scenario:**

```
SCENARIO: [Short descriptive name]
SOURCE:   [Design doc, section, or "NEW — justification"]

GIVEN  [precondition — the state of the system before this scenario]
WHEN   [trigger — what the caller does]
THEN   [outcome — what the component produces, including side effects like ledger writes]
```

**How it's produced:** Extracted from the concrete flows in `KERNEL_PHASE_2_v2.md` Section 14 (Flow A, Flow B), `STATE_OF_DOPEJAR.md` "How a Turn Works" section, and any framework specs (FMWK-008 through FMWK-011) that define contracts involving this component. Edge cases are derived from the "Common Traps" section of `DESIGN_PHILOSOPHY.md` and the "Deferred Decisions" section of `KERNEL_PHASE_2_v2.md`.

**Acceptance criteria:**

- [ ] Every primary scenario traces to a specific design document section
- [ ] At least 2 edge case scenarios cover failure modes (not just happy paths)
- [ ] Scenarios are written from the CALLER's perspective, not the component's internals
- [ ] No scenario references implementation details (class names, file paths, method names)
- [ ] The scenario set covers: normal operation, error/failure, resource exhaustion (e.g., budget), and missing/invalid input

**Definition of done:** An agent reading D2 can write acceptance tests for every scenario without consulting the design docs. The scenarios are the spec — if the code satisfies them, the component works.

---

### D3: Interface Definitions

**Question it answers:** What goes in, what comes out, and what is the exact shape of each?

**What it contains:**

- **Inbound interface(s).** The exact shape of what this component receives. Field names, types, which fields are required vs. optional, and what each field means. This is the component's API contract — what callers must provide.
- **Outbound interface(s).** The exact shape of what this component returns. Same level of detail as inbound.
- **Side-effect interfaces.** What the component writes to external systems as a consequence of execution (e.g., ledger entries, metrics, state changes). These are NOT return values — they are observable effects. Include the shape of each side-effect write.
- **Error interface.** What failure looks like to the caller. Error codes, error shapes, and what the caller should do with each. "The component fails" is not an error interface — "the component returns `{error_code: 'budget_exhausted', ...}` and the caller should retry with a smaller scope" is.

**Format per interface:**

```
INTERFACE: [Name — e.g., "Prompt Envelope (inbound)"]
DIRECTION: IN | OUT | SIDE-EFFECT | ERROR

SCHEMA:
  field_name:     type        required/optional   description
  field_name:     type        required/optional   description
  ...

CONSTRAINTS:
  - [Any validation rules, size limits, enum values, etc.]

EXAMPLE:
  {concrete JSON example with realistic values}
```

**How it's produced:** Extracted from `KERNEL_PHASE_2_v2.md` Section 8 (infrastructure components), Section 17 (work order schema), FMWK-008 (work order protocol), FMWK-011 (prompt contract schema), and `STATE_OF_DOPEJAR.md` Layer descriptions. For new components, the interface is designed to be consistent with existing patterns.

**Acceptance criteria:**

- [ ] Every field has a type, required/optional flag, and description
- [ ] Every interface has at least one concrete example with realistic values
- [ ] Error interface covers at least: invalid input, missing dependency, resource exhaustion, and upstream failure
- [ ] Side-effect interfaces include the shape of what gets written (not just "writes to ledger")
- [ ] Inbound interface is sufficient to write a mock caller; outbound interface is sufficient to write a mock consumer
- [ ] No interface references internal implementation (no class names, no file paths)

**Definition of done:** An agent can implement both a mock caller (sends valid inbound data, reads outbound data) and a mock implementation (receives inbound, produces outbound + side-effects) from D3 alone, with zero ambiguity about shapes.

---

### D4: Dependency Surface Analysis

**Question it answers:** What does this component need from the system that may not exist yet?

**This is the deliverable that catches the problems you'd otherwise chase for days.** It systematically walks every boundary the component touches and asks: is there a defined contract here, or will the builder agent invent one implicitly?

**What it contains:**

For each boundary category below, state: (a) what the component needs, (b) whether an existing contract covers it, and (c) if not, what must be defined before building begins.

**Boundary categories:**

| Category | What to examine | Example gap |
|----------|----------------|-------------|
| **Data In** | Is the inbound schema defined somewhere shared, or only in this component's D3? If only here, it's an implicit standard — make it explicit. | Prompt envelope format defined only in HO1 → should be a shared schema |
| **Data Out** | Same question for outbound. Will other components consume this output? If yes, the schema is shared. | Response envelope consumed by HO2 → shared contract needed |
| **Persistence** | What gets written to disk/ledger? What is the entry format? Is it a system-wide standard or component-specific? | Exchange ledger entry format — if HO2 and admin tools will query these entries, the schema is shared |
| **Authentication / Authorization** | Who can call this component? How is identity established? Are there capability boundaries? | HO1 callable only by HO2 — is this enforced, or just a convention? |
| **External Services** | What APIs or providers does this component call? What are their contracts? Do they differ in response format, token counting, error shapes? | Anthropic and Qwen return tokens differently — need a normalization standard |
| **Configuration** | What's tunable? Where does config live? Is it per-component or shared? | Budget thresholds — per HO1 config, or from admin_config.json (shared)? |
| **Error Propagation** | What does failure look like to the system, not just the caller? Does a failure here cascade? How does the system recover? | HO1 gateway timeout → does HO2 retry? Degrade? Who decides? |
| **Observability** | What can an operator see? What gets logged beyond the ledger? Metrics, health checks, debug traces? | Admin tools expect to query HO1m — the query interface must be defined |
| **Token / Resource Accounting** | How are consumed resources reported? Is there a standard unit? Do different providers report differently? | Anthropic tokens vs. Qwen tokens — need canonical unit for budgeting |

**How it's produced:** Walk each boundary using D3 (Interface Definitions) as the starting point. For each interface, ask: "Is the other side of this interface already defined in an existing contract (FMWK, schema, shared spec)?" Check against `DESIGN_PHILOSOPHY.md` Section 6 (governance), `KERNEL_PHASE_2_v2.md` Section 5 (syscall model), Section 8 (infrastructure), and the existing FMWK specs (008-011).

**Output format per boundary:**

```
BOUNDARY:        [Category — e.g., "Persistence: Exchange Ledger Entries"]
WHAT IS NEEDED:  [What the component requires at this boundary]
EXISTING CONTRACT: [Reference to existing spec/schema/FMWK, or "NONE"]
GAP:             [What must be defined — or "COVERED" if existing contract is sufficient]
SHARED?:         [YES if other components will use this contract, NO if component-private]
RECOMMENDATION:  [Define as shared contract in H-0 / Define inline / Defer with interface stub]
```

**Acceptance criteria:**

- [ ] Every boundary category has been examined (no "N/A" without justification)
- [ ] Every gap is classified as SHARED or component-private
- [ ] Every SHARED gap has a recommendation: define before building, or define an interface stub that can be filled later
- [ ] Every existing contract reference is verified (the cited FMWK/schema actually covers what's claimed)
- [ ] The analysis references specific design doc sections, not general claims

**Definition of done:** All shared gaps are either (a) resolved into shared contract specs (fed into Handoff 0) or (b) have explicit interface stubs with documented assumptions that the builder agent will code against. No implicit contracts remain — every boundary is either covered by an existing spec or flagged.

---

### D5: Non-Goals

**Question it answers:** What is explicitly out of scope for this component?

**What it contains:**

- **Capability non-goals.** Things this component will never do, even in future versions. These are architectural boundaries, not deferrals. (e.g., "HO1 will never maintain session state between work orders.")
- **Deferred capabilities.** Things this component might do eventually but are NOT part of this build. Each deferral must state WHY it's deferred and WHAT the trigger would be to add it. (e.g., "Provider failover deferred — single provider sufficient for current work. Trigger: when multi-provider is needed for production reliability.")
- **Adjacent component boundaries.** Capabilities that belong to a DIFFERENT component, stated here to prevent scope creep. (e.g., "Context assembly is HO2's job. HO1 receives assembled context, it does not retrieve or assemble it.")

**How it's produced:** Extracted from `KERNEL_PHASE_2_v2.md` Section 15 (Deferred Decisions), `DESIGN_PHILOSOPHY.md` Section 10 (Common Traps), and the D1 "What it is NOT" section (expanded with justifications). Cross-referenced with the D4 Dependency Surface to ensure deferred items don't create hidden gaps.

**Acceptance criteria:**

- [ ] At least 3 capability non-goals (permanent architectural boundaries)
- [ ] Every deferred capability has a WHY and a TRIGGER for when it would be added
- [ ] Adjacent component boundaries reference the actual component that owns the capability
- [ ] No non-goal contradicts the design docs (if it does, flag as a design question in D6)
- [ ] Deferred capabilities that appear in D4 as boundary gaps are cross-referenced

**Definition of done:** A builder agent that encounters a feature request outside D5's scope can point to a specific non-goal entry and refuse without escalation. The non-goals are the component's immune system against scope creep.

---

### D6: Forced Clarifications

**Question it answers:** What do we NOT know yet, and what must be resolved before building?

**This is the most important deliverable.** Everything in D1-D5 is extraction — pulling known information from design docs into a structured format. D6 is where you discover what the design docs DON'T answer. Every unresolved item here is a decision that, if made implicitly by a builder agent, will create a problem you chase for days.

**What it contains:**

- **Unresolved design questions.** Gaps found during D1-D5 extraction where the design docs are silent, ambiguous, or contradictory. Each question must state: what was being extracted, what document was consulted, and what was missing or unclear.
- **Decision-required items.** Questions where multiple valid answers exist and a human must choose. Include the options and trade-offs for each.
- **Assumption log.** If a deliverable (D1-D5) was completed by ASSUMING an answer that isn't in the design docs, log the assumption here. Assumptions are acceptable for draft specs but must be resolved before handoff decomposition.

**Format per clarification:**

```
CLARIFICATION: [Short title]
FOUND DURING:  [Which deliverable — D1, D2, D3, D4, or D5]
SEARCHED:      [Which design doc sections were consulted]
QUESTION:      [The specific question that needs an answer]
OPTIONS:       [If decision-required: the valid options with trade-offs]
IMPACT:        [What happens if this is left unresolved — which handoffs are blocked?]
STATUS:        OPEN | RESOLVED([answer]) | ASSUMED([assumption])
```

**How it's produced:** Accumulated during the production of D1-D5. Every time an extractor consults a design doc and finds silence, ambiguity, or contradiction, they log a clarification. D6 is not written separately — it is built incrementally as the other deliverables are written.

**Acceptance criteria:**

- [ ] Every ASSUMED entry in D1-D5 has a corresponding D6 clarification
- [ ] Every OPEN clarification states which handoffs it blocks
- [ ] No clarification is answerable by reading the design docs (if it is, it should have been extracted, not flagged)
- [ ] Decision-required items have at least 2 options with trade-offs
- [ ] RESOLVED items include the decision and who made it

**Definition of done:** All clarifications are either RESOLVED or ASSUMED-with-documented-risk. Zero OPEN items remain before handoff decomposition begins. This is the gate: if D6 has OPEN items, you are not ready to write handoffs.

---

### D7: Holdout Scenarios

**Question it answers:** How do we prove the built component actually works, independent of the builder agent's own tests?

**This concept comes from the Dark Factory pattern (StrongDM).** The builder agent writes its own unit and integration tests during DTT (Design → Test → Then implement). But the builder's tests can only verify what the builder understood. Holdout scenarios are acceptance tests written by the spec author (you), stored separately from the build, and evaluated AFTER the builder delivers. The builder never sees them. This prevents the agent from "teaching to the test."

**What it contains:**

- **End-to-end acceptance scenarios.** 3-5 scenarios that prove the component works as a system participant, not just as an isolated unit. Each scenario involves real (or realistic) input, passes through the component, and produces observable output + side effects that can be verified.
- **Verification method.** For each scenario: what command to run, what to check, and what constitutes PASS/FAIL. These must be executable — not prose descriptions of what "should" happen, but concrete checks.
- **Separation enforcement.** Holdout scenarios are stored in a DIFFERENT location from the builder's handoff. The builder's handoff spec (when decomposed) must NOT reference or include these scenarios. They are the reviewer's tool, not the builder's.

**Format per holdout scenario:**

```
HOLDOUT: [Short descriptive name]
TRACES TO: [D2 scenario(s) this validates]

SETUP:
  [What must be true before this test runs — installed packages, config, running services]

EXECUTE:
  [Exact steps — commands, API calls, or input sequences]

VERIFY:
  [What to check — file contents, ledger entries, return values, absence of errors]
  PASS IF: [Concrete, measurable condition]
  FAIL IF: [Concrete, measurable condition]
```

**How it's produced:** Written by the spec author (not the builder agent) after D2 (User Stories) and D3 (Interface Definitions) are complete. Each holdout traces to one or more D2 scenarios but tests them from the outside — through real interfaces, checking real side effects. The Dark Factory principle applies: these tests evaluate the output the way a user would, not the way a developer would.

**Acceptance criteria:**

- [ ] At least 3 holdout scenarios covering: happy path, error path, and a cross-boundary integration
- [ ] Every scenario has executable verification steps (not prose)
- [ ] No scenario references internal implementation (class names, method names, file internals)
- [ ] Scenarios are stored separately from handoff specs (enforced by file location convention)
- [ ] At least 1 scenario verifies a side effect (e.g., ledger entry written with correct schema)
- [ ] Holdout scenarios are reviewed by someone other than the spec author if possible

**Definition of done:** After a builder agent delivers the component and all handoffs are VALIDATED, the reviewer runs every holdout scenario. If all pass, the component is accepted. If any fail, the failure traces back to a specific D2 scenario and D3 interface — the spec told us what to expect, the holdout proved it didn't happen.

---

## How the Seven Deliverables Compose

```
D1: Identity ─────────────────────────▶ "What is it?"
D2: User Stories ─────────────────────▶ "What does it do?" (caller's view)
D3: Interface Definitions ────────────▶ "What goes in / comes out?" (exact shapes)
D4: Dependency Surface ───────────────▶ "What's missing?" (shared contracts, gaps)
D5: Non-Goals ────────────────────────▶ "What does it NOT do?" (scope boundaries)
D6: Forced Clarifications ────────────▶ "What don't we know?" (gate before building)
D7: Holdout Scenarios ────────────────▶ "How do we prove it works?" (reviewer's tests)

D1-D3: Extraction (pull from design docs)
D4:    Analysis (walk boundaries, find gaps)
D5:    Scoping (prevent creep)
D6:    Accumulated during D1-D5 (gaps found along the way)
D7:    Written after D1-D3 are stable (acceptance proof)
```

**The handoff decomposition gate:** D6 has zero OPEN items. Only then do you decompose into:

- **H-0:** Shared contracts identified by D4 (schemas, standards, interface stubs)
- **H-1:** Thinnest working pipe (smallest subset of D2 scenarios that proves the foundation)
- **H-2+:** Layered capabilities (remaining D2 scenarios, one per handoff)

Each handoff references specific D2 scenarios it must satisfy, specific D3 interfaces it must implement, and specific D4 contracts it must code against. The handoff's acceptance criteria come directly from the product spec — they are not invented by the handoff author.

---

## Repeatable Process

This framework applies to any component. The steps:

1. **Select component.** Identify what you're speccing.
2. **Identify design doc sources.** Which sections of KERNEL_PHASE_2_v2.md, STATE_OF_DOPEJAR.md, DESIGN_PHILOSOPHY.md (and any FMWKs) contain information about this component.
3. **Extract D1-D3.** Pull identity, scenarios, and interfaces from the sources. Log clarifications to D6 as they arise.
4. **Analyze D4.** Walk every boundary in D3. Flag shared gaps.
5. **Scope D5.** Define what's permanently out, what's deferred, and what belongs elsewhere.
6. **Resolve D6.** Human reviews all clarifications. Resolves or accepts assumptions. Gate: zero OPEN items.
7. **Write D7.** Author holdout scenarios from D2+D3. Store separately.
8. **Decompose into handoffs.** D4 shared gaps → H-0. D2 scenarios → H-1 through H-N.

Time estimate for extraction: 2-4 hours per component (with design docs already written). The payoff: handoffs that don't surprise you.
