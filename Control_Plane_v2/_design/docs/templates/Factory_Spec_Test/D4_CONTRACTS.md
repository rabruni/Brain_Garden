# D4: Contracts — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Spec Version:** 0.1.0 (matches D2)
**Data Model:** D3 v0.1.0
**Status:** Draft

---

## Inbound Contracts

#### IN-001: Validate Spec

**Caller:** Operator (CLI)
**Trigger:** `factory validate --spec-dir <path>`
**Scenarios:** SC-001, SC-006, SC-007, SC-010

**Request Shape:** CLI arguments

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| spec_dir | string | yes | Path to directory containing D1-D10 documents |

**Constraints:**
- spec_dir must exist and be a directory
- Directory must contain files matching D*_*.md pattern

**Example:** `factory validate --spec-dir _design/docs/templates/test/`

#### IN-002: Generate Handoffs

**Caller:** Operator (CLI)
**Trigger:** `factory generate --spec-dir <path> --output-dir <path>`
**Scenarios:** SC-002

**Request Shape:** CLI arguments

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| spec_dir | string | yes | Path to validated spec |
| output_dir | string | yes | Where to write generated handoffs |

**Constraints:**
- Spec must pass validation (IN-001) first — orchestrator runs validation internally before generating
- output_dir is created if it doesn't exist

#### IN-003: Generate Prompts

**Caller:** Operator (CLI)
**Trigger:** `factory prompts --handoffs-dir <path> --spec-dir <path>`
**Scenarios:** SC-003

**Request Shape:** CLI arguments

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| handoffs_dir | string | yes | Directory containing generated handoffs |
| spec_dir | string | yes | Original spec directory (for D2/D4 question extraction) |

#### IN-004: Run Holdouts

**Caller:** Operator (CLI)
**Trigger:** `factory holdout --spec-dir <path> --install-root <path>`
**Scenarios:** SC-004, SC-009

**Request Shape:** CLI arguments

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| spec_dir | string | yes | Spec directory (for D9 holdouts) |
| install_root | string | yes | Path to the installed/built code to test against |

**Constraints:**
- install_root must exist
- D9 must have at least 1 holdout scenario

#### IN-005: Full Pipeline Run

**Caller:** Operator (CLI)
**Trigger:** `factory run --spec-dir <path> --output-dir <path>`
**Scenarios:** SC-005

**Request Shape:** CLI arguments

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| spec_dir | string | yes | Spec directory |
| output_dir | string | yes | Output directory for all artifacts |
| agent_backend | string | no | "claude-api" or "claude-code" (default: "claude-code") |

---

## Outbound Contracts

#### OUT-001: Validation Report

**Consumer:** Operator (stdout + JSON file)
**Scenarios:** SC-001, SC-006, SC-007, SC-010

**Response Shape:** ValidationResult (D3 E-002)

**Example Response (success):**
```json
{
  "status": "PASS",
  "spec_dir": "test/",
  "component_name": "HO1 Cognitive Process",
  "checks": [
    {"check_name": "all_documents_present", "status": "PASS", "message": "10/10 documents found"},
    {"check_name": "d6_no_open_items", "status": "PASS", "message": "0 OPEN clarifications"},
    {"check_name": "d2_scenarios_covered", "status": "PASS", "message": "10/10 scenarios covered by D8"},
    {"check_name": "d4_contracts_covered", "status": "PASS", "message": "12/12 contracts assigned to D8 tasks"},
    {"check_name": "d9_minimum_holdouts", "status": "PASS", "message": "7 holdout scenarios (>= 3)"},
    {"check_name": "d8_no_dependency_cycles", "status": "PASS", "message": "7 tasks, 0 cycles"}
  ],
  "summary": {"documents": 10, "scenarios": 10, "tasks": 7, "holdouts": 7}
}
```

**Example Response (failure):**
```json
{
  "status": "FAIL",
  "spec_dir": "incomplete/",
  "checks": [
    {"check_name": "all_documents_present", "status": "FAIL", "message": "9/10 documents found", "details": ["Missing: D3_DATA_MODEL.md"]}
  ]
}
```

#### OUT-002: Generated Handoff Files

**Consumer:** Builder agent (reads markdown), PromptGenerator (reads structured data)
**Scenarios:** SC-002

**Response Shape:** Handoff markdown files + index JSON

