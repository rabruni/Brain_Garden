# BUILDER_HANDOFF_26B: Observability Tools — Session Forensics

## 1. Mission

Give the admin agent deterministic, server-side tools for session forensics: list sessions, get human-readable overviews, reconstruct full conversation timelines, query ledger entries with full metadata, and grep JSONL files without stuffing them into LLM context. Five new tools in PKG-ADMIN-001, all paginated, all zero LLM token cost for data retrieval.

**Depends on HANDOFF-26A** (pristine memory + budget modes must be complete first — these tools read the enriched ledger data that 26A produces).

One package modified: PKG-ADMIN-001.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write/update tests FIRST.
3. **Package everything.** Modified package gets updated `manifest.json` SHA256 hashes. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> `install.sh` -> all gates pass.
5. **No hardcoding.** Pagination defaults come from tool parameters, not magic constants.
6. **No file replacement.** In-package modifications only.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` -- never with `./` prefix.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_26B.md`.
9. **Full regression test.** Run ALL staged package tests. Report pass/fail.
10. **Baseline snapshot.** Include in results file.
11. **All five tools must be added to `admin_config.json` tools array** -- otherwise HO2 won't expose them to the LLM via tools_allowed.
12. **All five tools must support pagination** via `limit`, `offset` parameters. `max_bytes` caps the total response size.
13. **session_overview must return human-readable summary FIRST**, structured diagnostics second. The `about` field (what this session was about) is the most important single field.

## 3. Architecture / Design

### Tool Overview

```
list_sessions         session_overview         reconstruct_session
     |                      |                          |
     v                      v                          v
  ho2m.jsonl           all 3 ledgers              all 3 ledgers
  (SESSION_START/END)  (aggregated stats)        (merged timeline)

query_ledger_full     grep_jsonl
     |                     |
     v                     v
  any ledger           any ledger
  (full metadata)      (regex filter)
```

### Tool Contracts

#### 1. list_sessions

**Input:** `{limit: 20, offset: 0}`
**Source:** ho2m.jsonl — SESSION_START and SESSION_END events
**Output:**
```json
{
  "status": "ok",
  "count": 3,
  "sessions": [
    {
      "session_id": "SES-ABCD1234",
      "started_at": "2026-02-17T14:30:00Z",
      "ended_at": "2026-02-17T14:42:00Z",
      "duration_seconds": 720,
      "turn_count": 8,
      "status": "completed",
      "first_user_message": "hello",
      "last_response_preview": "Goodbye! Session ended."
    }
  ]
}
```

**Logic:** Scan ho2m for SESSION_START events. For each, find matching SESSION_END (same session_id). Count TURN_RECORDED events. Extract first user_message from first TURN_RECORDED. Status derived from: SESSION_END exists = "completed", no SESSION_END = "active", last event is DEGRADATION = "errored".

#### 2. session_overview

**Input:** `{session_id: "SES-ABCD1234"}`
**Source:** All three ledgers (ho2m, ho1m, governance)
**Output:**
```json
{
  "status": "ok",
  "summary": {
    "session_id": "SES-ABCD1234",
    "started_at": "...",
    "ended_at": "...",
    "duration": "12 minutes",
    "turn_count": 8,
    "status": "completed",
    "about": "User asked about installed frameworks, queried ledger events, and attempted conversation reconstruction. Session ended cleanly.",
    "top_user_messages": ["hello", "what frameworks are installed?", "show me turn events"],
    "errors": [],
    "warnings": [{"type": "budget_warning", "message": "Budget low: 1200 remaining"}]
  },
  "diagnostics": {
    "tokens": {"input_total": 42000, "output_total": 8500, "grand_total": 50500},
    "work_orders": {"total": 16, "by_type": {"classify": 8, "synthesize": 8}, "by_state": {"completed": 14, "failed": 2}},
    "tools": {"total_calls": 5, "by_tool": {"list_packages": {"called": 1, "succeeded": 1, "failed": 0}}},
    "quality_gates": {"passed": 7, "rejected": 1},
    "ledger_events": {"ho2m": 18, "ho1m": 24, "governance": 32}
  }
}
```

**The `about` field is deterministic** — derived from:
- First user message (what they started with)
- Most frequent WO types (what they mostly did)
- Tool call patterns (which tools were used)
- Error/warning presence
- How the session ended (clean /exit, budget exhaustion, error)

