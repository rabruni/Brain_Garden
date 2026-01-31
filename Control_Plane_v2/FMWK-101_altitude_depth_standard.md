# FMWK-101: Altitude-to-Depth Standard

**Version:** 1.0.0
**Status:** DRAFT
**Purpose:** Define required documentation depth at each altitude level

---

## 1. The Problem

Current state:
- We have altitude levels (L4/L3/L2/L1) for conversation governance
- We have spec packs (00-07 files) for documentation
- But NO mapping that says "at L4, you need THIS level of detail"

This causes:
- Agents writing too little detail (drift risk)
- Agents writing too much detail (over-engineering)
- No way to validate if content depth matches declared altitude

---

## 2. Altitude-to-Documentation Mapping

### Overview

| Altitude | Focus | C4 Equivalent | Primary Artifact | Detail Level |
|----------|-------|---------------|------------------|--------------|
| L4 | Identity/Vision | System Context | SPEC.md | WHY + WHAT (not HOW) |
| L3 | Strategy/Design | Container | WORK_ITEM.md | WHAT + HOW (not code) |
| L2 | Operations/Build | Component | Implementation | HOW (code-level) |
| L1 | Moment/Execute | Code | Running system | NOW (execution) |

### Spec Pack Mapping

| Spec Pack File | L4 Depth | L3 Depth | L2 Depth |
|----------------|----------|----------|----------|
| 00_overview | FULL | Summary only | Reference only |
| 01_problem | FULL | Summary only | Reference only |
| 02_solution | High-level | FULL | Reference only |
| 03_requirements | Capabilities | FULL | Acceptance only |
| 04_design | Architecture | Components | FULL (code-level) |
| 05_testing | Strategy | Test plan | FULL (test code) |
| 06_rollout | Phases | Steps | FULL (commands) |
| 07_registry | Entry | Entry | Entry |

---

## 3. L4 (Identity/Vision) Documentation Requirements

**Focus:** WHY this exists, WHAT problem it solves, WHO it serves

### 00_overview.md (FULL)
Required content:
- Vision statement (2-3 sentences describing the future state)
- Problem context (why this matters)
- Success definition (what "winning" looks like)
- Stakeholders (who benefits, who is affected)
- Constraints (boundaries, non-negotiables)

NOT required at L4:
- Implementation details
- API specifications
- Code structure

### 01_problem.md (FULL)
Required content:
- Problem narrative (story-form, not technical)
- Impact assessment (who is hurt, how much)
- Root cause analysis (why the problem exists)
- Non-goals (explicit boundaries)
- Evidence (data, quotes, observations)

### 02_solution.md (High-level)
Required content:
- Solution approach (2-3 paragraphs, conceptual)
- Key decisions (what choices were made, why)
- Alternatives considered (at least 2)
- Risks (strategic risks, not implementation)

NOT required at L4:
- Component diagrams
- API contracts
- Data models

### 03_requirements.md (Capabilities)
Required content:
- Capability statements ("The system shall...")
- User outcomes (what users can do)
- Quality attributes (performance, security - targets, not specs)

NOT required at L4:
- Detailed acceptance criteria
- Test cases
- Technical requirements

### 04_design.md (Architecture)
Required content:
- System context diagram (boxes and arrows, who talks to whom)
- Key components (names and responsibilities, 1 sentence each)
- Integration points (what external systems)
- Technology decisions (if fixed)

NOT required at L4:
- Internal component structure
- API specifications
- Data schemas
- File lists

