# Requirements

## Functional Requirements

### FR-ADMIN-001: Explain Artifact
**Priority:** P0

The Admin Agent MUST explain any valid artifact (framework, spec, package, file).

**Acceptance Criteria:**
- Accept artifact ID (e.g., FMWK-000, SPEC-CORE-001, PKG-KERNEL-001)
- Accept file path (e.g., lib/merkle.py)
- Return human-readable explanation
- Include ownership chain in output
- Return error for unknown artifacts

### FR-ADMIN-002: List Installed Packages
**Priority:** P0

The Admin Agent MUST list installed packages with status.

**Acceptance Criteria:**
- Return list of all installed packages
- Include version, file count, manifest hash
- Include installation timestamp
- Sort by package ID

### FR-ADMIN-003: Show System Health
**Priority:** P0

The Admin Agent MUST show system health via integrity check.

**Acceptance Criteria:**
- Report orphan count
- Report hash verification status
- Report kernel parity status
- Report ledger existence
- Return overall pass/fail

### FR-ADMIN-004: Trace Gate Failures
**Priority:** P1

The Admin Agent SHOULD trace gate failures to root cause.

**Acceptance Criteria:**
- Accept gate ID or failure message
- Identify which check failed
- Suggest remediation if possible

### FR-ADMIN-005: Describe Governed Roots
**Priority:** P1

The Admin Agent SHOULD describe governed roots and path classes.

**Acceptance Criteria:**
- List governed roots from config
- Explain PRISTINE vs DERIVED classification
- Explain APPEND_ONLY paths

### FR-ADMIN-006: Reconstruct Recent Context
**Priority:** P2

The Admin Agent MAY reconstruct recent context from ledgers.

**Acceptance Criteria:**
- Accept time range or entry count
- Return recent governance events
- Include event type, timestamp, decision

### FR-ADMIN-007: Read-Only Mode
**Priority:** P0

The Admin Agent MUST operate in read-only mode.

**Acceptance Criteria:**
- No writes to PRISTINE paths
- Only writes to session ledger (L-EXEC, L-EVIDENCE)
- Sandbox verification passes with empty declared_outputs

### FR-ADMIN-008: Log Queries to L-EXEC
**Priority:** P0

The Admin Agent MUST log all queries to L-EXEC.

**Acceptance Criteria:**
- Every query creates L-EXEC entry
- Entry includes session_id, turn_number
- Entry includes query_hash, result_hash
- Entry includes status

### FR-ADMIN-009: Wrap trace.py
**Priority:** P0

The Admin Agent MUST wrap trace.py for low-level operations.

**Acceptance Criteria:**
- Use subprocess to call trace.py
- Parse JSON output
- Handle trace.py errors gracefully

### FR-ADMIN-010: Human-Friendly Output
**Priority:** P1

The Admin Agent SHOULD add reasoning layer for human-friendly explanations.

**Acceptance Criteria:**
- Format output as readable text
- Add context and explanations
- Highlight important information
