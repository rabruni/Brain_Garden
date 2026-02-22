# D2: Specification — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Package ID:** PKG-DARK-FACTORY-001
**Spec Version:** 0.1.0
**Status:** Draft
**Author:** Ray + Claude (Cowork session)
**Design Sources:** PRODUCT_SPEC_FRAMEWORK.md (7-deliverable pipeline), test/ directory (filled HO1 example), FINDINGS.md (process test observations), BUILDER_HANDOFF_STANDARD.md (handoff format), BUILDER_PROMPT_CONTRACT.md (agent prompt format)
**Constitution:** D1 v1.0.0

---

## Component Purpose

The Dark Factory Orchestrator automates the pipeline from product spec (D1-D10 documents) to validated code delivery. It reads a complete set of D-documents for a component, validates spec completeness, decomposes D8 tasks into handoff documents, generates agent prompts, dispatches builder agents, collects results, runs holdout scenarios, and produces pass/fail reports with full traceability to the original spec. The first use case is the HO1 Cognitive Process build defined in the test/ directory.

## What This Component Is NOT

- The orchestrator is NOT a builder. It does not write application code, tests, or package manifests. It generates handoff documents and validates results.
- The orchestrator is NOT an LLM. It does not reason about code quality, suggest fixes, or interpret ambiguous specs. It mechanically applies the D-template pipeline.
- The orchestrator is NOT a CI/CD system. It does not manage branches, run linters, or deploy artifacts. It dispatches agents and validates their output.
- The orchestrator is NOT a spec authoring tool. It reads D1-D10 as input — it does not help write them.

## User Scenarios

### Primary Scenarios (happy path)

#### SC-001: Validate a complete product spec

**Priority:** P1 (must-have)
**Source:** PRODUCT_SPEC_FRAMEWORK.md "Repeatable Process" step 6 — "Resolve D6. Gate: zero OPEN items."

**GIVEN** a directory containing D1-D10 documents for a component (e.g., the HO1 test/ directory)
**WHEN** the operator runs `factory validate --spec-dir test/`
**THEN** the orchestrator reads all 10 documents, checks completeness (all required sections present, D6 has zero OPEN items, every D2 scenario is covered by D8, every D4 contract is assigned to a D8 task, D9 has >= 3 holdouts), and reports PASS with a summary: document count, scenario count, task count, holdout count
**AND** if any check fails, reports FAIL with the specific gap (e.g., "D2 SC-003 not covered by any D8 task")

**Testing Approach:** Run validate on the test/ spec (should PASS). Run on a modified spec with a removed D8 task (should FAIL naming the orphaned scenario).

#### SC-002: Generate handoffs from a validated spec

**Priority:** P1 (must-have)
**Source:** PRODUCT_SPEC_FRAMEWORK.md "How the Seven Deliverables Compose" — "Decompose into handoffs. D4 shared gaps → H-0. D2 scenarios → H-1 through H-N."

**GIVEN** a validated product spec (SC-001 passed)
**WHEN** the operator runs `factory generate --spec-dir test/ --output-dir handoffs/`
**THEN** the orchestrator produces one handoff markdown file per D8 task, following the BUILDER_HANDOFF_STANDARD.md format (10 required sections). Each handoff contains: mission (from D8 task description), critical constraints (from D1), architecture (from D7 plan, scoped to this task), implementation steps (from D8 acceptance criteria), package plan (from D7 file structure), test plan (from D2 scenarios mapped to this task), existing code references (from D10), E2E verification commands (from D10), files summary (from D7), design principles (from D1 filtered to this task)
**AND** each handoff includes traceability: D2 scenario IDs, D4 contract IDs, D8 task ID
**AND** no handoff contains any content from D9 (holdout isolation)

**Testing Approach:** Generate handoffs from the test/ spec. Verify each handoff has all 10 sections. Grep all handoffs for D9 content — zero matches. Verify every D2 scenario appears in at least one handoff.

#### SC-003: Generate agent prompts from handoffs

**Priority:** P1 (must-have)
**Source:** BUILDER_PROMPT_CONTRACT.md "Template" section — variables in [BRACKETS] filled per handoff