Format: one paragraph, plain language, no jargon. Example: "User asked about installed frameworks, queried session ledger for turn events, and read kernel source files. Two budget warnings occurred. Session ended cleanly."

#### 3. reconstruct_session

**Input:** `{session_id: "SES-ABCD1234", limit: 100, offset: 0, max_bytes: 50000, verbosity: "compact", include_prompts: false, include_tool_payloads: true}`
**Source:** All three ledgers
**Output:** Chronological timeline merged by timestamp:
```json
{
  "status": "ok",
  "session_id": "SES-ABCD1234",
  "event_count": 45,
  "returned": 45,
  "timeline": [
    {
      "timestamp": "2026-02-17T14:30:00Z",
      "source": "ho2m",
      "event_type": "SESSION_START",
      "actor": "ho2",
      "turn_number": null,
      "wo_id": null,
      "payload": {}
    },
    {
      "timestamp": "2026-02-17T14:30:01Z",
      "source": "ho2m",
      "event_type": "TURN_RECORDED",
      "actor": "user",
      "turn_number": 1,
      "wo_id": null,
      "payload": {"user_message": "hello", "response": "Hi! How can I help?"}
    },
    {
      "timestamp": "2026-02-17T14:30:01Z",
      "source": "governance",
      "event_type": "EXCHANGE",
      "actor": "gateway",
      "turn_number": null,
      "wo_id": "WO-SES-ABCD1234-001",
      "payload": {"prompt": "...", "response": "...", "input_tokens": 500, "output_tokens": 200}
    }
  ]
}
```

**Merge rules:**
- Primary sort: timestamp
- Tie-breaker: source priority (ho2m > ho1m > governance), then event_id
- Each row includes `source` (which ledger it came from)

**Verbosity modes:**
- `compact`: event_type, actor, wo_id, turn_number, and summary fields only. No prompt/response text.
- `full`: everything including prompts and tool payloads (subject to include_prompts and include_tool_payloads flags)

**max_bytes cap:** If serialized response exceeds max_bytes, truncate the timeline array and set `"truncated": true`.

#### 4. query_ledger_full

**Input:** `{ledger: "governance", event_type: "EXCHANGE", max_entries: 10, offset: 0}`
**Source:** Any single ledger
**Output:** Same as current query_ledger but with FULL metadata (not just metadata_keys):
```json
{
  "status": "ok",
  "source": "governance",
  "count": 2,
  "entries": [
    {
      "id": "EVT-xxx",
      "event_type": "EXCHANGE",
      "submission_id": "PRC-SYNTHESIZE-001",
      "decision": "SUCCESS",
      "reason": "Exchange completed",
      "timestamp": "...",
      "metadata": { ... full metadata dict ... }
    }
  ]
}
```

Existing `query_ledger` is unchanged (backward compatible). `query_ledger_full` is a separate tool.

#### 5. grep_jsonl

**Input:** `{ledger: "ho2m", pattern: "budget_exhausted", limit: 20, offset: 0}`
**Source:** Any single ledger file
**Output:** Matching entries (server-side regex filter):
```json
{
  "status": "ok",
  "source": "ho2m",
  "pattern": "budget_exhausted",
  "count": 3,
  "entries": [
    {
      "line_number": 42,
      "raw": "{ ... full JSON line ... }"
    }
  ]
}
```

**Logic:** Read the JSONL file line by line. Apply regex to each raw line. Return matching lines with line numbers. This is server-side filtering -- the LLM never sees non-matching lines.

### Adversarial Analysis: session_overview `about` field

**Hurdles**: Generating a human-readable summary deterministically (no LLM) requires heuristic text assembly. Edge cases: sessions with 0 turns, sessions that only errored, sessions with only classify WOs.
**Not Enough**: Just returning structured data forces the user to mentally reconstruct what happened. The whole point is "what was this session about" at a glance.
**Too Much**: We could use an LLM call to summarize -- but that defeats the purpose (token cost, latency, budget consumption).
**Synthesis**: Template-based deterministic summary. Start with first user message, add "queried X via Y tool" for each tool used, add "N errors/warnings", end with exit method. Covers all cases without LLM.

## 4. Implementation Steps

### Step 1: Add five tool handlers to main.py

In `_staging/PKG-ADMIN-001/HOT/admin/main.py`, add five functions inside `_register_admin_tools()`:

