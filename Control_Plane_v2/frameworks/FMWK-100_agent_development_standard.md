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

## 7. Reusable Module Standard

### 7.1 Definition

A reusable module is a package that:
- Provides functionality usable by multiple agents/specs
- Exposes both Python API and CLI interface
- Follows pipe-first contract
- Has no hidden IO

### 7.2 Invariants (I-MOD-*)

- **I-MOD-1**: Every module is a package (manifest-declared files).
- **I-MOD-2**: CLI reads JSON stdin, writes JSON stdout.
- **I-MOD-3**: No filesystem crawling in PRISTINE.
- **I-MOD-4**: All inputs via stdin JSON, all outputs via stdout JSON.
- **I-MOD-5**: Evidence metadata emitted in response envelope.
- **I-MOD-6**: Errors returned in envelope, not thrown.
- **I-MOD-7**: Secrets only from env, never logged.

### 7.3 Required Artifacts

For each module package:
- `<module>/__main__.py` - CLI entrypoint
- `schemas/<module>_request.json` - Input schema
- `schemas/<module>_response.json` - Output schema
- `tests/test_<module>_pipe.py` - Pipe-first test
- `tests/test_<module>_purity.py` - No hidden IO test

### 7.4 Pipe-First Contract

Every reusable module MUST expose:
- **Python API**: importable functions/classes
- **CLI**: reads JSON from stdin, writes JSON to stdout
- **Schema**: JSON Schema for request/response in schemas/<module>_request.json

CLI invocation pattern:
```bash
echo '{"input": ...}' | python3 -m modules.<name> | jq .
```

Response envelope (all CLIs):
```json
{
  "status": "ok" | "error",
  "result": "<output>",
  "evidence": {
    "input_hash": "sha256:...",
    "output_hash": "sha256:...",
    "timestamp": "ISO8601"
  },
  "error": null | {"code": "...", "message": "..."}
}
```

### 7.5 No Hidden IO (No Drift)

**FORBIDDEN (always)**:
- Crawling PRISTINE directories
- Reading ledgers without explicit range/reference
- Implicit caches that persist across invocations
- Hidden persistent state (files, globals, singletons with state)
- Importing modules not declared in package dependencies
- ANY undeclared DERIVED write → CapabilityViolation

**ALLOWED (with constraints)**:
- Reading explicitly declared inputs (paths in request JSON)
- Reading declared PRISTINE paths (schemas, config) listed in manifest
- Writing to DERIVED ONLY when declared in request
- Ephemeral in-memory caches (cleared per invocation)
- Environment variables for secrets (never logged)

### 7.6 Capability-Gated Behavior

Network capability gating:
- Any outbound call (LLM, HTTP) requires CAPABILITY_NETWORK
- Runner injects capability token via env: CAPABILITY_NETWORK=<token>
- Module checks for token presence before network call
- Missing token → CapabilityViolation, no network call made

Secret handling protocol:
- Secrets read from env vars (never from PRISTINE files)
- Env var naming: <SERVICE>_API_KEY, <SERVICE>_SECRET
- Secrets NEVER appear in stdout JSON, L-EXEC entries, or any PRISTINE file

### 7.7 Evidence Emission Schema

Every module emits evidence in response envelope:
```json
{
  "evidence": {
    "session_id": "SES-...",
    "turn_number": 3,
    "work_order_id": "WO-...",
    "input_hash": "sha256:...",
    "output_hash": "sha256:...",
    "timestamp": "ISO8601",
    "duration_ms": 123,
    "declared_reads": [
      {"path": "schemas/foo.json", "hash": "sha256:..."}
    ],
    "declared_writes": [
      {"path": "tmp/SES-.../out.json", "hash": "sha256:...", "size": 1234}
    ],
    "external_calls": [
      {
        "request_id": "REQ-...",
        "provider": "anthropic",
        "model": "claude-opus-4-5-20251101",
        "cached": false
      }
    ]
  }
}
```

---

## 8. Agent Runtime Requirements

### 8.1 Invariants (I-AGENT-*)

- **I-AGENT-1**: Agents are stateless. All context is reconstructed from ledgers per turn.
- **I-AGENT-2**: Agents write to L-EXEC (per-session ledger) documenting every action.
- **I-AGENT-3**: Agents operate in exactly one tier (HO1, HO2, or HO3).
- **I-AGENT-4**: Capabilities are declared in package manifest and enforced at runtime.
- **I-AGENT-5**: Agents cannot invoke forbidden operations (defined in manifest.forbidden).

