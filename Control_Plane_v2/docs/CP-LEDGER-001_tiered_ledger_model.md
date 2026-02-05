# CP-LEDGER-001: Tiered Ledger Model

**Document ID**: CP-LEDGER-001
**Version**: 1.0.0
**Status**: NORMATIVE
**Plane**: HO3

---

## 1. Purpose

This document specifies the taxonomy, structure, and access rules for ledgers in the Control Plane. Ledgers serve as externalized memory for stateless agents.

---

## 2. Ledger Taxonomy

| Ledger Type | Code | Tier | Purpose |
|-------------|------|------|---------|
| Intent | L-INTENT | HO3 | Strategic goals and framework evolution |
| Work Order | L-WORKORDER | HO2 | Authorized units of work |
| Execution | L-EXEC | HO1 | Task execution logs |
| Package | L-PACKAGE | HO3 | Package install/upgrade/uninstall history |
| Evidence | L-EVIDENCE | HO1 | Artifact provenance and quality evidence |

---

## 3. Ledger Files by Tier

### 3.1 HO3 (Governance)

| File | Type | Contents |
|------|------|----------|
| `ledger/governance.jsonl` | L-INTENT | Framework changes, policy decisions |
| `ledger/packages.jsonl` | L-PACKAGE | Package lifecycle events |

### 3.2 HO2 (Work Order)

| File | Type | Contents |
|------|------|----------|
| `planes/ho2/ledger/workorder.jsonl` | L-WORKORDER | Work order lifecycle |
| `planes/ho2/ledger/session-{id}.jsonl` | L-WORKORDER | Per-session state |

### 3.3 HO1 (Worker)

| File | Type | Contents |
|------|------|----------|
| `planes/ho1/ledger/worker.jsonl` | L-EXEC | Task execution events |
| `planes/ho1/ledger/evidence-{id}.jsonl` | L-EVIDENCE | Evidence for specific work |

---

## 4. Write Authority

### 4.1 Who May Write

| Ledger Type | May Write | Requires |
|-------------|-----------|----------|
| L-INTENT | HO3 agents, humans | Approval |
| L-WORKORDER | HO2 agents, humans | Approval |
| L-EXEC | HO1 agents | Active Work Order |
| L-PACKAGE | Package manager only | Signed package |
| L-EVIDENCE | HO1 agents | Active Work Order |

### 4.2 Who MUST NOT Write

| Ledger Type | Forbidden Writers |
|-------------|-------------------|
| L-INTENT | HO2 agents, HO1 agents, BUILT apps |
| L-WORKORDER | HO1 agents, BUILT apps |
| L-PACKAGE | All except package manager |
| Any HO3 ledger | BUILT applications |

---

## 5. Active Ledger Limits

| Tier | Active Ledgers | Rationale |
|------|----------------|-----------|
| HO3 | 1 | Single governance authority |
| HO2 | Few (<=10) | One per active session/project |
| HO1 | Many (<=100) | One per active task/worker |

### 5.1 Lifecycle

| State | Description |
|-------|-------------|
| ACTIVE | Accepts new entries |
| SEALED | Read-only, preserved for audit |
| ARCHIVED | Compressed, retained per policy |

---

## 6. Entry Schema

### 6.1 Common Fields (All Ledgers)

```json
{
  "entry_id": "{TYPE}-{YYYYMMDD}-{HHMMSS}-{SEQ}",
  "timestamp": "ISO8601",
  "event_type": "{event_enum}",
  "author": "{agent_id | user_id}",
  "prev_hash": "sha256:...",
  "entry_hash": "sha256:..."
}
```

### 6.2 L-INTENT Entry

```json
{
  "entry_id": "INTENT-20260202-120000-001",
  "event_type": "FRAMEWORK_PROPOSED | FRAMEWORK_APPROVED | POLICY_CHANGE",
  "framework_id": "FMWK-XXX-001",
  "description": "...",
  "approval_chain": ["user1", "user2"],
  "...common fields..."
}
```

### 6.3 L-WORKORDER Entry

```json
{
  "entry_id": "WO-20260202-001",
  "event_type": "PROPOSED | APPROVED | REJECTED | STARTED | COMPLETED | FAILED",
  "work_order_id": "WO-20260202-001",
  "type": "code_change | spec_delta | package_install | ...",
  "scope": {
    "allowed_files": ["..."],
    "forbidden_files": ["..."]
  },
  "assigned_to": "agent_id | user_id",
  "...common fields..."
}
```

### 6.4 L-EXEC Entry

```json
{
  "entry_id": "EXEC-20260202-120000-001",
  "event_type": "TASK_START | TASK_PROGRESS | TASK_COMPLETE | TASK_FAIL",
  "work_order_id": "WO-20260202-001",
  "task_id": "TASK-001",
  "inputs": [
    {"artifact_id": "ART-001", "version": "1.0.0", "hash": "sha256:..."}
  ],
  "outputs": [
    {"artifact_id": "ART-002", "path": "...", "hash": "sha256:..."}
  ],
  "...common fields..."
}
```