**1a. `_list_sessions(args)`**: Read ho2m.jsonl, find SESSION_START/END pairs, count TURN_RECORDED per session, extract previews. Paginated.

**1b. `_session_overview(args)`**: Read all three ledgers for given session_id. Compute summary fields, build deterministic `about` string, aggregate diagnostics.

**1c. `_reconstruct_session(args)`**: Read all three ledgers, filter by session_id, merge by timestamp, apply verbosity and include flags, cap at max_bytes.

**1d. `_query_ledger_full(args)`**: Like existing _query_ledger but return full metadata dict instead of metadata_keys. Paginated.

**1e. `_grep_jsonl(args)`**: Read raw JSONL file line by line, apply regex, return matching lines. Paginated.

Register all five:
```python
dispatcher.register_tool("list_sessions", _list_sessions)
dispatcher.register_tool("session_overview", _session_overview)
dispatcher.register_tool("reconstruct_session", _reconstruct_session)
dispatcher.register_tool("query_ledger_full", _query_ledger_full)
dispatcher.register_tool("grep_jsonl", _grep_jsonl)
```

### Step 2: Add five tool entries to admin_config.json

Add to the `tools` array in `admin_config.json`:

```json
{
    "tool_id": "list_sessions",
    "description": "List all sessions with timestamps, turn counts, and previews",
    "handler": "tools.list_sessions",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 20},
            "offset": {"type": "integer", "default": 0}
        }
    }
},
{
    "tool_id": "session_overview",
    "description": "Human-readable session summary with diagnostics (tokens, WOs, tools, errors)",
    "handler": "tools.session_overview",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Session ID to summarize"}
        },
        "required": ["session_id"]
    }
},
{
    "tool_id": "reconstruct_session",
    "description": "Full chronological timeline of a session merged from all ledgers",
    "handler": "tools.reconstruct_session",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "limit": {"type": "integer", "default": 100},
            "offset": {"type": "integer", "default": 0},
            "max_bytes": {"type": "integer", "default": 50000},
            "verbosity": {"type": "string", "enum": ["compact", "full"], "default": "compact"},
            "include_prompts": {"type": "boolean", "default": false},
            "include_tool_payloads": {"type": "boolean", "default": true}
        },
        "required": ["session_id"]
    }
},
{
    "tool_id": "query_ledger_full",
    "description": "Query ledger entries with FULL metadata (not summary)",
    "handler": "tools.query_ledger_full",
    "parameters": {
        "type": "object",
        "properties": {
            "ledger": {"type": "string", "enum": ["governance", "ho2m", "ho1m"], "default": "governance"},
            "event_type": {"type": "string"},
            "max_entries": {"type": "integer", "default": 10},
            "offset": {"type": "integer", "default": 0}
        }
    }
},
{
    "tool_id": "grep_jsonl",
    "description": "Server-side regex search across a ledger file",
    "handler": "tools.grep_jsonl",
    "parameters": {
        "type": "object",
        "properties": {
            "ledger": {"type": "string", "enum": ["governance", "ho2m", "ho1m"]},
            "pattern": {"type": "string", "description": "Regex pattern to match"},
            "limit": {"type": "integer", "default": 20},
            "offset": {"type": "integer", "default": 0}
        },
        "required": ["ledger", "pattern"]
    }
}
```

### Step 3: Update tests

Add new test class `TestForensicTools` in `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`:

See Test Plan (Section 6) for full list.

### Step 4: Governance cycle

1. Update `manifest.json` hashes for PKG-ADMIN-001
2. Delete `.DS_Store` and `__pycache__`, rebuild archive with `pack()`
3. Rebuild `CP_BOOTSTRAP.tar.gz`
4. Clean-room install to temp dir
5. `pytest` -- all tests pass
6. Run 8/8 governance gates

## 5. Package Plan

**No new packages.** One existing package modified:

