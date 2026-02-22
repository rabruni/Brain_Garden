# BUILDER_HANDOFF_30: Forensic Observability Surface

## 1. Mission

Add deterministic forensic tooling to **PKG-ADMIN-001** so admins can see the exact prompt journey for any turn — what was sent to the LLM, what came back, what tools were called, what the gate decided — reconstructed from ledger entries alone, with no LLM summarization. Introduces two shared modules (`forensic_policy.py`, `ledger_forensics.py`), one new tool (`trace_prompt_journey`), and flips forensic tool defaults from compact/hidden to full/visible.

**Package:** PKG-ADMIN-001 (modified, no new packages)

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every change gets test coverage.
3. **Package everything.** Modified package gets updated `manifest.json` SHA256 hashes. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → `install.sh` → all gates pass.
5. **No hardcoding.** Forensic policy defaults come from `ForensicPolicy` dataclass, not magic constants scattered per tool.
6. **No file replacement.** These are in-package modifications, no cross-package file changes.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never with `./` prefix.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_30.md`.
9. **Full regression test.** Run ALL staged package tests. Report pass/fail.
10. **Baseline snapshot.** Include in results file.
11. **Single package scope.** This handoff modifies ONLY PKG-ADMIN-001. Do NOT touch HO1, HO2, Gateway, or any other package.
12. **No LLM changes.** The trace tool reads ledgers. It does NOT add logging to HO1/HO2/Gateway. Those packages already log everything needed.

## 3. Architecture / Design

### The Problem

The system logs everything — every prompt, response, tool call, gate decision — to three append-only ledgers. But the admin tools default to compact views that hide the evidence. When the admin asks "show latest sessions", they get an LLM narrative about sessions, not the actual data. There is no tool that reassembles the full prompt journey for a turn from ledger entries.

### What Exists (Data Sources)

All data is already in the ledgers. Verified by LP2 trace:

| Ledger | Event Types | Key Fields |
|--------|-------------|------------|
| `governance.jsonl` | EXCHANGE, DISPATCH, PROMPT_REJECTED, BUDGET_WARNING | `metadata.prompt` (FULL TEXT), `metadata.response` (FULL TEXT), `metadata.input_tokens`, `metadata.output_tokens`, `metadata.model_id`, `metadata.work_order_id`, `metadata.session_id`, `metadata.dispatch_entry_id`, `metadata.context_hash`, `metadata.finish_reason`, `metadata.tools_offered`, `metadata.tool_use_in_response`, `metadata.retry_count` |
| `ho2m.jsonl` | WO_PLANNED, WO_DISPATCHED, WO_CHAIN_COMPLETE, WO_QUALITY_GATE, TURN_RECORDED, SESSION_START, SESSION_END | `metadata.provenance.work_order_id`, `metadata.provenance.session_id`, `metadata.wo_type`, `metadata.context_fingerprint`, `metadata.cost`, `metadata.wo_ids` |
| `ho1m.jsonl` | WO_EXECUTING (implicit via state transition), LLM_CALL, TOOL_CALL, WO_COMPLETED, WO_FAILED | `metadata.provenance.work_order_id`, `metadata.tool_id`, `metadata.arguments`, `metadata.result`, `metadata.input_tokens`, `metadata.output_tokens`, `metadata.model_id`, `metadata.cost` |

### Design: Two Shared Modules + One Tool + Default Flips

#### Module 1: `forensic_policy.py`

A single policy object that all forensic tools read from. Prevents each tool from inventing its own compact/full semantics.

```python
@dataclass
class ForensicPolicy:
    """Shared defaults for forensic tool behavior."""
    verbosity: str = "full"           # was "compact" — forensic truth first
    include_prompts: bool = True      # was False — prompts are the evidence
    include_tool_payloads: bool = True
    include_responses: bool = True
    include_evidence_ids: bool = True  # new: attach ledger entry IDs to each stage
    max_bytes: int = 500_000          # was 50000 — forensic data is large
    max_entries: int = 200            # pagination cap
    truncation_marker: str = "[TRUNCATED at {bytes} bytes — use offset to continue]"