**GIVEN** generated handoff documents (SC-002 completed)
**WHEN** the operator runs `factory prompts --handoffs-dir handoffs/ --spec-dir test/`
**THEN** the orchestrator produces one agent prompt per handoff, following BUILDER_PROMPT_CONTRACT.md template. Each prompt contains: HANDOFF_ID, ONE_LINE_MISSION, CONTRACT_VERSION, 7 mandatory rules, 10 verification questions (derived from D2 scenarios and D4 contracts for this task), 3 adversarial questions (genesis set or infrastructure set based on config), expected answers section (for reviewer, derived from D2/D4)
**AND** prompts reference the handoff file path, not inline the full handoff content

**Testing Approach:** Generate prompts from test/ handoffs. Verify each prompt has 13 questions. Verify adversarial set matches config. Verify expected answers section exists.

#### SC-004: Run holdout scenarios against delivered code

**Priority:** P1 (must-have)
**Source:** PRODUCT_SPEC_FRAMEWORK.md D7 "Holdout Scenarios" — "After a builder delivers... the reviewer runs every holdout scenario."

**GIVEN** a builder agent has delivered code for a task (results file exists with PASS status)
**WHEN** the operator runs `factory holdout --spec-dir test/ --install-root /path/to/installed`
**THEN** the orchestrator reads D9, executes each holdout scenario's Setup/Execute/Verify steps against the installed code, and reports per-scenario PASS/FAIL
**AND** for each FAIL, the report traces to: the D2 scenario(s) the holdout validates, the D4 contract(s) being tested, and the D8 task responsible
**AND** overall verdict follows the Run Protocol from D9: all P0 must pass, P1 threshold met

**Testing Approach:** Run holdouts against the test/ HO1 spec with a mock installed root. Inject one failing holdout. Verify the failure report names the correct D2 scenario, D4 contract, and D8 task.

#### SC-005: Full pipeline run (validate → generate → prompt → dispatch → holdout)

**Priority:** P2 (important)
**Source:** PRODUCT_SPEC_FRAMEWORK.md "Repeatable Process" — steps 1-8

**GIVEN** a complete product spec and a configured builder agent endpoint (Claude API or Claude Code subprocess)
**WHEN** the operator runs `factory run --spec-dir test/ --output-dir output/`
**THEN** the orchestrator executes the full pipeline: validate spec → generate handoffs → generate prompts → dispatch builder agents (sequentially per D8 dependency graph) → collect results → run holdouts → produce final report
**AND** the final report contains: per-task status (PASS/FAIL/BLOCKED), per-holdout status, overall verdict, total tokens consumed, total time elapsed

**Testing Approach:** Run full pipeline against the test/ spec with a mock builder agent that returns pre-canned results. Verify the pipeline executes tasks in D8 dependency order. Verify holdouts run after all tasks complete.

### Edge Cases and Failure Modes

#### SC-006: Incomplete spec — missing document

**Priority:** P1 (must-have)
**Source:** D1 Article 5 (Validate Before Dispatch), D1 Article 7 (No Silent Failures)

**GIVEN** a spec directory missing D3_DATA_MODEL.md
**WHEN** the operator runs `factory validate --spec-dir incomplete/`
**THEN** the orchestrator reports FAIL with: "Missing required document: D3_DATA_MODEL.md"
**AND** does not proceed to generation

**Testing Approach:** Remove D3 from a copy of test/. Run validate. Verify exact error message.

#### SC-007: Incomplete spec — unresolved D6 clarification

**Priority:** P1 (must-have)
**Source:** PRODUCT_SPEC_FRAMEWORK.md D6 — "D7 (Plan) cannot begin until: (a) zero OPEN clarifications remain"

**GIVEN** a spec where D6 contains a clarification with STATUS: OPEN
**WHEN** the operator runs `factory validate --spec-dir open_gaps/`
**THEN** the orchestrator reports FAIL with: "D6 has 1 OPEN clarification(s): CLR-001 [title]. Resolve before proceeding."

**Testing Approach:** Add an OPEN clarification to D6 in a copy of test/. Run validate. Verify it names the specific clarification.

#### SC-008: Builder agent fails a task

**Priority:** P1 (must-have)
**Source:** BUILDER_HANDOFF_STANDARD.md "Results File" — Status: FAIL

