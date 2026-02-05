# FMWK-100: Agent Development Standard

**Version:** 1.0.0
**Status:** DRAFT
**Purpose:** Minimum viable framework for agent-assisted module development

---

## 1. Overview

This framework defines the minimum standards that ALL modules developed through the Control Plane must meet. It consolidates:
- Definition of Done (quality bar)
- Code structure requirements
- Testing requirements
- Documentation requirements
- Review checklist

Agents MUST comply with this framework. Modules that don't meet these standards cannot pass gates.

---

## 2. Definition of Done

A module is DONE when ALL of the following are true:

### 2.1 Spec Pack Complete
- [ ] All 8 files (00-07) have substantive content (no placeholders)
- [ ] 08_commit.md exists with MODE=COMMIT
- [ ] WORK_ITEM.md exists in work_items/ (if L3)

### 2.2 Code Complete
- [ ] All files listed in 04_design.md "Files Changed" exist
- [ ] No TODO/FIXME comments in production code
- [ ] No hardcoded secrets, paths, or credentials
- [ ] Code follows naming conventions (snake_case for Python)

### 2.3 Tests Complete
- [ ] At least ONE test file exists per module
- [ ] Test command in 05_testing.md passes (exit code 0)
- [ ] Tests cover the primary happy path
- [ ] Tests cover at least one error case

### 2.4 Documentation Complete
- [ ] README.md exists at module root
- [ ] README has: Purpose, Usage, Dependencies, Examples
- [ ] All public functions have docstrings
- [ ] 07_registry.md lists all artifacts

### 2.5 Review Complete
- [ ] Human has reviewed and approved (08_commit.md MODE=COMMIT)
- [ ] All gates pass (G0, G1, G2, G3)

---

## 3. Spec Pack Content Requirements

Each spec pack file MUST contain substantive content. Minimum requirements:

### 00_overview.md
REQUIRED SECTIONS:
- Summary: 2+ sentences describing what this module does
- Scope (In/Out): At least 2 items each
- Success Criteria: At least 2 measurable criteria
- Frameworks: List FMWK-100 (this framework) + any others

### 01_problem.md
REQUIRED SECTIONS:
- Problem Description: 2+ paragraphs explaining the problem
- Impact: Who is affected and severity
- Non-Goals: At least 1 explicit non-goal

### 02_solution.md
REQUIRED SECTIONS:
- Proposed Solution: Clear description of approach
- Alternatives Considered: At least 1 alternative (even if "do nothing")
- Risks: At least 1 identified risk

### 03_requirements.md
REQUIRED SECTIONS:
- At least ONE functional requirement (FR-XXX)
- Each requirement has acceptance criteria
- Priority assigned (P0/P1/P2)

### 04_design.md
REQUIRED SECTIONS:
- Architecture: Description or diagram of components
- Files Changed: Table with File | Action | Description
- Dependencies: List internal and external deps

### 05_testing.md
REQUIRED SECTIONS:
- Test command: Single line starting with "$ " (G3 runs this)
- At least ONE test case documented
- Verification Checklist: At least 3 items

### 06_rollout.md
REQUIRED SECTIONS:
- Rollout approach (can be "Direct commit" for small changes)
- Rollback plan (can be "git revert" for simple cases)

### 07_registry.md
REQUIRED SECTIONS:
- Registry entry with: id, name, entity_type, artifact_path, status
- Dependencies listed (or "none")
- Version number

---

## 4. Code Structure Standards

### 4.1 File Organization
```
module_name/
  __init__.py       # Required: exports public API
  main.py           # Required: entry point (if executable)
  core.py           # Core logic
  models.py         # Data models (if any)
  utils.py          # Utilities (if any)
  tests/
    __init__.py
    test_core.py    # Required: at least one test file
  README.md         # Required: module documentation
```

### 4.2 Naming Conventions
- Files: snake_case.py
- Classes: PascalCase
- Functions: snake_case
- Constants: UPPER_SNAKE_CASE
- Private: _leading_underscore

### 4.3 Code Quality
- Max line length: 100 characters
- Max function length: 50 lines (prefer smaller)
- Max file length: 500 lines (split if larger)
- No circular imports
- No wildcard imports (from x import *)

---

## 5. Testing Standards

### 5.1 Minimum Test Coverage
- Every module MUST have at least one test file
- Tests MUST be runnable via single command
- Test command MUST return exit code 0 on success