```

Tools that are NOT forensic (list_sessions summary, session_overview "about" paragraph) keep their current compact defaults. Only `reconstruct_session`, `query_ledger_full`, `grep_jsonl`, and the new `trace_prompt_journey` use `ForensicPolicy`.

#### Module 2: `ledger_forensics.py`

Shared helpers for ledger reassembly. Eliminates duplicate correlation logic across forensic tools.

```python
def read_all_ledgers(root: Path, session_id: str) -> dict[str, list]:
    """Read all three ledgers, filter by session_id, return grouped by source."""

def correlate_by_wo(entries: list) -> dict[str, list]:
    """Group entries by work_order_id across all ledger sources."""

def order_chronologically(entries: list) -> list:
    """Sort by (timestamp, source_priority, entry_id). Source priority: ho2m=0, ho1m=1, governance=2."""

def extract_stages(wo_entries: list) -> list[dict]:
    """From a WO's entries, extract ordered stages: planned → dispatched → executing → prompt → response → tool_calls → completed/failed → gate."""

def entry_session_id(entry) -> str | None:
    """Extract session_id from entry metadata (all probing paths)."""

def entry_wo_id(entry) -> str | None:
    """Extract work_order_id from entry metadata (all probing paths)."""
```

These functions are factored FROM the existing `_entry_session_id`, `_entry_wo_id`, `_entry_matches_session`, `_read_entries`, `_parse_ts` helpers already in `main.py`. The existing tool functions (`_reconstruct_session`, etc.) will be updated to call these shared helpers instead of their inlined copies.

#### Tool: `trace_prompt_journey`

Deterministic, ledger-reassembled prompt journey for a session or specific work order.

**Input:**
```json
{
  "session_id": "SES-abc123",
  "wo_id": "(optional) WO-abc123-001",
  "turn_number": "(optional) 1",
  "include_prompts": true,
  "include_tool_payloads": true,
  "include_responses": true,
  "limit": 200,
  "offset": 0,
  "max_bytes": 500000
}
```

**Output:**
```json
{
  "status": "ok",
  "session_id": "SES-abc123",
  "wo_count": 2,
  "llm_call_count": 3,
  "tool_call_count": 1,
  "turns": [
    {
      "turn_number": 1,
      "wo_chain": [
        {
          "wo_id": "WO-abc123-001",
          "wo_type": "classify",
          "stages": [
            {
              "stage": "wo_planned",
              "timestamp": "...",
              "evidence_id": "LE-...",
              "input_context": {"user_input": "show latest sessions"}
            },
            {
              "stage": "wo_dispatched",
              "timestamp": "...",
              "evidence_id": "LE-..."
            },
            {
              "stage": "prompt_sent",
              "timestamp": "...",
              "evidence_id": "LE-...",
              "prompt_text": "You are a speech act classifier...",
              "prompt_hash": "sha256:...",
              "model_id": "claude-sonnet-4-5-20250929",
              "provider_id": "anthropic"
            },
            {
              "stage": "llm_response",
              "timestamp": "...",
              "evidence_id": "LE-...",
              "response_text": "{\"speech_act\":\"command\"...}",
              "input_tokens": 150,
              "output_tokens": 30,
              "finish_reason": "stop",
              "latency_ms": 450
            },
            {
              "stage": "wo_completed",
              "timestamp": "...",
              "evidence_id": "LE-...",
              "output_result": {"speech_act": "command", "ambiguity": "low"}
            }
          ]
        },
        {
          "wo_id": "WO-abc123-002",
          "wo_type": "synthesize",
          "stages": [
            {"stage": "wo_planned", "...": "..."},
            {"stage": "wo_dispatched", "...": "..."},
            {"stage": "prompt_sent", "prompt_text": "...", "...": "..."},
            {"stage": "llm_response", "finish_reason": "tool_use", "...": "..."},
            {
              "stage": "tool_call",
              "tool_id": "list_sessions",
              "arguments": {"limit": 5},
              "result": {"sessions": ["..."]},
              "evidence_id": "LE-..."
            },
            {"stage": "prompt_sent", "prompt_text": "...(with tool results)...", "...": "..."},
            {"stage": "llm_response", "response_text": "Here are...", "...": "..."},
            {"stage": "wo_completed", "...": "..."}
          ]
        }
      ],
      "quality_gate": {
        "decision": "accept",
        "reason": "...",
        "evidence_id": "LE-..."
      }
    }
  ],
  "truncated": false
}
```

#### Correlation Logic

1. **Session → WOs**: Find all entries across three ledgers matching `session_id`. Group by `wo_id`.
2. **WO → Stages**: For each WO, order entries chronologically. Map event types to stage names:
   - `WO_PLANNED` → `wo_planned`
   - `WO_DISPATCHED` → `wo_dispatched`
   - `DISPATCH` (governance) → correlated to WO via `metadata.session_id` + `metadata.work_order_id`
   - `EXCHANGE` (governance) → `prompt_sent` + `llm_response` (split: prompt from metadata.prompt, response from metadata.response)
   - `LLM_CALL` (ho1m) → correlated via `metadata.provenance.work_order_id`
   - `TOOL_CALL` (ho1m) → `tool_call`
   - `WO_COMPLETED` / `WO_FAILED` → `wo_completed` / `wo_failed`
   - `WO_QUALITY_GATE` (ho2m) → `quality_gate`
3. **WOs → Turns**: Group WOs into turns. Each turn starts with a classify WO, followed by synthesize WO(s). Turn number comes from `TURN_RECORDED.metadata.turn_number` if present, else sequential order.
4. **Evidence linkage**: Every stage includes the `evidence_id` — the ledger entry's own `id` field — so the admin can drill into any stage with `query_ledger_full`.

#### Default Flips

| Tool | Field | Before | After |
|------|-------|--------|-------|
| `reconstruct_session` | `verbosity` | `"compact"` | `ForensicPolicy.verbosity` ("full") |
| `reconstruct_session` | `include_prompts` | `False` | `ForensicPolicy.include_prompts` (True) |
| `reconstruct_session` | `max_bytes` | `50000` | `ForensicPolicy.max_bytes` (500000) |
| `query_ledger_full` | `limit` | `10` | `ForensicPolicy.max_entries` (200) |

The user can still override any default via explicit tool arguments. The policy just flips what happens when they DON'T specify.

### Adversarial Analysis: Centralizing Forensic Policy

**Hurdles**: Existing tests assert current defaults (verbosity="compact", include_prompts=False). Those tests need updating. Risk of breaking reconstruct_session behavior for users who expect compact output by default.

**Not Enough**: Without centralization, each new forensic tool will reinvent defaults. We already have 4 forensic tools with inconsistent truncation behavior. Adding trace_prompt_journey as a 5th with yet another set of inline defaults compounds the drift.

**Too Much**: Could build a full forensic framework with mode switching, output formatters, and evidence graph builders. That's premature — we have 1 consumer (ADMIN). The dataclass + module is the minimum viable centralization.

**Synthesis**: Centralize as a dataclass + shared helper module in PKG-ADMIN-001. Not a framework, not cross-package. Just stop duplicating the same 6 defaults in 5 places.

### Adversarial Analysis: Flipping reconstruct_session Defaults

**Hurdles**: Users who relied on compact output will suddenly get verbose output. But this is an admin tool — admins want truth, not polish. And the old behavior is one `verbosity="compact"` arg away.

**Not Enough**: If we don't flip defaults, the new trace_prompt_journey tool returns full data but the existing reconstruct_session still hides it. Admin gets inconsistent experiences depending on which tool they happen to use.

**Too Much**: Could add a global "forensic mode" toggle that switches all tools at once. Overkill — the dataclass defaults achieve this already, and per-tool overrides remain available.

**Synthesis**: Flip defaults. Compact mode remains available via explicit args. No user data is lost in either direction — it's just what you see by default.

## 4. Implementation Steps

### Step 1: Create `forensic_policy.py`

Create `_staging/PKG-ADMIN-001/HOT/admin/forensic_policy.py`:

```python
"""Shared forensic policy for ADMIN tools.

Centralizes defaults so forensic tools behave consistently.
Tools that are NOT forensic (list_sessions, session_overview) do not use this.
"""