### PKG-ADMIN-001 (modified)
| Field | Value |
|-------|-------|
| Package ID | PKG-ADMIN-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/admin/main.py` -- 5 new tool handlers + registrations
- `HOT/config/admin_config.json` -- 5 new tool entries
- `HOT/tests/test_admin.py` -- new tests

Dependencies: unchanged

## 6. Test Plan

### PKG-ADMIN-001 new tests (25+)

**TestListSessions:**

| Test | Description | Expected |
|------|-------------|----------|
| `test_list_sessions_returns_sessions` | Populate ho2m with 2 sessions -> list | Returns 2 sessions with IDs |
| `test_list_sessions_includes_turn_count` | Session with 3 turns -> turn_count=3 | turn_count field correct |
| `test_list_sessions_status_completed` | Session with SESSION_END -> completed | status="completed" |
| `test_list_sessions_status_active` | Session without SESSION_END -> active | status="active" |
| `test_list_sessions_pagination` | 5 sessions, limit=2, offset=2 | Returns sessions 3-4 |
| `test_list_sessions_first_message_preview` | Turn with user_message -> preview | first_user_message populated |

**TestSessionOverview:**

| Test | Description | Expected |
|------|-------------|----------|
| `test_overview_human_summary` | Session with turns and tools -> summary | about field is human-readable paragraph |
| `test_overview_about_field_deterministic` | Same session twice -> same about | Identical about strings |
| `test_overview_includes_errors` | Session with budget_exhausted -> errors list | errors array populated |
| `test_overview_token_totals` | Session with known token counts -> totals | tokens.grand_total matches sum |
| `test_overview_tool_counts` | Session with 3 tool calls -> counts | tools.total_calls == 3 |
| `test_overview_wo_by_state` | Session with mixed WO outcomes -> state counts | by_state correctly counted |
| `test_overview_unknown_session` | Non-existent session_id -> error | status="error" |

**TestReconstructSession:**

| Test | Description | Expected |
|------|-------------|----------|
| `test_reconstruct_chronological_order` | Events from 3 ledgers -> merged | Sorted by timestamp |
| `test_reconstruct_includes_source` | Each event -> source field | source in (ho2m, ho1m, governance) |
| `test_reconstruct_compact_mode` | verbosity=compact -> no prompts | No prompt/response text |
| `test_reconstruct_full_mode` | verbosity=full -> includes prompts | prompt and response present |
| `test_reconstruct_pagination` | 50 events, limit=10 -> first 10 | returned==10, event_count==50 |
| `test_reconstruct_max_bytes_cap` | max_bytes=100 -> truncated | truncated=true |

**TestQueryLedgerFull:**

| Test | Description | Expected |
|------|-------------|----------|
| `test_full_returns_metadata` | Entry with metadata -> full dict | metadata is dict, not keys list |
| `test_full_pagination` | 20 entries, offset=5, max_entries=3 | Returns entries 6-8 |
| `test_full_default_governance` | No ledger param -> governance | Reads governance ledger |

**TestGrepJsonl:**

| Test | Description | Expected |
|------|-------------|----------|
| `test_grep_finds_matching_lines` | Pattern matches 3 lines -> returns 3 | count==3 with line numbers |
| `test_grep_returns_raw_json` | Match -> raw field | raw is the original JSON line |
| `test_grep_invalid_ledger` | Unknown ledger -> error | status="error" |
| `test_grep_no_matches` | Pattern matches nothing -> empty | count==0, entries==[] |

**TestForensicToolsInConfig:**

| Test | Description | Expected |
|------|-------------|----------|
| `test_all_forensic_tools_in_config` | All 5 tool_ids in admin_config.json | All present in tools array |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Admin main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | Tool registration pattern, _register_admin_tools |
| Admin config | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | Tool config structure |
| Admin tests | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` | Test patterns |
| LedgerClient | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | read_all(), read_by_event_type() API |
| Session manager | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/session_manager.py` | TURN_RECORDED metadata fields |
| HO2 supervisor | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | WO event metadata fields |
| LLM Gateway | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` | EXCHANGE metadata fields (:486-511) |
| Kernel hashing | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | compute_sha256() |
| Kernel packages | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | pack() |

## 8. End-to-End Verification