### 6.5 L-PACKAGE Entry

```json
{
  "entry_id": "PKGLOG-20260202-120000-001",
  "event_type": "GENESIS | INSTALLED | UPGRADED | UNINSTALLED",
  "package_id": "PKG-XXX-001",
  "version": "1.0.0",
  "previous_version": null,
  "manifest_hash": "sha256:...",
  "signature": "base64:...",
  "signed_by": "key_id",
  "work_order_id": "WO-...",
  "asset_count": 15,
  "planes": ["ho3", "ho2"],
  "removed_assets": [],
  "...common fields..."
}
```

### 6.6 L-EVIDENCE Entry

```json
{
  "entry_id": "EVID-20260202-120000-001",
  "event_type": "EVIDENCE_ATTACHED | EVIDENCE_VALIDATED | EVIDENCE_REJECTED",
  "work_order_id": "WO-20260202-001",
  "artifact_id": "ART-EVID-001",
  "evidence_type": "test_result | review_feedback | trace_link | ...",
  "path": "evidence/...",
  "hash": "sha256:...",
  "validates": ["ART-REQ-001", "ART-DESIGN-002"],
  "...common fields..."
}
```

---

## 7. Turn Isolation Contract

### 7.1 Principle

Each agent turn operates on **declared inputs only**. No side-channel reads.

### 7.2 Required Prompt Header

```yaml
# MUST be present in every agent prompt
ledger_ids:
  - L-EXEC-20260202-001          # Ledgers agent may read
artifact_ids:
  - ART-REQ-001@1.0.0            # Artifacts agent may reference
  - ART-DESIGN-002@2.1.0
versions:
  framework: FMWK-SDLC-100@1.0.0
  spec: SPEC-TRACE-001@1.2.0
work_order_id: WO-20260202-001   # Authorizing work order
turn_number: 3                    # Sequence within session
declared_inputs:
  - file: requirements.md
    hash: sha256:abc123...
  - ledger_entry: L-EXEC-20260202-001#42
```

### 7.3 Isolation Rules

| Rule | Enforcement |
|------|-------------|
| I1 | Agent may only read artifacts listed in `artifact_ids` |
| I2 | Agent may only read ledgers listed in `ledger_ids` |
| I3 | Agent may only reference files with declared `hash` |
| I4 | Agent MUST write outputs to ledger before turn ends |
| I5 | Undeclared reads are gate violations |

---

## 8. Evidence Recording

### 8.1 Evidence Types

| Type | Description | Validates |
|------|-------------|-----------|
| `test_result` | Test execution output | Implementation |
| `review_feedback` | Human/agent review | Design, code |
| `trace_link` | Requirement to implementation link | Traceability |
| `coverage_report` | Code coverage data | Completeness |
| `approval_record` | Explicit approval | Work Order |

### 8.2 Evidence Pointers

Evidence entries point to artifacts they validate:

```json
{
  "event_type": "EVIDENCE_ATTACHED",
  "artifact_id": "ART-EVID-TEST-001",
  "validates": [
    "ART-IMPL-FUNC-001",
    "ART-REQ-FUNC-001"
  ]
}
```

### 8.3 Evidence Validation Gate

Gate G-EVIDENCE checks:
1. Evidence artifact exists at declared path
2. Hash matches declared hash
3. Evidence type is appropriate for target artifacts
4. All required evidence types present per spec

---

## 9. Chain Integrity

### 9.1 Hash Chain

```
entry[0].prev_hash = "0" * 64  (genesis)
entry[n].prev_hash = entry[n-1].entry_hash
entry[n].entry_hash = sha256(canonical_json(entry[n]) + entry[n].prev_hash)
```

### 9.2 Verification

```
FOR i = 1 TO len(ledger):
  computed = sha256(canonical_json(entry[i]) + entry[i-1].entry_hash)
  ASSERT computed == entry[i].entry_hash
```

### 9.3 Chain Break Response

| Scenario | Action |
|----------|--------|
| Hash mismatch | FAIL CLOSED |
| Missing entry | FAIL CLOSED |
| Entry modified | FAIL CLOSED |

---

## 10. Ledger Hierarchy

```
HO3 (governance.jsonl)
 |
 +-- L-INTENT: Framework evolution
 |
 +-- L-PACKAGE: Package lifecycle
      |
      +-- references work_order_id --> HO2

HO2 (workorder.jsonl)
 |
 +-- L-WORKORDER: Work authorization
 |
 +-- parent_ledger --> HO3
      |
      +-- dispatches to --> HO1

HO1 (worker.jsonl)
 |
 +-- L-EXEC: Task execution
 |
 +-- L-EVIDENCE: Quality evidence
 |
 +-- parent_ledger --> HO2
```

---

## References

- CP-ARCH-001: Control Plane Architecture Overview
- CP-PKG-001: Framework & Package Model Specification