from dataclasses import dataclass


@dataclass
class ForensicPolicy:
    """Shared defaults for forensic tool behavior.

    Used by: reconstruct_session, query_ledger_full, grep_jsonl, trace_prompt_journey.
    NOT used by: list_sessions, session_overview (those are summary tools, not forensic).
    """
    verbosity: str = "full"
    include_prompts: bool = True
    include_tool_payloads: bool = True
    include_responses: bool = True
    include_evidence_ids: bool = True
    max_bytes: int = 500_000
    max_entries: int = 200
    truncation_marker: str = "[TRUNCATED at {bytes} bytes — use offset to continue]"


# Singleton default policy — import and use directly
DEFAULT_POLICY = ForensicPolicy()
```

### Step 2: Create `ledger_forensics.py`

Create `_staging/PKG-ADMIN-001/HOT/admin/ledger_forensics.py`:

Implement the shared helpers listed in the Architecture section. The key functions:

- `read_all_ledgers(root, session_id)` — reads ho2m, ho1m, governance; filters by session; returns `{"ho2m": [...], "ho1m": [...], "governance": [...]}`.
- `correlate_by_wo(entries_by_source)` — groups all entries by wo_id; returns `{"WO-xxx-001": [entry1, entry2, ...]}`.
- `order_chronologically(entries)` — sorts by (timestamp, source_priority, id).
- `extract_stages(wo_entries)` — maps event types to named stages with evidence_ids.
- `entry_session_id(entry)` — refactored from main.py `_entry_session_id`.
- `entry_wo_id(entry)` — refactored from main.py `_entry_wo_id`.
- `entry_matches_session(entry, session_id)` — refactored from main.py `_entry_matches_session`.
- `parse_ts(ts_string)` — refactored from main.py `_parse_ts`.

Import `LedgerClient` with the same try/except pattern used in main.py.

### Step 3: Create `test_forensic_policy.py`

Create `_staging/PKG-ADMIN-001/HOT/tests/test_forensic_policy.py`.

Tests for ForensicPolicy dataclass defaults and overrides. See Test Plan section.

### Step 4: Create `test_ledger_forensics.py`

Create `_staging/PKG-ADMIN-001/HOT/tests/test_ledger_forensics.py`.

Tests for all shared helper functions. Uses tmp_path with synthetic JSONL entries. See Test Plan section.

### Step 5: Create `test_trace_prompt_journey.py`

Create `_staging/PKG-ADMIN-001/HOT/tests/test_trace_prompt_journey.py`.

Tests for the trace_prompt_journey tool handler. Uses fixture ledgers with known entries. See Test Plan section.

### Step 6: Add `trace_prompt_journey` tool handler to `main.py`

In `_register_admin_tools()`, add `_trace_prompt_journey` handler function:

1. Import `ForensicPolicy`, `DEFAULT_POLICY` from `forensic_policy`.
2. Import `read_all_ledgers`, `correlate_by_wo`, `order_chronologically`, `extract_stages` from `ledger_forensics`.
3. Parse args: session_id (required), wo_id (optional filter), turn_number (optional filter), plus forensic policy overrides.
4. Call `read_all_ledgers(root, session_id)` to get all entries.
5. Call `correlate_by_wo()` to group by WO.
6. For each WO group, call `extract_stages()` to build ordered stages.
7. Group WOs into turns (classify + synthesize pairs).
8. Apply `include_prompts`, `include_tool_payloads`, `include_responses` filters.
9. Apply `max_bytes` truncation with explicit marker.
10. Register: `dispatcher.register_tool("trace_prompt_journey", _trace_prompt_journey)`.

### Step 7: Refactor `_reconstruct_session` to use shared modules

In `main.py`, update `_reconstruct_session`:

1. Import `DEFAULT_POLICY` from `forensic_policy`.
2. Change default for `verbosity` from `"compact"` to `DEFAULT_POLICY.verbosity`.
3. Change default for `include_prompts` from `False` to `DEFAULT_POLICY.include_prompts`.
4. Change default for `max_bytes` from `50000` to `DEFAULT_POLICY.max_bytes`.
5. Replace inline `_entry_session_id`, `_entry_wo_id`, `_entry_matches_session`, `_parse_ts` calls with imports from `ledger_forensics`.

### Step 8: Refactor `_query_ledger_full` to use shared policy

Update default `limit` from `10` to `DEFAULT_POLICY.max_entries`.

### Step 9: Refactor shared helpers out of `main.py`

The following functions currently defined inside `_register_admin_tools` will be replaced by imports from `ledger_forensics`:
- `_entry_session_id` → `ledger_forensics.entry_session_id`
- `_entry_wo_id` → `ledger_forensics.entry_wo_id`
- `_entry_matches_session` → `ledger_forensics.entry_matches_session`
- `_parse_ts` → `ledger_forensics.parse_ts`
- `_read_entries` → `ledger_forensics.read_entries`
- `_resolve_ledger_source` → `ledger_forensics.resolve_ledger_source`
- `_get_ledger_map` → `ledger_forensics.get_ledger_map`

Keep these as thin wrappers or direct imports inside `_register_admin_tools` closure, since they need `root` from the closure scope. The `ledger_forensics` functions take `root` as an explicit parameter.

### Step 10: Update `admin_config.json`

Add `trace_prompt_journey` tool definition to the `tools` array:

```json
{
  "tool_id": "trace_prompt_journey",
  "description": "Reconstruct the full prompt journey for a session/turn from ledger entries. Returns ordered stages: WO planning, exact prompts sent, LLM responses, tool calls, gate decisions. Deterministic, no LLM summarization.",
  "handler": "tools.trace_prompt_journey",
  "parameters": {
    "type": "object",
    "properties": {
      "session_id": {"type": "string", "description": "Session ID to trace"},
      "wo_id": {"type": "string", "description": "Optional: filter to specific WO"},
      "turn_number": {"type": "integer", "description": "Optional: filter to specific turn"},
      "include_prompts": {"type": "boolean", "default": true, "description": "Include full prompt text"},
      "include_tool_payloads": {"type": "boolean", "default": true, "description": "Include tool arguments and results"},
      "include_responses": {"type": "boolean", "default": true, "description": "Include full LLM response text"},
      "limit": {"type": "integer", "default": 200},
      "offset": {"type": "integer", "default": 0},
      "max_bytes": {"type": "integer", "default": 500000}
    },
    "required": ["session_id"]
  }
}
```

### Step 11: Update `reconstruct_session` defaults in `admin_config.json`

Change the tool definition's parameter defaults:
- `verbosity` default: `"compact"` → `"full"`
- `include_prompts` default: `false` → `true`
- `max_bytes` default: `50000` → `500000`

### Step 12: Governance cycle

1. Update `manifest.json` SHA256 hashes for all modified and new assets.
2. Add new assets to manifest: `forensic_policy.py`, `ledger_forensics.py`, `test_forensic_policy.py`, `test_ledger_forensics.py`, `test_trace_prompt_journey.py`.
3. Delete `.DS_Store` files, rebuild archive with `pack()`.
4. Rebuild `CP_BOOTSTRAP.tar.gz`.
5. Clean-room install to temp dir.
6. `pytest` — all tests pass.
7. Run 8/8 governance gates.

## 5. Package Plan

**No new packages.** One existing package modified:

### PKG-ADMIN-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-ADMIN-001 |
| Version | 1.1.0 (bump from 1.0.0) |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

New assets:
- `HOT/admin/forensic_policy.py` — classification: library
- `HOT/admin/ledger_forensics.py` — classification: library
- `HOT/tests/test_forensic_policy.py` — classification: test
- `HOT/tests/test_ledger_forensics.py` — classification: test
- `HOT/tests/test_trace_prompt_journey.py` — classification: test

Modified assets:
- `HOT/admin/main.py` — trace_prompt_journey tool, refactored helpers
- `HOT/config/admin_config.json` — new tool def, updated defaults
- `HOT/tests/test_admin.py` — updated default assertions

Dependencies: unchanged

## 6. Test Plan

### `test_forensic_policy.py` — 6 tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_default_verbosity_full` | ForensicPolicy() has verbosity="full" | verbosity == "full" |
| `test_default_include_prompts_true` | ForensicPolicy() has include_prompts=True | include_prompts is True |
| `test_default_max_bytes` | ForensicPolicy() has max_bytes=500_000 | max_bytes == 500000 |
| `test_override_verbosity` | ForensicPolicy(verbosity="compact") | verbosity == "compact" |
| `test_truncation_marker_format` | truncation_marker contains `{bytes}` placeholder | "{bytes}" in marker |
| `test_default_policy_singleton` | DEFAULT_POLICY matches ForensicPolicy() | all fields equal |

