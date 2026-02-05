# Requirements

## Functional Requirements

### FR-RT-001: Load Agent Package
**Priority:** P0

The runtime MUST load agent packages from `installed/<pkg-id>/`.

**Acceptance Criteria:**
- Load manifest.json from package directory
- Extract capabilities from manifest
- Raise PackageNotFoundError if package missing

### FR-RT-002: Read Capabilities from Manifest
**Priority:** P0

The runtime MUST read capabilities from manifest.capabilities.

**Acceptance Criteria:**
- Parse `capabilities.read` as list of glob patterns
- Parse `capabilities.execute` as list of allowed commands
- Parse `capabilities.write` as list of writable path patterns
- Parse `capabilities.forbidden` as list of denied patterns

### FR-RT-003: Enforce Capabilities at Runtime
**Priority:** P0

The runtime MUST enforce read/write/execute capabilities during execution.

**Acceptance Criteria:**
- Block reads to paths not matching `capabilities.read`
- Block writes to paths not matching `capabilities.write`
- Block executions not matching `capabilities.execute`
- Block any operation matching `capabilities.forbidden`
- Raise CapabilityViolation on blocked operations

### FR-RT-004: Generate Session ID
**Priority:** P0

The runtime MUST generate unique session_id for each session.

**Acceptance Criteria:**
- Format: `SES-<timestamp>-<random>`
- Timestamp component for ordering
- Random component for uniqueness
- No collisions in concurrent sessions

### FR-RT-005: Build Prompt Header
**Priority:** P1

The runtime MUST build prompt headers with declared context.

**Acceptance Criteria:**
- Include session_id, turn_number
- Include declared_inputs list with hashes
- Include declared_outputs list
- Include context_as_of timestamp
- Include work_order_id if present

### FR-RT-006: Write L-EXEC Entry
**Priority:** P0

The runtime MUST write L-EXEC entries to session ledger.

**Acceptance Criteria:**
- Path: `planes/<tier>/sessions/<sid>/ledger/exec.jsonl`
- Entry includes: session_id, turn_number, query_hash, result_hash, status
- Entry follows LedgerEntry schema
- Hash chain maintained

### FR-RT-007: Write L-EVIDENCE Entry
**Priority:** P0

The runtime MUST write L-EVIDENCE entries to session ledger.

**Acceptance Criteria:**
- Path: `planes/<tier>/sessions/<sid>/ledger/evidence.jsonl`
- Entry includes: session_id, turn_number, work_order_id (if present)
- Entry includes: declared_reads[], declared_writes[], external_calls[]
- Written for every turn, even on error

### FR-RT-008: Verify Ledger Chain
**Priority:** P1

The runtime MUST verify ledger chain integrity on reads.

**Acceptance Criteria:**
- Verify entry_hash matches computed hash
- Verify previous_hash links correctly
- Log warning on legacy entries (no hash)
- Raise IntegrityError on tampered entries

### FR-RT-009: Support HO2 Checkpoints
**Priority:** P2

The runtime SHOULD support HO2 hybrid checkpoints for context acceleration.

**Acceptance Criteria:**
- Find latest checkpoint before target timestamp
- Replay only entries since checkpoint
- Merge checkpoint state with recent deltas

### FR-RT-010: Raise CapabilityViolation on Forbidden
**Priority:** P0

The runtime MUST raise CapabilityViolation for forbidden operations.

**Acceptance Criteria:**
- Check against `capabilities.forbidden` patterns
- Block operation before execution
- Log violation to L-EVIDENCE
- Include violation details in exception

### FR-RT-011: Log Capability Violations
**Priority:** P0

The runtime MUST log all capability violations to L-EVIDENCE.

**Acceptance Criteria:**
- Log attempted operation
- Log violated capability
- Log session_id and turn_number
- Log timestamp

### FR-RT-012: Execute in Session-Scoped Sandbox
**Priority:** P0

The runtime MUST execute each turn inside a session-scoped sandbox.

**Acceptance Criteria:**
- Sandbox paths: `tmp/<sid>/`, `output/<sid>/`
- All other paths read-only
- Subprocess temp files redirected to sandbox
- Sandbox created before turn, verified after

### FR-RT-013: Require declared_outputs
**Priority:** P0

The runtime MUST require `request.declared_outputs[]` for every turn.

**Acceptance Criteria:**
- Reject turns without declared_outputs field
- Each entry has path and role
- Paths must match capabilities.write patterns

### FR-RT-014: Set TMPDIR for Subprocess Isolation
**Priority:** P0

The runtime MUST set TMPDIR/TEMP/TMP to session sandbox.

**Acceptance Criteria:**
- TMPDIR = `tmp/<sid>/`
- TEMP = `tmp/<sid>/`
- TMP = `tmp/<sid>/`
- PYTHONDONTWRITEBYTECODE = 1 (no .pyc files)

### FR-RT-015: Enumerate Realized Writes
**Priority:** P0

The runtime MUST enumerate realized writes post-execution.

**Acceptance Criteria:**
- Walk `tmp/<sid>/` and `output/<sid>/`
- Compute hash for each file
- Record path, hash, size
- Compare to declared_outputs

### FR-RT-016: Block on Write Surface Mismatch
**Priority:** P0

The runtime MUST block turn if realized != declared.

**Acceptance Criteria:**
- If undeclared writes exist, raise CapabilityViolation
- If declared writes missing, raise CapabilityViolation
- Write violation to L-EVIDENCE
- Do NOT copy outputs to final locations

### FR-RT-017: Evidence Linkage Fields
**Priority:** P0

Evidence entries MUST include session_id, turn_number, work_order_id.

**Acceptance Criteria:**
- session_id always present
- turn_number always present (1-indexed)
- work_order_id present if turn is under work order

### FR-RT-018: Both Ledgers Required
**Priority:** P0

Both exec.jsonl and evidence.jsonl MUST exist for valid session.

**Acceptance Criteria:**
- Create both ledgers on session start
- Write to both per turn
- Gate validation checks both exist