### 05_testing.md (Strategy)
Required content:
- Testing philosophy (how we'll know it works)
- Verification approach (manual, automated, both)
- Key scenarios to verify (3-5 critical paths)

NOT required at L4:
- Test cases
- Test code
- Specific commands

### 06_rollout.md (Phases)
Required content:
- Rollout phases (names and goals)
- Success criteria per phase
- Rollback strategy (conceptual)

NOT required at L4:
- Deployment commands
- Environment details
- Runbook steps

---

## 4. L3 (Strategy/Design) Documentation Requirements

**Focus:** WHAT we're building, HOW it's structured, not code

### 00_overview.md (Summary)
- 1 paragraph summary
- Reference to L4 spec if exists

### 01_problem.md (Summary)
- 1 paragraph problem statement
- Reference to L4 spec if exists

### 02_solution.md (FULL)
Required content:
- Solution design (detailed approach)
- Component breakdown (what pieces, what each does)
- Interaction patterns (how pieces communicate)
- Trade-offs (what we're gaining, what we're sacrificing)

### 03_requirements.md (FULL)
Required content:
- Functional requirements (FR-001 format)
- Non-functional requirements (specific targets)
- Acceptance criteria (for each requirement)
- User stories (if applicable)

### 04_design.md (Components)
Required content:
- Component diagram (internal structure)
- Interface contracts (inputs, outputs, errors)
- Data model (entities, relationships)
- File structure (what files, what each does)
- Dependencies (internal and external)

NOT required at L3:
- Implementation code
- Line-by-line logic
- Detailed algorithms

### 05_testing.md (Test Plan)
Required content:
- Test cases (ID, description, expected result)
- Test categories (unit, integration, E2E)
- Coverage targets
- Test command (single $ line)

### 06_rollout.md (Steps)
Required content:
- Step-by-step deployment
- Prerequisites
- Verification checks
- Rollback steps

---

## 5. L2 (Operations/Build) Documentation Requirements

**Focus:** HOW to implement, code-level detail

### 00_overview.md (Reference)
- Link to L3/L4 spec
- Current build status

### 01_problem.md (Reference)
- Link to L3/L4 spec

### 02_solution.md (Reference)
- Link to L3 design

### 03_requirements.md (Acceptance)
- Acceptance commands only
- Link to full requirements in L3

### 04_design.md (FULL - Code Level)
Required content:
- All L3 content PLUS:
- Pseudocode or algorithm descriptions
- Error handling approach
- Edge cases
- Exact file paths and function names

### 05_testing.md (FULL - Test Code)
Required content:
- All L3 content PLUS:
- Actual test code or test file references
- Mock/fixture setup
- CI integration

### 06_rollout.md (FULL - Commands)
Required content:
- All L3 content PLUS:
- Exact commands to run
- Environment variables
- Secrets handling

---

## 6. Validation Rules

### For L4 Specs
```
MUST have:
  - 00_overview: Vision statement (2+ sentences)
  - 00_overview: Success definition
  - 01_problem: Problem narrative (2+ paragraphs)
  - 01_problem: Non-goals (1+)
  - 02_solution: Solution approach
  - 02_solution: Alternatives (2+)
  - 04_design: System context (diagram or description)

MUST NOT have:
  - 04_design: File paths
  - 04_design: API specifications
  - 05_testing: Test code
```

### For L3 Specs
```
MUST have:
  - 02_solution: Component breakdown
  - 03_requirements: At least 1 FR-XXX
  - 03_requirements: Acceptance criteria
  - 04_design: Component diagram
  - 04_design: Interface contracts
  - 04_design: File structure
  - 05_testing: Test cases (3+)
  - 05_testing: Test command ($ line)

MUST NOT have:
  - 04_design: Implementation code
  - 05_testing: Detailed test code
```

### For L2 Specs
```
MUST have:
  - Reference to L3 spec
  - 04_design: Exact file paths
  - 04_design: Function signatures
  - 05_testing: Test files exist
  - 06_rollout: Exact commands
```

---

## 7. Gate Integration

### G1.5: Altitude Depth Gate (NEW)

This gate validates content depth matches declared altitude.

```python
def validate_altitude_depth(spec_pack, declared_altitude):
    """
    Validate spec pack content matches declared altitude.

    Returns:
        PASS: Content depth matches altitude
        FAIL: Content too shallow OR too detailed for altitude
    """
    if declared_altitude == "L4":
        # Must have vision, must NOT have implementation
        check_has(spec_pack, "00_overview", "vision_statement")
        check_has(spec_pack, "01_problem", "problem_narrative")
        check_not_has(spec_pack, "04_design", "file_paths")
        check_not_has(spec_pack, "05_testing", "test_code")

    elif declared_altitude == "L3":
        # Must have design, must NOT have code
        check_has(spec_pack, "03_requirements", "FR-XXX")
        check_has(spec_pack, "04_design", "component_diagram")
        check_has(spec_pack, "05_testing", "test_command")
        check_not_has(spec_pack, "04_design", "implementation_code")

    elif declared_altitude == "L2":
        # Must have code-level detail
        check_has(spec_pack, "04_design", "file_paths")
        check_has(spec_pack, "05_testing", "test_files")
        check_has(spec_pack, "06_rollout", "exact_commands")
```

---

## 8. Example: Control Plane at Each Altitude

### L4 Spec (Vision): "What is Control Plane?"

```markdown
# 00_overview.md

## Vision
Control Plane is a governance system that ensures AI agents
build high-quality, consistent software by enforcing standards
at every stage from idea to deployment.

## Success Definition
- Agents produce code that meets quality standards without human intervention
- Every module is documented, tested, and auditable
- Drift is detected and corrected automatically

## Stakeholders
- Developers using AI agents to build software
- Teams maintaining AI-built codebases
- Organizations requiring auditability
```

### L3 Spec (Design): "How is Control Plane structured?"

```markdown
# 04_design.md

## Components
- Shaper: Converts intent to contracts (WORK_ITEM.md, SPEC.md)
- Flow Runner: Manages phase progression (Phase0A → Phase4)
- Gate Runner: Validates at each phase (G0, G1, G2, G3)
- Registry: Tracks what exists (CSV files)

## Interfaces
- cp.py: CLI entry point
- flow_runner.py: Phase management
- gate_runner.py: Validation execution

## File Structure
- /Control_Plane/
  - cp.py (CLI)
  - /flow_runner/ (phase management)
  - /modules/design_framework/shaper/ (shaping)
  - /registries/ (CSV registries)
  - /docs/specs/ (spec packs)
```

### L2 Spec (Build): "How to implement Gate G1.5?"

```markdown
# 04_design.md

## File: flow_runner/gate_runner.py

### Function: _run_g1_5(spec_id, declared_altitude)

```python
def _run_g1_5(self, spec_id: str) -> GateResult:
    """Validate content depth matches declared altitude."""
    spec_root = self.repo_root / "Control_Plane" / "docs" / "specs" / spec_id
    commit_md = spec_root / "08_commit.md"
    altitude = self._extract_altitude(commit_md)

    if altitude == "L4":
        # Check for vision content
        overview = (spec_root / "00_overview.md").read_text()
        if "vision" not in overview.lower():
            return GateResult(
                gate_id="G1.5",
                status="failed",
                category="SPEC_DEFECT",
                reason="L4 spec missing vision statement in 00_overview.md"
            )
    # ... etc
```
```

---

## 9. Usage

### Declaring Altitude

In 08_commit.md:
```markdown
## ALTITUDE
L3

## ALTITUDE_JUSTIFICATION
This is a design-level spec defining component structure.
Implementation details are deferred to L2 work items.
```

### Compliance Declaration

In 00_overview.md:
```markdown
## Frameworks
- FMWK-100: Agent Development Standard
- FMWK-101: Altitude Depth Standard (this document)

## Altitude
L3 (Strategy/Design)
```

---

## 10. Relationship to Existing Altitude Governance

This framework COMPLEMENTS (not replaces) the existing altitude system:

| System | Controls | Location |
|--------|----------|----------|
| altitude.py | Conversation transitions | dopejar/hrm/altitude.py |
| FMWK-101 | Documentation depth | This framework |
| Shaper | Artifact routing (L3→WORK_ITEM, L4→SPEC) | shaper/ |

The flow:
1. Conversation altitude (altitude.py) determines WHAT we're discussing
2. Shaper routes to artifact type based on altitude
3. FMWK-101 validates DEPTH of documentation matches altitude
4. Gates enforce compliance

---

## Metadata

```yaml
framework_id: FMWK-101
name: Altitude Depth Standard
version: 1.0.0
status: draft
created: 2026-01-27
category: Governance
dependencies: [FMWK-100]
provides: [altitude_depth_validation, content_depth_standard]
ci_gate: required
```