### `test_ledger_forensics.py` — 14 tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_entry_session_id_from_metadata` | Entry with metadata.session_id | Returns session_id |
| `test_entry_session_id_from_provenance` | Entry with metadata.provenance.session_id | Returns session_id |
| `test_entry_session_id_from_submission` | Entry with SES- submission_id | Returns submission_id |
| `test_entry_session_id_missing` | Entry with no session info | Returns None |
| `test_entry_wo_id_from_provenance` | Entry with metadata.provenance.work_order_id | Returns wo_id |
| `test_entry_wo_id_from_submission` | Entry with WO- submission_id | Returns submission_id |
| `test_entry_wo_id_missing` | Entry with no WO info | Returns None |
| `test_read_all_ledgers_filters_session` | 3 ledgers with mixed sessions | Only matching entries returned |
| `test_read_all_ledgers_missing_files` | Ledger file doesn't exist | Returns empty list for that source |
| `test_correlate_by_wo_groups` | Entries from 3 sources with same wo_id | Grouped under one key |
| `test_order_chronologically` | Entries with varied timestamps and sources | Sorted by time, then source priority |
| `test_extract_stages_classify_wo` | WO entries for a classify WO | Stages: planned → dispatched → prompt_sent → llm_response → wo_completed |
| `test_extract_stages_synthesize_with_tools` | WO entries with tool calls | Stages include tool_call between prompt_sent and followup prompt_sent |
| `test_extract_stages_evidence_ids` | Every stage from extract_stages | Each stage dict has "evidence_id" key |

