# CP-SDLC-QUAL-001: SDLC Quality Feedback Governance

**Document ID**: CP-SDLC-QUAL-001
**Version**: 1.0.0
**Status**: NORMATIVE (LAW)
**Plane**: HO3
**Framework**: FMWK-SDLC-100

---

## 1. Purpose

This document defines the governance rules for quality feedback in SDLC-governed specs. It specifies WHAT must exist, not HOW to implement it.

---

## 2. Scope

This LAW applies to all Spec Packs governed by FMWK-SDLC-100.

---

## 3. Invariants

### 3.1 Feedback Existence

| ID | Rule |
|----|------|
| QF-MUST-001 | Every SDLC spec MUST define required feedback types |
| QF-MUST-002 | Every deliverable artifact MUST have associated feedback |
| QF-MUST-003 | Feedback MUST be recorded as evidence in L-EVIDENCE |
| QF-MUST-004 | Feedback MUST be traceable to source artifacts |

### 3.2 Feedback Completeness

| ID | Rule |
|----|------|
| QF-MUST-005 | Feedback bundle MUST exist before phase gate passes |
| QF-MUST-006 | Feedback MUST cover all artifacts in scope |
| QF-MUST-007 | Missing feedback MUST fail the phase gate |

### 3.3 Feedback Integrity

| ID | Rule |
|----|------|
| QF-MUST-008 | Feedback MUST NOT be modified after recording |
| QF-MUST-009 | Feedback MUST be signed by its author |
| QF-MUST-010 | Feedback MUST reference specific artifact versions |

### 3.4 Prohibitions

| ID | Rule |
|----|------|
| QF-MUSTNOT-001 | Feedback MUST NOT be self-authored (author != artifact author) |
| QF-MUSTNOT-002 | Feedback MUST NOT reference non-existent artifacts |
| QF-MUSTNOT-003 | Feedback MUST NOT omit required metadata fields |

---

## 4. Required Evidence Artifacts

### 4.1 Evidence Types by Phase

| SDLC Phase | Required Evidence Types |
|------------|-------------------------|
| Requirements | `requirements_review`, `stakeholder_approval` |
| Design | `design_review`, `architecture_approval` |
| Implementation | `code_review`, `static_analysis` |
| Testing | `test_results`, `coverage_report` |
| Deployment | `deployment_approval`, `security_scan` |

### 4.2 Evidence Ownership

| Rule | Statement |
|------|-----------|
| EO-001 | Each evidence type MUST be owned by a Spec Pack |
| EO-002 | Evidence artifacts MUST be declared in spec manifest |
| EO-003 | Evidence MUST be stored in governed paths |

### 4.3 Evidence Path Pattern

```
evidence/{spec_id}/{phase}/{evidence_type}/{artifact_id}.json
```

---

## 5. Required Metadata

### 5.1 Attribution

Every feedback artifact MUST include:

| Field | Type | Description |
|-------|------|-------------|
| `author_id` | string | Identity of feedback author |
| `author_role` | enum | `human_reviewer`, `agent_reviewer`, `automated_tool` |
| `authored_at` | ISO8601 | Timestamp of authorship |
| `author_signature` | string | Cryptographic signature |

### 5.2 Classification

Every feedback artifact MUST include:

| Field | Type | Description |
|-------|------|-------------|
| `feedback_type` | enum | Type from allowed list |
| `severity` | enum | `blocker`, `major`, `minor`, `suggestion` |
| `category` | enum | `correctness`, `completeness`, `clarity`, `compliance` |
| `phase` | enum | SDLC phase this feedback applies to |

### 5.3 Actionability

Every feedback artifact MUST include:

| Field | Type | Description |
|-------|------|-------------|
| `actionable` | boolean | Whether action is required |
| `action_required` | string | Description of required action (if actionable) |
| `resolution_deadline` | ISO8601 | When action must be resolved (if actionable) |
| `resolved` | boolean | Whether action has been resolved |
| `resolved_by` | string | Identity of resolver (if resolved) |
| `resolved_at` | ISO8601 | When resolved (if resolved) |

### 5.4 Traceability

Every feedback artifact MUST include:

| Field | Type | Description |
|-------|------|-------------|
| `target_artifacts` | array | Artifacts this feedback applies to |
| `target_versions` | array | Specific versions referenced |
| `target_locations` | array | Specific locations within artifacts |
| `trace_links` | array | Links to requirements/design/tests |
| `work_order_id` | string | Authorizing Work Order |

---

## 6. Feedback Schema

### 6.1 Minimal Structure

```yaml
# feedback-artifact.schema.yaml (normative structure, not implementation)

required_fields:
  - feedback_id
  - feedback_type
  - attribution
  - classification
  - actionability
  - traceability
  - content
  - integrity

attribution:
  required:
    - author_id
    - author_role
    - authored_at
    - author_signature

classification:
  required:
    - feedback_type
    - severity
    - category
    - phase

actionability:
  required:
    - actionable
  conditional:
    - action_required      # if actionable=true
    - resolution_deadline  # if actionable=true

traceability:
  required:
    - target_artifacts
    - target_versions
    - work_order_id

content:
  required:
    - summary
  optional:
    - details
    - recommendations
    - attachments

integrity:
  required:
    - content_hash
    - signature
```

### 6.2 Feedback Type Enum