Files written:
- `<output_dir>/H-FACTORY-NNN/H-FACTORY-NNN_BUILDER_HANDOFF.md` per task
- `<output_dir>/handoff_index.json` (maps task IDs to handoff IDs and file paths)

#### OUT-003: Generated Prompt Files

**Consumer:** Agent dispatcher (reads prompt text)
**Scenarios:** SC-003

**Response Shape:** Prompt markdown files + expected answers

Files written:
- `<output_dir>/H-FACTORY-NNN/H-FACTORY-NNN_AGENT_PROMPT.md` per handoff
- `<output_dir>/H-FACTORY-NNN/H-FACTORY-NNN_EXPECTED_ANSWERS.md` per handoff (reviewer only)

#### OUT-004: Holdout Report

**Consumer:** Operator
**Scenarios:** SC-004, SC-009

**Response Shape:** List of HoldoutResult (D3 E-006) + verdict

```json
{
  "holdouts": [
    {"holdout_id": "HS-001", "priority": "P0", "status": "PASS", ...},
    {"holdout_id": "HS-002", "priority": "P0", "status": "FAIL", ...}
  ],
  "p0_pass": false,
  "p0_total": 4,
  "p0_passed": 3,
  "verdict": "REJECT",
  "verdict_reason": "P0 holdout HS-002 failed — component not accepted"
}
```

#### OUT-005: Factory Report

**Consumer:** Operator
**Scenarios:** SC-005

**Response Shape:** FactoryReport (D3 E-007)

---

## Side-Effect Contracts

#### SIDE-001: Dispatch Ledger Write

**Target System:** Dispatch ledger (append-only JSONL file)
**Trigger:** Every time a builder agent is dispatched or returns a result
**Scenarios:** SC-005, SC-008

**Write Shape:** DispatchRecord (D3 E-005)

**Ordering Guarantee:** Written BEFORE dispatching the agent (DISPATCHED event) and AFTER receiving results (COMPLETED/FAILED event).
**Failure Behavior:** If ledger write fails, log warning and continue. Dispatch ledger is for audit — its failure does not block the pipeline.

#### SIDE-002: Handoff File Writes

**Target System:** Filesystem (output_dir)
**Trigger:** During generate step (SC-002)
**Scenarios:** SC-002

**Write Shape:** Markdown files per BUILDER_HANDOFF_STANDARD.md format

**Ordering Guarantee:** All handoffs written before generate step reports success.
**Failure Behavior:** If any file write fails, report FAIL for the entire generate step. Do not produce partial handoff sets.

---

## Error Contracts

#### ERR-001: SPEC_INCOMPLETE

**Condition:** Spec directory missing required documents or failing validation checks (SC-006, SC-007, SC-010)
**Scenarios:** SC-006, SC-007, SC-010
**Caller Action:** Fix the spec and re-run validate.

#### ERR-002: GENERATION_FAILED

**Condition:** Handoff generation fails (e.g., D8 task references nonexistent D2 scenario)
**Scenarios:** SC-002
**Caller Action:** Fix the spec (D8/D2 mismatch) and re-run generate.

#### ERR-003: DISPATCH_FAILED

**Condition:** Builder agent could not be launched or returned an error (not a FAIL result — an infrastructure error)
**Scenarios:** SC-005, SC-008
**Caller Action:** Check agent backend configuration. Retry or fix infrastructure.

#### ERR-004: HOLDOUT_EXECUTION_ERROR

**Condition:** Holdout scenario's setup or execute steps fail to run (not a FAIL result — the test itself could not execute)
**Scenarios:** SC-004
**Caller Action:** Check install_root and holdout commands. Fix and re-run.

---

## Error Code Enum

| Code | Meaning | Retryable |
|------|---------|-----------|
| SPEC_INCOMPLETE | Product spec missing docs or failing checks | no (fix spec) |
| GENERATION_FAILED | Handoff generation hit an inconsistency | no (fix spec) |
| DISPATCH_FAILED | Builder agent infrastructure error | yes (after fixing infra) |
| HOLDOUT_EXECUTION_ERROR | Holdout test could not run | yes (after fixing env) |
| BUILDER_TASK_FAILED | Builder returned FAIL status | yes (re-dispatch or revise spec) |
| HOLDOUT_SCENARIO_FAILED | Holdout verify step returned FAIL | no (fix code or revise spec) |