### `test_trace_prompt_journey.py` — 12 tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_journey_requires_session_id` | Call without session_id | Returns status=error |
| `test_journey_empty_session` | Session with no ledger entries | Returns status=ok, turns=[], wo_count=0 |
| `test_journey_single_turn_no_tools` | Classify + synthesize WO, no tool calls | 1 turn, 2 WOs, 2 LLM calls, 0 tool calls |
| `test_journey_single_turn_with_tool` | Classify + synthesize WO with 1 tool call | 1 turn, 2 WOs, 3 LLM calls, 1 tool call |
| `test_journey_multi_turn` | 2 complete turns | 2 turns, each with classify + synthesize |
| `test_journey_includes_prompt_text` | include_prompts=True | prompt_sent stage has prompt_text field |
| `test_journey_excludes_prompt_text` | include_prompts=False | prompt_sent stage has NO prompt_text field |
| `test_journey_includes_tool_payload` | include_tool_payloads=True | tool_call stage has arguments + result |
| `test_journey_excludes_tool_payload` | include_tool_payloads=False | tool_call stage has tool_id only, no arguments/result |
| `test_journey_filter_by_wo_id` | wo_id filter specified | Only stages for that WO returned |
| `test_journey_max_bytes_truncation` | max_bytes=1000 with large data | truncated=True, truncation marker present |
| `test_journey_quality_gate_included` | Turn with quality gate entry | Turn has quality_gate dict with decision + evidence_id |

