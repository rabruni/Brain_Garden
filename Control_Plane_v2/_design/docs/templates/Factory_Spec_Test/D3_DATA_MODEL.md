# D3: Data Model — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Spec Version:** 0.1.0 (matches D2)
**Status:** Draft
**Shared Entities:** 3

---

## Entities

### E-001: ProductSpec (PRIVATE)

**Scope:** PRIVATE — the orchestrator's internal representation of D1-D10.
**Source:** D2 SC-001 (validate), SC-002 (generate)
**Description:** The parsed, validated representation of a complete product spec. Created by reading a spec directory.

| Field | Type | Required | Description | Constraints |
|-------|------|----------|-------------|-------------|
| spec_dir | string | yes | Path to the spec directory | Must exist, must contain D1-D10 files |
| component_name | string | yes | Extracted from D2 metadata "Component" field | Non-empty |
| package_id | string | yes | Extracted from D2 metadata "Package ID" field | Pattern: PKG-*-NNN or "TBD" |
| constitution | ConstitutionDoc | yes | Parsed D1 | See E-002 |
| specification | SpecDoc | yes | Parsed D2 | Contains scenarios list |
| data_model | DataModelDoc | yes | Parsed D3 | Contains entities list |
| contracts | ContractsDoc | yes | Parsed D4 | Contains inbound, outbound, side-effect, error contracts |
| research | ResearchDoc | yes | Parsed D5 | Contains research log, decisions |
| gap_analysis | GapAnalysisDoc | yes | Parsed D6 | Contains gaps, clarifications |
| plan | PlanDoc | yes | Parsed D7 | Contains architecture, file creation order, testing strategy |
| tasks | TasksDoc | yes | Parsed D8 | Contains task list with dependencies |
| holdouts | HoldoutDoc | yes | Parsed D9 | Contains holdout scenarios — NEVER exposed to builders |
| agent_context | AgentContextDoc | yes | Parsed D10 | Contains commands, tool rules, conventions |

**Example:**
```json
{
  "spec_dir": "test/",
  "component_name": "HO1 Cognitive Process",
  "package_id": "PKG-HO1-EXECUTOR-002",
  "constitution": {"version": "1.0.0", "articles": ["..."], "boundaries": {"always": [], "ask_first": [], "never": []}},
  "specification": {"scenarios": [{"id": "SC-001", "priority": "P1", "given": "...", "when": "...", "then": "..."}]},
  "tasks": {"tasks": [{"id": "T-001", "phase": 0, "depends_on": [], "scenarios": ["SC-001"]}]},
  "holdouts": {"scenarios": [{"id": "HS-001", "priority": "P0", "validates": ["SC-009"]}]}
}
```

**Invariants:**
- gap_analysis must have zero OPEN clarifications for the spec to be valid
- Every scenario ID in tasks.tasks[].scenarios must exist in specification.scenarios
- Every contract ID in tasks.tasks[].contracts must exist in contracts

### E-002: ValidationResult (SHARED)

**Scope:** SHARED — consumed by the operator and by downstream orchestrator stages.
**Used By:** Operator (CLI output), HandoffGenerator (gate check), PipelineRunner (pre-flight)
**Source:** D2 SC-001, SC-006, SC-007, SC-010
**Description:** The result of validating a product spec for completeness and consistency.

| Field | Type | Required | Description | Constraints |
|-------|------|----------|-------------|-------------|
| status | enum | yes | Overall result | PASS, FAIL |
| spec_dir | string | yes | Path that was validated | |
| component_name | string | no | Extracted if spec is parseable | |
| checks | list[CheckResult] | yes | Individual check results | At least 1 |
| summary | dict | no | Counts: documents, scenarios, tasks, holdouts | Present when PASS |

**CheckResult fields:**

| Field | Type | Required | Description | Constraints |
|-------|------|----------|-------------|-------------|
| check_name | string | yes | What was checked | e.g., "d6_no_open_items" |
| status | enum | yes | PASS or FAIL | |
| message | string | yes | Human-readable result | |
| details | list[string] | no | Specific items that failed | e.g., ["SC-003 not covered by D8"] |