### 8.2 Runtime Contract

Every agent turn receives:
- `session_id`: Unique session identifier
- `turn_number`: Integer turn within session
- `work_order_id`: Optional authorization reference
- `declared_inputs`: Files/artifacts the agent may read (with hashes)
- `declared_outputs`: Files the agent may write (with path patterns)
- `context_as_of`: Timestamp of context assembly

Every agent turn produces:
- `L-EXEC entry`: Hash of query + result, logged to session ledger
- `L-EVIDENCE entry`: Evidence with (session_id, turn_number, work_order_id)
- `result`: The agent's response

Session ledger location:
- `planes/<tier>/sessions/<session_id>/ledger/exec.jsonl`
- `planes/<tier>/sessions/<session_id>/ledger/evidence.jsonl`

### 8.3 Capability Enforcement

Capabilities declared in package manifest:
- `capabilities.read`: Glob patterns for readable paths
- `capabilities.execute`: Script invocations allowed
- `capabilities.write`: Glob patterns for writable paths (typically L-EXEC only)
- `capabilities.forbidden`: Explicitly denied operations

Violation of any capability → `CapabilityViolation` exception, turn aborted.

### 8.4 Write Surface Invariant

**GLOBAL INVARIANT**: `declared_outputs` is the ONLY write surface.

This applies to:
- Modules (pipe CLIs)
- Agent runtime itself
- Trace wrapper outputs
- Any subprocess temp files

**Session-Scoped Writable Sandbox**:
```
ALLOWED DERIVED roots (writable):
  tmp/<session_id>/**
  output/<session_id>/**

EVERYTHING ELSE: read-only
```

**Fail-Closed Enforcement**:
- Runtime MUST require `request.declared_outputs[]` for every turn
- Runtime MUST verify `capabilities.write` patterns match declared_outputs
- Runtime MUST block/abort turn if ANY write occurs outside declared_outputs
- ANY undeclared DERIVED write → CapabilityViolation

### 8.5 Replay Safety Invariant

A valid agent turn MUST be reproducible solely from:
- HO1 ledgers (execution tape)
- Declared PRISTINE reads (with hashes)
- Declared DERIVED outputs (with hashes)

If behavior cannot be replayed from these artifacts, it is INVALID.

---

## 9. Review Checklist

Before setting MODE=COMMIT, verify:

### 9.1 Spec Pack
- [ ] No {{placeholder}} markers remain
- [ ] No TBD/TODO in required sections
- [ ] All file references are valid
- [ ] Success criteria are measurable

### 9.2 Code
- [ ] Runs without errors
- [ ] No debug print statements
- [ ] No commented-out code blocks
- [ ] Imports are organized (stdlib, third-party, local)

### 9.3 Tests
- [ ] All tests pass
- [ ] No skipped tests without reason
- [ ] Test names describe what they test

### 9.4 Security
- [ ] No hardcoded credentials
- [ ] No sensitive data in logs
- [ ] File paths are validated
- [ ] User input is sanitized

---

## 10. Audit and Ledger Requirements

All governance operations MUST be logged to the ledger for accountability.

### 10.1 Required Ledger Events

| Operation | Event Type | Required Fields |
|-----------|------------|-----------------|
| Create artifact | `governance_create` | artifact_id, entity_type, artifact_path, framework_id, source_spec_id |
| Update artifact | `governance_update` | artifact_id, old_hash, new_hash |
| Delete artifact | `governance_delete` | artifact_id, artifact_path, reason |
| Validation pass | `validation_pass` | chain_id, layer, checks_passed |
| Validation fail | `validation_fail` | chain_id, layer, checks_failed, issues |

### 10.2 Ledger Entry Structure

Every ledger entry MUST include:
- `event_type`: Classification of the operation
- `submission_id`: Unique identifier for the operation
- `decision`: Result (CREATE, UPDATE, DELETE, PASS, FAIL)
- `reason`: Human-readable explanation
- `timestamp`: ISO 8601 UTC timestamp
- `metadata`: Operation-specific details

### 10.3 No Silent Operations

- Governance operations that modify state MUST log before returning
- Failed operations MUST also be logged with error details
- Log writes are synchronous (operation waits for log confirmation)

---

## 11. Gate Validation Mapping

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

## 12. Compliance Declaration

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

## 13. Exceptions

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
version: 2.0.0
status: draft
created: 2026-01-27
updated: 2026-02-03
category: Governance
dependencies: []
provides: [definition_of_done, code_standards, test_standards, doc_standards, audit_standards]
ci_gate: required
```