### Updated `test_admin.py` — existing tests modified

| Change | Description |
|--------|-------------|
| Update default assertions | Any test that asserts `verbosity=="compact"` or `include_prompts==False` for reconstruct_session must be updated to expect the new defaults |
| Add trace_prompt_journey registration test | Verify tool is registered in dispatcher |

Estimated delta: ~3 tests updated, ~1 test added = net 0 new in test_admin.py (updates only).

### Total new tests: 32 (6 + 14 + 12)

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Admin main.py (current) | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | Lines to modify, existing helper patterns |
| Admin config (current) | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | Tool definition format, existing defaults |
| Admin tests (current) | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` | Test patterns, fixture setup |
| Admin manifest (current) | `_staging/PKG-ADMIN-001/manifest.json` | Asset registration pattern |
| LedgerClient | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | LedgerEntry fields, read_all(), read_by_event_type() |
| Gateway EXCHANGE write | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py:537-591` | Exact fields in EXCHANGE metadata |
| HO1 TOOL_CALL write | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py:221-231` | Exact fields in TOOL_CALL metadata |
| HO2 WO event writes | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py:436-531` | WO_PLANNED, WO_DISPATCHED, etc. metadata structure |
| Kernel hashing | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | compute_sha256() for manifest updates |
| Kernel packages | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | pack() for archive rebuilds |