**Example:**
```json
{
  "status": "FAIL",
  "spec_dir": "test/",
  "component_name": "HO1 Cognitive Process",
  "checks": [
    {"check_name": "all_documents_present", "status": "PASS", "message": "10/10 documents found"},
    {"check_name": "d6_no_open_items", "status": "PASS", "message": "0 OPEN clarifications"},
    {"check_name": "d2_scenarios_covered", "status": "FAIL", "message": "1 scenario not covered by D8", "details": ["SC-003"]}
  ],
  "summary": null
}
```

### E-003: Handoff (SHARED)

**Scope:** SHARED — produced by orchestrator, consumed by builder agents.
**Used By:** Builder agent (reads spec), PromptGenerator (extracts mission), HoldoutRunner (traces failures)
**Source:** D2 SC-002
**Description:** A generated handoff document following BUILDER_HANDOFF_STANDARD.md format.

| Field | Type | Required | Description | Constraints |
|-------|------|----------|-------------|-------------|
| handoff_id | string | yes | Unique handoff identifier | Pattern: H-FACTORY-NNN |
| task_id | string | yes | D8 task this handoff implements | Must exist in ProductSpec.tasks |
| mission | string | yes | One paragraph from D8 task description | Non-empty |
| scenarios | list[string] | yes | D2 scenario IDs covered | Non-empty |
| contracts | list[string] | yes | D4 contract IDs implemented | |
| critical_constraints | list[string] | yes | From D1 articles | Non-empty |
| architecture | string | yes | From D7 plan, scoped to this task | |
| implementation_steps | list[string] | yes | From D8 acceptance criteria | |
| package_plan | dict | yes | From D7 file structure | |
| test_plan | list[TestEntry] | yes | From D2 scenarios mapped to this task | |
| existing_code_refs | list[dict] | no | From D10 | |
| verification_commands | list[string] | yes | From D10 commands section | |
| files_summary | list[dict] | yes | From D7 file creation order | |
| design_principles | list[string] | yes | From D1 filtered to this task | |
| output_path | string | yes | Where the handoff markdown was written | |

**Example:**
```json
{
  "handoff_id": "H-FACTORY-001",
  "task_id": "T-001",
  "mission": "Extract ContractLoader as a standalone shared service in HOT/kernel/",
  "scenarios": ["SC-001", "SC-002", "SC-005"],
  "contracts": ["IN-001", "OUT-001", "ERR-002"],
  "critical_constraints": ["ALL work in _reboot/_staging/", "DTT per-behavior cycles"],
  "output_path": "handoffs/H-FACTORY-001/H-FACTORY-001_BUILDER_HANDOFF.md"
}
```

### E-004: AgentPrompt (PRIVATE)

**Scope:** PRIVATE — produced by orchestrator, dispatched to builder.
**Source:** D2 SC-003
**Description:** A generated agent prompt following BUILDER_PROMPT_CONTRACT.md template.

| Field | Type | Required | Description | Constraints |
|-------|------|----------|-------------|-------------|
| handoff_id | string | yes | Which handoff this prompt dispatches | Must match a Handoff |
| contract_version | string | yes | BUILDER_PROMPT_CONTRACT version used | Semantic version |
| mission_oneliner | string | yes | One-line mission for prompt header | |
| mandatory_rules | list[string] | yes | 7 rules from prompt contract | Exactly 7 |
| verification_questions | list[string] | yes | 10 task-specific questions | Exactly 10 |
| adversarial_questions | list[string] | yes | 3 adversarial questions | Exactly 3 |
| expected_answers | list[string] | yes | For reviewer — not visible to agent | Exactly 13 |
| prompt_text | string | yes | The full rendered prompt | |

### E-005: DispatchRecord (SHARED)