| Value | Description | Phase |
|-------|-------------|-------|
| `requirements_review` | Review of requirements | Requirements |
| `stakeholder_approval` | Stakeholder sign-off | Requirements |
| `design_review` | Review of design | Design |
| `architecture_approval` | Architecture sign-off | Design |
| `code_review` | Review of code | Implementation |
| `static_analysis` | Automated code analysis | Implementation |
| `test_results` | Test execution results | Testing |
| `coverage_report` | Code coverage metrics | Testing |
| `security_scan` | Security analysis results | Testing |
| `deployment_approval` | Deployment sign-off | Deployment |

---

## 7. Structural Rubric

### 7.1 Purpose

The structural rubric defines the SHAPE of feedback, not its quality scores.

### 7.2 Rubric Fields

| Field | Type | Description |
|-------|------|-------------|
| `completeness_addressed` | boolean | All required areas covered |
| `correctness_addressed` | boolean | Accuracy verified |
| `clarity_addressed` | boolean | Understandability assessed |
| `compliance_addressed` | boolean | Standards conformance checked |
| `areas_reviewed` | array | Specific areas examined |
| `areas_not_reviewed` | array | Explicit gaps (if any) |
| `blockers_found` | integer | Count of blocking issues |
| `majors_found` | integer | Count of major issues |
| `minors_found` | integer | Count of minor issues |
| `suggestions_found` | integer | Count of suggestions |

### 7.3 Rubric Constraints

| Constraint | Rule |
|------------|------|
| RC-001 | At least one `*_addressed` field MUST be true |
| RC-002 | `areas_reviewed` MUST be non-empty |
| RC-003 | Sum of `*_found` counts MUST match content items |

---

## 8. Required Gates

### 8.1 G-FEEDBACK-COMPLETE

**Purpose**: Verify feedback bundle exists and conforms to schema.

**Checks**:

| Check | Failure |
|-------|---------|
| Feedback artifact exists | "Missing feedback for {artifact}" |
| Schema valid | "Feedback schema invalid: {errors}" |
| All required fields present | "Missing field: {field}" |
| Attribution complete | "Missing attribution: {field}" |
| Author signature valid | "Invalid author signature" |

**Trigger**: Phase gate transition.

### 8.2 G-FEEDBACK-TRACE

**Purpose**: Verify feedback maps to requirements, design, and tests.

**Checks**:

| Check | Failure |
|-------|---------|
| Target artifacts exist | "Unknown target: {artifact}" |
| Target versions exist | "Unknown version: {version}" |
| Trace links valid | "Broken trace: {link}" |
| All requirements traced | "Untraced requirement: {req}" |
| All designs traced | "Untraced design: {design}" |
| All tests traced | "Untraced test: {test}" |

**Trigger**: Phase gate transition.

---

## 9. Gate Sequence

```
Phase N Complete
      |
      v
+-------------------------------------+
|      G-FEEDBACK-COMPLETE            |
|                                     |
|  * Feedback exists?                 |
|  * Schema valid?                    |
|  * Attribution complete?            |
|  * Signature valid?                 |
|                                     |
|  FAIL -> Block phase transition     |
+-------------------------------------+
      |
      | PASS
      v
+-------------------------------------+
|       G-FEEDBACK-TRACE              |
|                                     |
|  * Targets exist?                   |
|  * Versions match?                  |
|  * Requirements traced?             |
|  * Designs traced?                  |
|  * Tests traced?                    |
|                                     |
|  FAIL -> Block phase transition     |
+-------------------------------------+
      |
      | PASS
      v
Phase N+1 Start
```

---

## 10. Evidence Recording

### 10.1 Ledger Entry

All feedback MUST be recorded in L-EVIDENCE:

```json
{
  "entry_id": "EVID-20260202-120000-001",
  "event_type": "EVIDENCE_ATTACHED",
  "work_order_id": "WO-20260202-001",
  "artifact_id": "ART-FEEDBACK-001",
  "evidence_type": "code_review",
  "phase": "implementation",
  "path": "evidence/SPEC-XXX-001/implementation/code_review/ART-FEEDBACK-001.json",
  "hash": "sha256:...",
  "validates": [
    "ART-IMPL-FUNC-001@1.0.0",
    "ART-REQ-FUNC-001@1.0.0"
  ],
  "author_id": "reviewer@org",
  "timestamp": "2026-02-02T12:00:00Z"
}
```

### 10.2 Validation Entry

Feedback validation MUST be recorded:

```json
{
  "entry_id": "EVID-20260202-120001-001",
  "event_type": "EVIDENCE_VALIDATED",
  "artifact_id": "ART-FEEDBACK-001",
  "validated_by": "G-FEEDBACK-COMPLETE",
  "validation_result": "PASS",
  "timestamp": "2026-02-02T12:00:01Z"
}
```

---

## 11. Path Authorizations

Specs governed by this framework MAY own files matching:

```
evidence/{spec_id}/**
artifacts/{spec_id}/**
```

---

## 12. Change Control

Allowed Work Order types for SDLC-governed specs:

| Type | Description |
|------|-------------|
| `feedback_submit` | Submit new feedback |
| `feedback_resolve` | Resolve actionable feedback |
| `phase_transition` | Request phase gate passage |
| `evidence_attach` | Attach new evidence |

---

## 13. Security Posture

| Rule | Statement |
|------|-----------|
| SP-001 | Fail-closed on missing feedback |
| SP-002 | Fail-closed on schema violation |
| SP-003 | Fail-closed on broken trace |
| SP-004 | Fail-closed on invalid signature |
| SP-005 | No phase transition without complete evidence |

---

## References

- CP-ARCH-001: Control Plane Architecture Overview
- CP-PKG-001: Framework & Package Model Specification
- CP-LEDGER-001: Tiered Ledger Model
- FMWK-SDLC-100: SDLC Framework LAW Document