## 8. End-to-End Verification

```bash
# 1. Clean-room install
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev

# 2. Run all tests
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR" -v

# 3. Run gates
python3 "$TMPDIR/HOT/scripts/gate_check.py" --all --enforce --root "$TMPDIR"

# 4. Verify trace_prompt_journey tool exists
python3 -c "
import sys; sys.path.insert(0, '$TMPDIR/HOT/admin')
from forensic_policy import ForensicPolicy, DEFAULT_POLICY
assert DEFAULT_POLICY.verbosity == 'full'
assert DEFAULT_POLICY.include_prompts == True
assert DEFAULT_POLICY.max_bytes == 500000
print('forensic_policy: OK')
"

# 5. E2E with real API (requires ANTHROPIC_API_KEY)
cd "$TMPDIR" && python3 -m admin.main --root "$TMPDIR" --dev
# Test:
#   admin> hello
#   admin> show latest sessions
#   admin> /exit
# Then run trace_prompt_journey on the session that was just created
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `forensic_policy.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | CREATE |
| `ledger_forensics.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | CREATE |
| `test_forensic_policy.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | CREATE |
| `test_ledger_forensics.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | CREATE |
| `test_trace_prompt_journey.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | CREATE |
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY |
| `admin_config.json` | `_staging/PKG-ADMIN-001/HOT/config/` | MODIFY |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (hashes + new assets) |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_30.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Forensic truth first.** Default to showing everything. Compact mode is opt-in, not opt-out. An admin tool that hides evidence by default is broken.
2. **Ledger is the single source.** trace_prompt_journey reconstructs from ledger entries only. No runtime state, no in-memory caches, no LLM calls to "explain" what happened.
3. **Evidence-linked output.** Every stage in the journey carries the ledger entry ID that proves it. The admin can drill into any stage with `query_ledger_full`.
4. **Centralize policy, not logic.** ForensicPolicy is a shared defaults object, not a framework. It tells tools what their defaults should be. It doesn't control how they execute.
5. **Shared helpers, not shared abstractions.** ledger_forensics.py provides functions, not classes. No inheritance, no strategy pattern, no plugin system. Just stop duplicating the same 7 helper functions in 5 tools.
6. **Backward compatible.** Users can still pass `verbosity="compact"` and `include_prompts=false` to get the old behavior. Defaults changed, API unchanged.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-30** — Forensic observability surface for ADMIN tools

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_30_forensic_observability.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → install YOUR changes on top → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_30.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
10. This modifies ONLY PKG-ADMIN-001. Do NOT touch HO1, HO2, Gateway, or any other package. Do NOT add logging to other packages — the ledger data is already there.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the TWO new modules this handoff creates? What is the purpose of each?
2. What is the ONE new tool added? What does it return that no existing tool returns?
3. Which THREE ledgers does trace_prompt_journey read from? What are their filesystem paths relative to the plane root?
4. How does the tool correlate entries across ledgers to the same WO? What metadata field links them?
5. What is the EXCHANGE event's metadata.prompt field? Is it a hash, a summary, or the full prompt text? (Verify by reading llm_gateway.py:568)
6. Name the FOUR existing forensic tools whose defaults are being changed. What are the OLD and NEW defaults for reconstruct_session's verbosity?
7. What does every stage in the trace output include to enable drill-down? Why is this important?
8. How many total new tests are you adding? Break down by test file.
9. What tar format command do you use? What format do SHA256 hashes use in manifests?
10. After this handoff, how many total tools does ADMIN have at runtime (static + dev)?

