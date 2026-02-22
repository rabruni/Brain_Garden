# D8: Tasks — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Plan Version:** D7 v0.1.0
**Status:** Draft
**Total Tasks:** 7
**Parallel Opportunities:** 2 pairs

---

## MVP Scope

P1 scenarios from D2: SC-001 through SC-010 (all 10). SC-005 (full pipeline) is P2 but included because it composes the P1 components.
P3 deferred: parallel dispatch (DEF-001), spec authoring assistance (DEF-002), live monitoring (DEF-003).

---

## Phase 0: Foundation

#### T-001: SpecParser — Read and Parse D1-D10

**Phase:** 0 — Foundation
**Parallel/Serial:** Serial (everything depends on parsing)
**Dependency:** None
**Scope:** L (large)
**Scenarios Satisfied:** Foundation for all scenarios
**Contracts Implemented:** Prerequisite for all contracts

**Acceptance Criteria:**
- `spec_parser.py` reads a directory of D-template markdown files
- Parses D1: extracts articles (rule, why, test, violations), boundary definitions (always, ask_first, never)
- Parses D2: extracts scenarios (ID, priority, GIVEN/WHEN/THEN, testing approach), deferred capabilities, success criteria, NEEDS CLARIFICATION markers
- Parses D3: extracts entities (name, scope, fields with types/constraints), relationship map
- Parses D4: extracts inbound, outbound, side-effect, and error contracts with their fields and scenarios
- Parses D5: extracts research questions with decisions
- Parses D6: extracts gaps with status (RESOLVED/OPEN/ASSUMED), clarifications with status
- Parses D7: extracts file creation order, component list, testing strategy
- Parses D8: extracts tasks with IDs, dependencies, phases, scenarios satisfied, contracts implemented
- Parses D9: extracts holdout scenarios with IDs, priority, validates/contracts fields, setup/execute/verify steps
- Parses D10: extracts commands, tool rules, coding conventions
- Returns ProductSpec (D3 E-001)
- Unit tests: 12+ (one per D-document format + error cases: missing file, malformed heading, empty document)

#### T-002: SpecValidator — Validate Completeness

**Phase:** 0 — Foundation
**Parallel/Serial:** Serial (depends on T-001)
**Dependency:** T-001
**Scope:** M (medium)
**Scenarios Satisfied:** SC-001, SC-006, SC-007, SC-010
**Contracts Implemented:** IN-001, OUT-001, ERR-001

**Acceptance Criteria:**
- `spec_validator.py` takes a ProductSpec and runs these checks:
  - all_documents_present: 10 D-documents exist
  - d6_no_open_items: zero clarifications with STATUS: OPEN
  - d2_scenarios_covered: every D2 scenario ID appears in at least one D8 task's scenarios_satisfied
  - d4_contracts_covered: every D4 contract ID appears in at least one D8 task's contracts_implemented
  - d9_minimum_holdouts: D9 has >= 3 holdout scenarios
  - d8_no_dependency_cycles: topological sort of D8 task dependencies succeeds
- Returns ValidationResult (D3 E-002) with per-check status and details
- Unit tests: 8+ (each check pass/fail, cycle detection with complex graph)

---

## Phase 1: Generation

#### T-003: HandoffGenerator — Generate Handoff Documents

**Phase:** 1 — Generation
**Parallel/Serial:** Parallel with T-004
**Dependency:** T-002 (validation must pass)
**Scope:** M (medium)
**Scenarios Satisfied:** SC-002
**Contracts Implemented:** IN-002, OUT-002, ERR-002

**Acceptance Criteria:**
- `handoff_generator.py` generates one markdown file per D8 task
- Each handoff follows BUILDER_HANDOFF_STANDARD.md (10 required sections)
- Section 1 (Mission): from D8 task description
- Section 2 (Critical Constraints): from D1 articles, filtered to task relevance
- Section 3 (Architecture): from D7 plan, scoped to this task's files
- Section 4 (Implementation Steps): from D8 acceptance criteria
- Section 5 (Package Plan): from D7 file structure
- Section 6 (Test Plan): from D2 scenarios mapped to this task → concrete test methods
- Section 7 (Existing Code): from D10 references
- Section 8 (E2E Verification): from D10 commands
- Section 9 (Files Summary): from D7 file creation order, scoped to this task
- Section 10 (Design Principles): from D1, scoped to this task
- Traceability: handoff header includes D2 scenario IDs, D4 contract IDs, D8 task ID
- NO D9 content in any handoff (D1 Article 2)
- Writes handoff_index.json mapping task IDs to handoff paths
- Unit tests: 10+ (each section generated correctly, traceability present, D9 exclusion verified, index file correct)

#### T-004: PromptGenerator — Generate Agent Prompts

**Phase:** 1 — Generation
**Parallel/Serial:** Parallel with T-003
**Dependency:** T-002 (needs validated spec for D2/D4 question extraction)
**Scope:** M (medium)
**Scenarios Satisfied:** SC-003
**Contracts Implemented:** IN-003, OUT-003

**Acceptance Criteria:**
- `prompt_generator.py` generates one agent prompt per handoff
- Follows BUILDER_PROMPT_CONTRACT.md template exactly
- Fills: HANDOFF_ID, ONE_LINE_MISSION, CONTRACT_VERSION, 7 mandatory rules
- Generates 10 verification questions from the task's D2 scenarios and D4 contracts:
  - Questions 1-3: scope (from D2 component purpose, what-it-is-not)
  - Questions 4-6: technical (from D4 contracts, D3 entities relevant to task)
  - Questions 7-8: packaging (from D7 package plan)
  - Question 9: test count (from D8 acceptance criteria)
  - Question 10: integration (from D4 side-effect contracts)