### 5.2 Test Structure
```python
def test_<function>_<scenario>_<expected>():
    """Test that <function> returns <expected> when <scenario>."""
    # Arrange
    input = ...

    # Act
    result = function(input)

    # Assert
    assert result == expected
```

### 5.3 Required Test Cases
- Happy path: Normal operation works
- Error case: Graceful handling of invalid input
- Edge case: Boundary conditions (empty, null, max)

---

## 6. Documentation Standards

### 6.1 README.md Template
```markdown
# Module Name

Brief description (1-2 sentences).

## Purpose

What problem does this solve?

## Usage

```python
from module import function
result = function(input)
```

## Dependencies

- dependency_1: why needed
- dependency_2: why needed

## Examples

Show 2-3 examples of common usage.
```

### 6.2 Docstring Template
```python
def function(param1: str, param2: int) -> bool:
    """Brief description of what the function does.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: When param1 is empty
    """
```

---

## 7. Review Checklist

Before setting MODE=COMMIT, verify:

### 7.1 Spec Pack
- [ ] No {{placeholder}} markers remain
- [ ] No TBD/TODO in required sections
- [ ] All file references are valid
- [ ] Success criteria are measurable

### 7.2 Code
- [ ] Runs without errors
- [ ] No debug print statements
- [ ] No commented-out code blocks
- [ ] Imports are organized (stdlib, third-party, local)

### 7.3 Tests
- [ ] All tests pass
- [ ] No skipped tests without reason
- [ ] Test names describe what they test

### 7.4 Security
- [ ] No hardcoded credentials
- [ ] No sensitive data in logs
- [ ] File paths are validated
- [ ] User input is sanitized

---

## 8. Audit and Ledger Requirements

All governance operations MUST be logged to the ledger for accountability.

### 8.1 Required Ledger Events

| Operation | Event Type | Required Fields |
|-----------|------------|-----------------|
| Create artifact | `governance_create` | artifact_id, entity_type, artifact_path, framework_id, source_spec_id |
| Update artifact | `governance_update` | artifact_id, old_hash, new_hash |
| Delete artifact | `governance_delete` | artifact_id, artifact_path, reason |
| Validation pass | `validation_pass` | chain_id, layer, checks_passed |
| Validation fail | `validation_fail` | chain_id, layer, checks_failed, issues |

### 8.2 Ledger Entry Structure

Every ledger entry MUST include:
- `event_type`: Classification of the operation
- `submission_id`: Unique identifier for the operation
- `decision`: Result (CREATE, UPDATE, DELETE, PASS, FAIL)
- `reason`: Human-readable explanation
- `timestamp`: ISO 8601 UTC timestamp
- `metadata`: Operation-specific details

### 8.3 No Silent Operations

- Governance operations that modify state MUST log before returning
- Failed operations MUST also be logged with error details
- Log writes are synchronous (operation waits for log confirmation)

---

## 9. Gate Validation Mapping

This framework maps to Control Plane gates:

| Requirement | Gate | Validation |
|-------------|------|------------|
| Spec pack files exist | G1 | Structure check |
| No placeholders | G1 | Content check |
| JSON/YAML valid | G2 | Syntax check |
| Test command passes | G3 | Execution check |
| MODE=COMMIT | G0 | Authorization check |
| Content depth | G1.5 | NEW - Framework compliance |
| Ledger logging | G4 | Audit trail verification |

---

## 10. Compliance Declaration

Modules declare framework compliance in 00_overview.md:

```markdown
## Frameworks

This module complies with:
- FMWK-100: Agent Development Standard (this document)
```

Gates will validate compliance by checking:
1. Framework declaration exists
2. All required sections have substantive content
3. Test command passes
4. Definition of Done checklist is satisfiable

---

## 11. Exceptions

If a module cannot comply with a requirement:
1. Document the exception in 01_problem.md under "Constraints"
2. Explain WHY compliance is not possible
3. Describe ALTERNATIVE measure taken
4. Human reviewer must explicitly approve exception

---

## Metadata

```yaml
framework_id: FMWK-100
name: Agent Development Standard
version: 1.1.0
status: draft
created: 2026-01-27
updated: 2026-01-29
category: Governance
dependencies: []
provides: [definition_of_done, code_standards, test_standards, doc_standards, audit_standards]
ci_gate: required
```