**GIVEN** a builder agent returns a results file with Status: FAIL for task T-003
**WHEN** the orchestrator processes the result
**THEN** the orchestrator marks T-003 as FAILED, checks the D8 dependency graph for tasks blocked by T-003, marks blocked tasks as BLOCKED, and reports which tasks can still proceed (those not depending on T-003)

**Testing Approach:** Mock a builder that fails T-003 in the test/ D8 dependency graph. Verify T-005 (depends on T-003) is marked BLOCKED. Verify T-003's parallel peer T-004 (if independent) is not blocked.

#### SC-009: Holdout scenario fails

**Priority:** P1 (must-have)
**Source:** D1 Article 6 (Holdout Failures Trace to Specs)

**GIVEN** a completed build where all builder tests pass
**WHEN** the orchestrator runs holdout HS-001 and the verify step returns FAIL
**THEN** the orchestrator produces a failure report containing: holdout ID (HS-001), D2 scenarios it validates (from D9 coverage matrix), D4 contracts it tests, D8 task responsible, the actual vs. expected output, and recommendation (re-dispatch task or revise spec)

**Testing Approach:** Mock a holdout that fails for HS-001. Verify the report contains all required fields and traces correctly.

#### SC-010: D8 dependency cycle

**Priority:** P1 (must-have)
**Source:** D1 Article 7 (No Silent Failures)

**GIVEN** a D8 document where T-002 depends on T-003 and T-003 depends on T-002
**WHEN** the operator runs `factory validate --spec-dir cyclic/`
**THEN** the orchestrator reports FAIL with: "Dependency cycle detected in D8: T-002 → T-003 → T-002"

**Testing Approach:** Create a D8 with a cycle. Run validate. Verify cycle is reported with the specific task IDs.

## Deferred Capabilities

#### DEF-001: Parallel Agent Dispatch

**What:** Launching multiple builder agents concurrently for tasks in the same D8 phase marked as parallel.
**Why Deferred:** Sequential dispatch is simpler and sufficient for validating the pipeline. Parallel dispatch requires coordination logic (shared filesystem, result aggregation, failure propagation).
**Trigger:** When build time for a full spec exceeds acceptable limits (e.g., > 2 hours for a 7-task spec).
**Impact if Never Added:** Builds take longer but complete correctly. Acceptable for development use.

#### DEF-002: Spec Authoring Assistance

**What:** Using an LLM to help fill out D1-D10 templates from design documents.
**Why Deferred:** The orchestrator's job is dispatch and validation, not authoring. Authoring assistance is a separate tool.
**Trigger:** When the manual effort to fill D1-D10 (estimated 2-4 hours per component) becomes a bottleneck.
**Impact if Never Added:** Humans fill out specs manually. This is the current workflow.

#### DEF-003: Live Agent Monitoring

**What:** Real-time observation of builder agent progress (token usage, files written, test results) during execution.
**Why Deferred:** The orchestrator collects results after completion. Live monitoring requires streaming integration with the builder agent runtime.
**Trigger:** When long-running builds (> 30 minutes) need progress visibility.
**Impact if Never Added:** Operator waits for completion. Acceptable for initial use.

## Success Criteria

- [ ] Validate detects all spec incompleteness types: missing docs, orphan scenarios, OPEN D6 items, D8 cycles
- [ ] Generated handoffs pass structural validation against BUILDER_HANDOFF_STANDARD.md (all 10 sections present)
- [ ] Generated prompts pass structural validation against BUILDER_PROMPT_CONTRACT.md (13 questions, correct template)
- [ ] Zero D9 content appears in any builder-visible artifact
- [ ] Holdout failure reports trace to specific D2 scenarios, D4 contracts, and D8 tasks
- [ ] Full pipeline completes end-to-end on the test/ HO1 spec (validate → generate → prompt → mock dispatch → holdout)
- [ ] Orchestrator produces deterministic output given identical input (D1 Article 8)

## Clarification Markers

[NEEDS CLARIFICATION]: For SC-005 full pipeline dispatch — should the orchestrator call the Claude API directly, invoke Claude Code as a subprocess, or support both? The answer affects D4 contracts (dispatch interface shape).

[NEEDS CLARIFICATION]: For SC-004 holdout execution — should holdout verify steps run as bash commands (subprocess), Python functions (imported), or both? The test/ D9 holdouts describe bash commands, but Python assertions may be more reliable for structural checks.
