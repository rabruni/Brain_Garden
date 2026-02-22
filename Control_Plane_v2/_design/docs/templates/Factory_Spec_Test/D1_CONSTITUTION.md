# D1: Constitution — Dark Factory Orchestrator

**Version:** 1.0.0
**Ratified:** 2026-02-22
**Last Amended:** 2026-02-22
**Design Authority:** PRODUCT_SPEC_FRAMEWORK.md, BUILDER_HANDOFF_STANDARD.md, BUILDER_PROMPT_CONTRACT.md, test/FINDINGS.md

---

## Articles

### Article 1: Specs Are Source of Truth — Code Is Derived

**Rule:** The orchestrator MUST treat D1-D10 documents as the canonical authority. No orchestrator logic may contradict, supplement, or reinterpret the content of a product spec.

**Why:** The entire value proposition of the Dark Factory is that the spec governs the build. If the orchestrator adds implicit behavior (default constraints, assumed interfaces, injected rules), it becomes an unauditable second source of truth. The spec author loses control.

**Test:** Diff the generated handoff against the source D2 scenarios and D4 contracts. Every requirement in the handoff must trace to a specific line in a D-document. Any orphan requirement is a violation.

**Violations:** No exceptions.

### Article 2: Holdout Isolation Is Inviolable

**Rule:** D9 holdout scenarios MUST NEVER be visible to builder agents. The orchestrator MUST NOT include D9 content in handoff specs, agent prompts, or any artifact the builder can access.

**Why:** Holdout scenarios are the independent verification mechanism. If the builder sees them, they become training data — the builder optimizes for the holdouts instead of implementing the spec. This is the core Dark Factory principle.

**Test:** Inspect every artifact the orchestrator produces for agent consumption (handoffs, prompts, context docs). Search for any content from D9. Any match is a violation.

**Violations:** No exceptions.

### Article 3: The Orchestrator Does Not Build — It Dispatches

**Rule:** The orchestrator MUST NOT write application code, modify source files, or create package contents. It generates handoff documents, agent prompts, and validation reports. Building is the builder agent's job.

**Why:** If the orchestrator writes code, it becomes an unverified builder with no holdout gate. The separation of dispatch (orchestrator) and execution (builder) is the same separation as HO2/HO1 in the cognitive model.

**Test:** Inspect all files written by the orchestrator. None may be .py source files, manifest.json files, or package archives inside a PKG-* directory. Orchestrator output is markdown, YAML, and JSON reports only.

**Violations:** No exceptions.

### Article 4: Every Handoff Is Traceable

**Rule:** Every generated handoff MUST reference the specific D2 scenarios, D3 entities, D4 contracts, and D8 task ID it implements. No handoff may exist without traceability to the product spec.

**Why:** Traceability is how the reviewer knows what the builder should have built. Without it, the reviewer has no acceptance criteria. Traceability also enables the orchestrator to detect coverage gaps (D2 scenarios not assigned to any handoff).

**Test:** For every generated handoff, verify that every D2 scenario listed in D8 for that task appears in the handoff. For every D2 scenario in the spec, verify at least one handoff covers it.

**Violations:** No exceptions.

### Article 5: Validate Before Dispatch

**Rule:** The orchestrator MUST validate the completeness of the product spec before generating any handoff. Validation MUST confirm: D6 has zero OPEN items, every D2 scenario is covered by at least one D8 task, every D4 contract is implemented by at least one D8 task, and D9 has at least 3 holdout scenarios.

**Why:** Dispatching from an incomplete spec produces incomplete handoffs. Builder agents cannot compensate for spec gaps — they will either invent answers (creating unauditable behavior) or fail and waste tokens.

**Test:** Attempt to run the orchestrator on a spec with an OPEN D6 item. The orchestrator must refuse and report the gap.

**Violations:** No exceptions.

### Article 6: Holdout Failures Trace to Specs

**Rule:** When a holdout scenario fails, the orchestrator MUST produce a report that traces the failure to specific D2 scenarios and D4 contracts. The report MUST identify which D8 task was responsible.

**Why:** A holdout failure without traceability is just a red flag with no action. Traceability tells the reviewer exactly which handoff to re-dispatch, which scenario was missed, and which contract was violated.

**Test:** Introduce a deliberate holdout failure (mock a builder that produces wrong output). Verify the failure report names the D2 scenario, D4 contract, and D8 task.

**Violations:** No exceptions.

### Article 7: No Silent Failures

**Rule:** Every orchestrator operation MUST produce an explicit status: PASS, FAIL, or BLOCKED. The orchestrator MUST NOT silently skip a step, ignore a missing document, or proceed past a validation failure.

**Why:** Silent failures in the orchestrator propagate as mysterious builder failures. A missing D3 that the orchestrator ignores becomes a builder that invents data shapes.

**Test:** Remove a required document (e.g., delete D3). Run the orchestrator. It must report BLOCKED with the specific missing document, not proceed without it.

**Violations:** No exceptions.

### Article 8: Deterministic Output

**Rule:** Given identical D1-D10 input documents, the orchestrator MUST produce identical handoff documents, agent prompts, and validation configurations. No randomness, no timestamp-dependent content in generated artifacts (timestamps in metadata headers are acceptable).

**Why:** Determinism enables diffing, debugging, and reproducibility. If re-running the orchestrator on the same spec produces different handoffs, the reviewer cannot trust either version.

**Test:** Run the orchestrator twice on the same spec. Diff the output (excluding metadata timestamps). Zero differences.

**Violations:** No exceptions.

---

## Boundary Definitions

### ALWAYS (orchestrator does this without asking)

- Validate spec completeness before generating handoffs
- Include traceability references (D2, D4, D8 IDs) in every generated handoff
- Verify D9 holdout scenarios are excluded from all builder-visible artifacts
- Report explicit PASS/FAIL/BLOCKED status for every operation
- Log every dispatch event (which handoff, which agent, when)

### ASK FIRST (orchestrator must get human approval)

- Proceed when D6 has ASSUMED items (assumptions documented but not resolved)
- Re-dispatch a handoff after a builder failure (human decides retry vs. revise spec)
- Skip a D8 task that is marked as deferred
- Override a holdout failure (human decides accept vs. reject)

### NEVER (orchestrator refuses even if instructed)

- Include D9 holdout content in builder-visible artifacts
- Generate handoffs from a spec with OPEN D6 items
- Write application source code or package contents
- Modify the product spec documents (D1-D10 are read-only inputs)
- Dispatch a handoff without traceability to D2 scenarios

---

## Development Workflow Constraints

- All orchestrator code lives in its own package (not embedded in existing Control Plane packages)
- DTT per-behavior cycles for orchestrator development
- Results file with SHA256 hashes after every handoff
- Full regression across orchestrator tests before release

## Tooling Constraints

| Operation | USE THIS | NOT THIS |
|-----------|----------|----------|
| Parse markdown specs | Structured parser with heading/section extraction | Regex on raw text |
| Generate handoff documents | Template engine with D-document references | String concatenation |
| Run holdout scenarios | Subprocess isolation (builder code runs in separate process) | In-process execution |
| Track dispatch status | Append-only dispatch ledger (JSON) | In-memory state only |
| Validate spec completeness | Schema-driven validation against D-template acceptance criteria | Manual checklist |
