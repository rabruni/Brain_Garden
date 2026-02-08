# Requirements

## Functional Requirements

### FR-EV-001: Deterministic JSON Hashing
**Priority:** P0

The `hash_json()` function MUST produce identical output for identical input across invocations.

**Acceptance Criteria:**
- `hash_json({"a": 1, "b": 2}) == hash_json({"b": 2, "a": 1})`
- Output format: `sha256:<64_hex_chars>`
- Empty dict hashes to consistent value

### FR-EV-002: File Hashing
**Priority:** P0

The `hash_file()` function MUST compute SHA256 hash of file contents.

**Acceptance Criteria:**
- Returns `sha256:<64_hex_chars>` for any readable file
- Raises `FileNotFoundError` for non-existent files
- Handles binary and text files correctly

### FR-EV-003: Evidence Envelope Construction
**Priority:** P0

The `build_evidence()` function MUST construct evidence envelopes with required linkage fields.

**Acceptance Criteria:**
- MUST include `session_id` (string)
- MUST include `turn_number` (int)
- MUST include `input_hash` (string)
- MUST include `output_hash` (string)
- MUST include `timestamp` (ISO8601 string)
- MAY include `work_order_id` if provided
- MAY include `declared_reads` list
- MAY include `declared_writes` list
- MAY include `external_calls` list

### FR-EV-004: Artifact Reference Building
**Priority:** P1

The `build_reference()` function MUST create standardized artifact references.

**Acceptance Criteria:**
- Returns `{"artifact_id": ..., "hash": ..., "timestamp": ...}`
- All references are JSON-serializable

### FR-EV-005: CLI Pipe Interface
**Priority:** P0

The module MUST be invocable via `python3 -m modules.stdlib_evidence` reading JSON from stdin.

**Acceptance Criteria:**
- Reads JSON object from stdin
- Writes JSON response envelope to stdout
- Response envelope has `status`, `result`, `evidence` fields
- Exit code 0 on success, 1 on error

### FR-EV-006: Error Handling
**Priority:** P1

Errors MUST be returned in the response envelope, not raised as exceptions.

**Acceptance Criteria:**
- Invalid JSON input returns `{"status": "error", "error": {"code": "INVALID_JSON", ...}}`
- Missing required fields return `{"status": "error", "error": {"code": "MISSING_FIELD", ...}}`
- Evidence is still emitted even on error

### FR-EV-007: No Side Effects
**Priority:** P0

The module MUST NOT have any filesystem or network side effects.

**Acceptance Criteria:**
- No files created or modified (except stdout)
- No network calls
- No global state modified
- Idempotent: running twice produces identical output