```bash
# 1. Clean-room install
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev

# 2. Run all tests
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests/" "$TMPDIR/HO1/tests/" "$TMPDIR/HO2/tests/" -v

# 3. Run gates
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 "$TMPDIR/HOT/scripts/gate_check.py" --all --enforce --root "$TMPDIR"

# 4. Verify all 10 tools in config
python3 -c "
import json
d=json.load(open('$TMPDIR/HOT/config/admin_config.json'))
tools=[t['tool_id'] for t in d['tools']]
expected=['gate_check','read_file','query_ledger','list_files','list_packages',
          'list_sessions','session_overview','reconstruct_session','query_ledger_full','grep_jsonl']
for t in expected:
    assert t in tools, f'{t} missing'
print(f'All {len(expected)} tools present')
"

# 5. E2E with real API (requires ANTHROPIC_API_KEY)
cd "$TMPDIR" && python3 -m admin.main --root "$TMPDIR" --dev
# Verification sequence:
#   admin> hello
#   admin> what sessions exist?
#     -> Expected tool call: list_sessions({})
#     -> Verify: returns at least current session
#   admin> give me an overview of the current session
#     -> Expected tool call: session_overview({"session_id": "<current>"})
#     -> Verify: about field is human-readable, turn_count >= 2
#   admin> /exit
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY |
| `admin_config.json` | `_staging/PKG-ADMIN-001/HOT/config/` | MODIFY |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (hashes) |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_26B.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Human summary first.** session_overview's `about` field is the most important output of this entire handoff. If a user can't tell what a session was about from one sentence, the tool failed.
2. **Server-side filtering.** grep_jsonl and reconstruct_session do their work before returning data. The LLM never processes raw ledger lines it doesn't need.
3. **Pagination everywhere.** Every forensic tool supports limit/offset. reconstruct_session also supports max_bytes. No unbounded result sets.
4. **Deterministic reconstruction.** Same session_id, same ledger data, same parameters = identical output. No LLM-generated summaries.
5. **Backward compatible.** Existing query_ledger is unchanged. query_ledger_full is additive.
6. **Config-driven exposure.** All five tools in admin_config.json. HO2 auto-exposes them via tools_allowed wiring.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-26B** -- Observability tools for session forensics

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_26B_observability_tools.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` -- NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir -> run install.sh -> install YOUR changes on top -> ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_26B.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives.
10. All five tools MUST be added to admin_config.json tools array. Without this, HO2 will not expose them to the LLM.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the FIVE tools this handoff adds? For each, what is its primary data source?
2. What does session_overview's `about` field contain? How is it generated (LLM or deterministic)?
3. What three ledger files does reconstruct_session merge? What is the merge sort key?
4. How does query_ledger_full differ from the existing query_ledger tool?
5. What does grep_jsonl do differently from feeding a file to the LLM via read_file?
6. What pagination parameters must ALL five tools support?
7. What does reconstruct_session's max_bytes parameter do? What happens when the limit is hit?
8. How many new tests are you adding? List the test class names.
9. After adding tools to admin_config.json, how many total tools will ADMIN have? List all tool_ids.
10. This handoff depends on HANDOFF-26A. What specific data from 26A do these tools need to work correctly?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. (1) list_sessions — ho2m.jsonl (SESSION_START/END). (2) session_overview — all 3 ledgers (ho2m, ho1m, governance). (3) reconstruct_session — all 3 ledgers. (4) query_ledger_full — any single ledger. (5) grep_jsonl — any single ledger file.
2. A human-readable one-paragraph summary of what the session was about. Generated DETERMINISTICALLY from ledger data (first user message, tool patterns, errors, exit method). No LLM call.
3. ho2m.jsonl, ho1m.jsonl, governance.jsonl. Primary sort: timestamp. Tie-breaker: source priority (ho2m > ho1m > governance), then event_id.
4. query_ledger returns metadata_keys (just key names) and truncates reason to 200 chars. query_ledger_full returns the full metadata dict and full reason string.
5. grep_jsonl does server-side regex filtering — only matching lines are returned. read_file dumps the entire file into LLM context, burning tokens for every line even non-matching ones.
6. `limit` and `offset`. reconstruct_session also supports `max_bytes`.
7. max_bytes caps the total serialized response size. When exceeded, the timeline array is truncated and `"truncated": true` is set in the response.
8. 25+ tests across 6 test classes: TestListSessions (6), TestSessionOverview (7), TestReconstructSession (6), TestQueryLedgerFull (3), TestGrepJsonl (4), TestForensicToolsInConfig (1).
9. 10 total: gate_check, read_file, query_ledger, list_files, list_packages, list_sessions, session_overview, reconstruct_session, query_ledger_full, grep_jsonl.
10. 26A ensures: (a) TURN_RECORDED fires on ALL paths (degradation, budget failure, etc.) so list_sessions/session_overview have complete data. (b) Full tool logging (no truncation) so reconstruct_session shows complete tool payloads. (c) Budget warnings are logged as events so session_overview can surface them.