- Selects adversarial set: genesis (default) or infrastructure (from config)
- Generates expected answers section (from D2/D4 content)
- Writes prompt file + expected answers file (separate — expected answers not visible to agent)
- Unit tests: 8+ (template rendering, question count, adversarial set selection, expected answers separate from prompt)

---

## Phase 2: Execution

#### T-005: AgentDispatcher — Dispatch Builder Agents

**Phase:** 2 — Execution
**Parallel/Serial:** Serial (depends on generation)
**Dependency:** T-003, T-004
**Scope:** M (medium)
**Scenarios Satisfied:** SC-005, SC-008
**Contracts Implemented:** IN-005, SIDE-001, ERR-003

**Acceptance Criteria:**
- `agent_dispatcher.py` launches Claude Code as subprocess with agent prompt
- Sets working directory to spec staging area
- Passes prompt via `-p` flag or stdin
- Waits for process completion (with configurable timeout)
- Checks for results file at expected path after completion
- Records DispatchRecord (D3 E-005) to dispatch ledger (JSONL)
- On process failure/timeout: marks dispatch FAILED with error detail
- On results file missing: marks dispatch FAILED
- On results file present: parses Status field, marks COMPLETED or BUILDER_TASK_FAILED
- Respects D8 dependency order: dispatches tasks per topological sort, skipping tasks whose dependencies FAILED (marks as BLOCKED)
- Unit tests: 8+ (subprocess launch mock, timeout handling, results file parsing, dependency ordering, BLOCKED propagation, ledger write)

---

## Phase 3: Validation

#### T-006: HoldoutRunner — Execute D9 Holdouts

**Phase:** 3 — Validation
**Parallel/Serial:** Parallel with T-007
**Dependency:** T-005 (builders must complete first, but holdout code is independent)
**Scope:** M (medium)
**Scenarios Satisfied:** SC-004, SC-009
**Contracts Implemented:** IN-004, OUT-004, ERR-004

**Acceptance Criteria:**
- `holdout_runner.py` reads D9 holdout scenarios from ProductSpec
- For each holdout: runs Setup commands (bash subprocess), runs Execute commands, runs Verify commands
- Verify: exit code 0 = PASS, non-zero = FAIL
- Produces HoldoutResult (D3 E-006) per scenario with traceability (validates_scenarios, validates_contracts, responsible_task)
- responsible_task derived by: holdout.validates_scenarios → D8 task that covers those scenarios
- Follows Run Protocol: P0 first, stop on P0 failure, then P1
- On command execution error (not FAIL — command couldn't run): marks as ERROR
- Unit tests: 8+ (setup/execute/verify flow, exit code interpretation, P0 gate, ERROR vs FAIL distinction, traceability derivation, subprocess mock)

#### T-007: ReportGenerator + E2E Pipeline Test

**Phase:** 3 — Validation
**Parallel/Serial:** Parallel with T-006
**Dependency:** T-005 (needs dispatch results), T-006 (needs holdout results — can use mocked)
**Scope:** M (medium)
**Scenarios Satisfied:** SC-005
**Contracts Implemented:** OUT-005

**Acceptance Criteria:**
- `report_generator.py` assembles FactoryReport (D3 E-007) from ValidationResult + DispatchRecords + HoldoutResults
- Computes verdict: ACCEPT (all P0 holdouts pass, all tasks COMPLETED), REJECT (any P0 holdout fails or critical task FAILED), PARTIAL (some tasks completed, others blocked/failed)
- Includes: per-task status, per-holdout status, total tokens, total duration
- `main.py` CLI wires all components together with subcommands: validate, generate, prompts, holdout, run
- E2E test: runs `factory validate` + `factory generate` + `factory prompts` on the test/ spec directory. Verifies handoffs and prompts are generated correctly. Runs `factory holdout` with mocked install root.
- E2E tests: 3+ (validate test/ spec, generate + verify handoffs, full pipeline with mocked dispatch)

---

## Task Dependency Graph

```
T-001 (SpecParser)
  │
  ▼
T-002 (SpecValidator)
  │
  ├──────────────┐
  ▼              ▼
T-003 (Handoff) T-004 (Prompts)  ◄── parallel
  │              │
  └──────┬───────┘
         ▼
T-005 (Dispatcher)
         │
         ├──────────────┐
         ▼              ▼
T-006 (Holdouts) T-007 (Reports + E2E)  ◄── parallel
```

---

## Summary

| Task | Phase | Scope | Serial/Parallel | Scenarios |
|------|-------|-------|-----------------|-----------|
| T-001 | 0 | L | Serial | Foundation |
| T-002 | 0 | M | Serial | SC-001, SC-006, SC-007, SC-010 |
| T-003 | 1 | M | Parallel w/ T-004 | SC-002 |
| T-004 | 1 | M | Parallel w/ T-003 | SC-003 |
| T-005 | 2 | M | Serial | SC-005, SC-008 |
| T-006 | 3 | M | Parallel w/ T-007 | SC-004, SC-009 |
| T-007 | 3 | M | Parallel w/ T-006 | SC-005 |

**Total: 7 tasks across 4 phases. 2 parallelizable pairs. Estimated 5 serial handoff waves.**

**MVP Tasks:** T-001 through T-007 (all — each is necessary for the pipeline).