**Scope:** SHARED — written to dispatch ledger, consumed by report generator.
**Used By:** PipelineRunner, ReportGenerator, HoldoutRunner
**Source:** D2 SC-005, SC-008
**Description:** A record of one handoff dispatch and its outcome.

| Field | Type | Required | Description | Constraints |
|-------|------|----------|-------------|-------------|
| dispatch_id | string | yes | Unique dispatch ID | Auto-generated UUID |
| handoff_id | string | yes | Which handoff was dispatched | |
| task_id | string | yes | D8 task ID | |
| timestamp_dispatched | string | yes | When the agent was launched | ISO 8601 |
| timestamp_completed | string | no | When the agent returned | ISO 8601, present when done |
| status | enum | yes | DISPATCHED, COMPLETED, FAILED, BLOCKED | |
| results_path | string | no | Path to builder's results file | Present when completed |
| error | string | no | Error description | Present when FAILED |
| tokens_used | int | no | Total tokens consumed | Present when completed |

### E-006: HoldoutResult (SHARED)

**Scope:** SHARED — produced by holdout runner, consumed by report generator.
**Used By:** ReportGenerator, operator
**Source:** D2 SC-004, SC-009
**Description:** Result of running one holdout scenario.

| Field | Type | Required | Description | Constraints |
|-------|------|----------|-------------|-------------|
| holdout_id | string | yes | D9 scenario ID (e.g., HS-001) | |
| priority | enum | yes | P0, P1, P2 | From D9 |
| status | enum | yes | PASS, FAIL, ERROR | |
| validates_scenarios | list[string] | yes | D2 scenario IDs this holdout tests | From D9 coverage matrix |
| validates_contracts | list[string] | yes | D4 contract IDs tested | From D9 |
| responsible_task | string | yes | D8 task that should satisfy this | Derived from D8/D2 mapping |
| actual_output | string | no | What was observed | Present on FAIL |
| expected_output | string | no | What was expected | Present on FAIL |
| error_message | string | no | Error details | Present on ERROR |

**Example:**
```json
{
  "holdout_id": "HS-001",
  "priority": "P0",
  "status": "FAIL",
  "validates_scenarios": ["SC-009"],
  "validates_contracts": ["ERR-006", "SIDE-001"],
  "responsible_task": "T-004",
  "actual_output": "Work order returned in COMPLETED state",
  "expected_output": "Work order returned in FAILED state with error_code OUTPUT_VALIDATION_FAILED"
}
```

### E-007: FactoryReport (SHARED)

**Scope:** SHARED — final output of the orchestrator.
**Used By:** Operator
**Source:** D2 SC-005
**Description:** The complete report of a factory run.

| Field | Type | Required | Description | Constraints |
|-------|------|----------|-------------|-------------|
| spec_dir | string | yes | Input spec directory | |
| component_name | string | yes | What was being built | |
| validation | ValidationResult | yes | Spec validation result | |
| dispatches | list[DispatchRecord] | yes | Per-task dispatch results | |
| holdouts | list[HoldoutResult] | yes | Per-holdout results | |
| verdict | enum | yes | ACCEPT, REJECT, PARTIAL | |
| verdict_reason | string | yes | Why this verdict | |
| total_tokens | int | yes | Sum of all dispatch tokens | |
| total_duration_ms | int | yes | Wall-clock time for full run | |

---

## Entity Relationship Map

```
ProductSpec (PRIVATE)
  |
  |-- validated by --> ValidationResult (SHARED)
  |
  |-- decomposes into --> Handoff[1+] (SHARED)
  |       |
  |       |-- generates --> AgentPrompt (PRIVATE)
  |       |
  |       |-- dispatched as --> DispatchRecord (SHARED)
  |
  |-- holdouts from D9 --> HoldoutResult[1+] (SHARED)
  |
  |-- all collected into --> FactoryReport (SHARED)
```

---

## Migration Notes

No prior model — greenfield. The orchestrator is a new tool. The test/ directory's D1-D10 documents serve as the schema definition for what the orchestrator must parse.