**Adversarial Bonus Questions:**
11. **Failure Mode:** If this build fails at gate G0A, which specific new file is the most likely culprit?
12. **Shortcut Check:** Is there a temptation to use `json.loads()` on raw JSONL lines instead of `LedgerClient.read_all()`? Why must you NOT do that?
13. **Semantic Audit:** The word "reconstruct" appears in both `reconstruct_session` and `trace_prompt_journey`. What is the semantic difference between these two tools?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. `forensic_policy.py` — shared ForensicPolicy dataclass with centralized defaults (verbosity, include_prompts, max_bytes, etc.). `ledger_forensics.py` — shared helper functions for ledger reading, session/WO correlation, chronological ordering, and stage extraction. Eliminates duplicated logic across forensic tools.
2. `trace_prompt_journey` — returns ordered stages (wo_planned → prompt_sent → llm_response → tool_call → wo_completed → quality_gate) with evidence IDs, reconstructed deterministically from ledger entries. No existing tool shows the full prompt journey with exact prompt text, response text, and tool payloads in stage order.
3. `governance.jsonl` (HOT/ledger/), `ho2m.jsonl` (HO2/ledger/), `ho1m.jsonl` (HO1/ledger/).
4. `metadata.provenance.work_order_id` is the primary correlation key. Also `metadata.work_order_id` and entries where `submission_id` starts with `WO-`. EXCHANGE entries are linked via `metadata.work_order_id` and `metadata.session_id`.
5. FULL TEXT. `llm_gateway.py:568` writes `"prompt": request.prompt` — the complete rendered prompt string. NOT a hash, NOT a summary.
6. `reconstruct_session`, `query_ledger_full`, `grep_jsonl`, and `trace_prompt_journey` (new). reconstruct_session verbosity: OLD="compact", NEW="full".
7. `evidence_id` — the ledger entry's own `id` field. Enables drill-down via `query_ledger_full` to see the full entry. Important because it links the summary view to the underlying truth.
8. 32 new tests: 6 in test_forensic_policy.py, 14 in test_ledger_forensics.py, 12 in test_trace_prompt_journey.py.
9. `tar czf ... -C dir $(ls dir)`. SHA256 format: `sha256:<64hex>` (71 chars).
10. 15 tools at runtime: 12 static (existing 11 + trace_prompt_journey) + 4 dev behind dual gate. Wait — existing static is 12 (10 core + show_runtime_config + list_tuning_files). So: 13 static + 4 dev = 17 total. Let me recount: gate_check, read_file, query_ledger, list_files, list_packages, list_sessions, session_overview, reconstruct_session, query_ledger_full, grep_jsonl, show_runtime_config, list_tuning_files = 12 static. Plus trace_prompt_journey = 13. Plus 4 dev = 17 at runtime (with dual gate).
11. `forensic_policy.py` or `ledger_forensics.py` — new files must be declared in manifest.json assets with correct SHA256 hashes. Missing or wrong hashes cause G0A UNDECLARED failure.
12. Yes, tempting for `_grep_jsonl` which already does raw line reading. But `LedgerClient.read_all()` handles hash chain verification, proper deserialization into LedgerEntry objects with typed fields, and future format changes. Raw parsing bypasses governance.
13. `reconstruct_session` returns a chronological timeline of ALL events for a session — a flat, time-ordered list. `trace_prompt_journey` returns a structured, stage-based view organized by turn → WO → stage, specifically showing the prompt→response→tool→gate flow. reconstruct is "what happened when", trace is "what did the LLM see and say".
