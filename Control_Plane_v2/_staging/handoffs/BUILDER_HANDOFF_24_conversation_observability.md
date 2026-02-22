# BUILDER_HANDOFF_24: Conversation Observability — Turn Persistence + Ledger Enrichment

## 1. Mission

Make conversations observable. Currently the admin shell records operational metadata (WO lifecycle, token costs, gate decisions) but the actual conversation — what the user said and what the system answered — is ephemeral. It lives in `SessionManager._history` (in-memory list) and dies when the session ends. The `query_ledger` tool returns only entry IDs, hiding all content. The `prompts_used` field on every ledger entry is always `[]`.

Three fixes across three packages:

1. **PKG-HO2-SUPERVISOR-001** — Persist each conversation turn as a `TURN_RECORDED` ledger event in `SessionManager.add_turn()`
2. **PKG-ADMIN-001** — Enrich `query_ledger` tool to return event_type + metadata excerpt (not just entry IDs)
3. **PKG-HO1-EXECUTOR-001** — Populate `prompts_used` field with `prompt_pack_id` in HO1 `_log_event()`

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write/update tests FIRST. Every change gets test coverage.
3. **Package everything.** Modified packages get updated `manifest.json` SHA256 hashes. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> `install.sh` -> all gates pass.
5. **No hardcoding.** Turn content truncation length (if any) comes from config, not a magic constant.
6. **No file replacement.** These are in-package modifications, no cross-package file changes.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never with `./` prefix.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_24.md`.
9. **Full regression test.** Run ALL staged package tests. Report pass/fail.
10. **Baseline snapshot.** Include in results file.
11. **This is a targeted fix.** Do NOT refactor surrounding code. Do NOT touch files outside the ones listed in Files Summary.

## 3. Architecture / Design

### Current State

```
User types "hello"
    |
    v
SessionManager.add_turn("hello", "Hi there!")       [session_manager.py:95]
    |-- appends to _history (in-memory list)         [session_manager.py:97-98]
    |-- increments _turn_count                       [session_manager.py:99]
    |-- writes NOTHING to ledger
    |
    v
Session ends -> SESSION_END logged                   [session_manager.py:77]
    |-- _history is garbage collected
    |-- conversation is GONE
```

```
query_ledger tool called
    |
    v
_query_ledger(args)                                  [main.py:107]
    |-- reads ledger entries
    |-- returns only: {"entries": [e.id for e in entries]}   [main.py:120]
    |-- event_type, metadata, content: ALL HIDDEN
```

```
HO1 logs LLM_CALL event
    |
    v
_log_event("LLM_CALL", wo, ...)                     [ho1_executor.py:395]
    |-- LedgerEntry created with prompts_used=[]     [default_factory=list]
    |-- prompt_pack_id is KNOWN (from contract)
    |-- but NEVER passed to prompts_used
```

### Fix Design

| Fix | Package | File | What | Why |
|-----|---------|------|------|-----|
| 1 | PKG-HO2-SUPERVISOR-001 | `session_manager.py` | Write `TURN_RECORDED` ledger event in `add_turn()` | Conversations must survive session end |
| 2 | PKG-ADMIN-001 | `main.py` | Return event_type + metadata excerpt from `query_ledger` | Entry IDs alone are useless |
| 3 | PKG-HO1-EXECUTOR-001 | `ho1_executor.py` | Pass `prompt_pack_id` to `prompts_used` in `_log_event()` | Dead field should carry data |

### Adversarial Analysis: Persisting Conversation Content to Ledger

**Hurdles**: Ledger is append-only with hash chaining. Large conversation turns increase ledger size. Need to decide whether to store full content or truncated excerpts.
**Not Enough**: If we only persist turn metadata (e.g., turn number, token count) without the actual text, the conversation is still effectively lost. The whole point is recoverability.
**Too Much**: We could build a separate conversation store with search, pagination, and retrieval. Overkill — the ledger already exists and handles append-only persistence.
**Synthesis**: Store full user message and response text in `TURN_RECORDED` events. Ledger is already designed for this kind of audit data. Truncation can be added later if ledger size becomes an issue.

## 4. Implementation Steps

### Step 1: Persist turns in SessionManager

In `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/session_manager.py`, modify `add_turn()` (line 95) to write a ledger event:

**Before:**
```python
    def add_turn(self, user_message: str, response: str) -> None:
        """Track turn in in-memory history."""
        self._history.append(TurnMessage(role="user", content=user_message))
        self._history.append(TurnMessage(role="assistant", content=response))
        self._turn_count += 1
```

**After:**
```python
    def add_turn(self, user_message: str, response: str) -> None:
        """Track turn in in-memory history and persist to ledger."""
        self._history.append(TurnMessage(role="user", content=user_message))
        self._history.append(TurnMessage(role="assistant", content=response))
        self._turn_count += 1
        self._ledger.write(
            LedgerEntry(
                event_type="TURN_RECORDED",
                submission_id=self._session_id or "unknown",
                decision="RECORDED",
                reason=f"Turn {self._turn_count} recorded",
                metadata={
                    "provenance": {
                        "agent_id": self._agent_id,
                        "agent_class": self._agent_class,
                        "session_id": self._session_id or "unknown",
                    },
                    "turn_number": self._turn_count,
                    "user_message": user_message,
                    "response": response,
                },
            )
        )
```

### Step 2: Enrich query_ledger tool output

In `_staging/PKG-ADMIN-001/HOT/admin/main.py`, modify `_query_ledger()` (line 107) to return useful content:

**Before (line 117-121):**
```python
        return {
            "status": "ok",
            "count": len(entries),
            "entries": [e.id for e in entries],
        }
```

**After:**
```python
        return {
            "status": "ok",
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "submission_id": e.submission_id,
                    "decision": e.decision,
                    "reason": e.reason[:200] if e.reason else "",
                    "timestamp": e.timestamp,
                    "metadata_keys": sorted(e.metadata.keys()) if e.metadata else [],
                }
                for e in entries
            ],
        }
```

This gives the LLM enough to answer questions about the ledger without dumping the full metadata (which could be huge for EXCHANGE entries with prompt text).

### Step 3: Populate prompts_used in HO1

In `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`, modify `_log_event()` (line 395) to include prompt_pack_id:

**Before:**
```python
    def _log_event(self, event_type: str, wo: dict, **metadata):
        entry = LedgerEntry(
            event_type=event_type,
            submission_id=wo.get("wo_id", ""),
            decision=event_type,
            reason=f"{event_type} for {wo.get('wo_id', '')}",
            metadata={
                "provenance": {
                    "agent_id": self.config.get("agent_id", ""),
                    "agent_class": self.config.get("agent_class", "ADMIN"),
                    "work_order_id": wo.get("wo_id", ""),
                    "session_id": wo.get("session_id", ""),
                },
                "scope": {"tier": "ho1"},
                **metadata,
            },
        )
        self.ledger.write(entry)
```

**After:**
```python
    def _log_event(self, event_type: str, wo: dict, **metadata):
        # Extract prompt_pack_id from WO constraints -> contract
        prompt_contract_id = wo.get("constraints", {}).get("prompt_contract_id", "")
        prompt_pack_id = ""
        if prompt_contract_id:
            try:
                contract = self.contract_loader.load(prompt_contract_id)
                prompt_pack_id = contract.get("prompt_pack_id", "")
            except Exception:
                pass
        prompts = [prompt_pack_id] if prompt_pack_id else []

        entry = LedgerEntry(
            event_type=event_type,
            submission_id=wo.get("wo_id", ""),
            decision=event_type,
            reason=f"{event_type} for {wo.get('wo_id', '')}",
            prompts_used=prompts,
            metadata={
                "provenance": {
                    "agent_id": self.config.get("agent_id", ""),
                    "agent_class": self.config.get("agent_class", "ADMIN"),
                    "work_order_id": wo.get("wo_id", ""),
                    "session_id": wo.get("session_id", ""),
                },
                "scope": {"tier": "ho1"},
                **metadata,
            },
        )
        self.ledger.write(entry)
```

Note: `contract_loader.load()` caches contracts, so the repeated call is not expensive. The `try/except` handles cases where the contract is unavailable (e.g., tool_call WOs with no contract).

### Step 4: Update tests

**PKG-HO2-SUPERVISOR-001** — update `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py`:

Add to `TestSessionManagement` class:
- `test_add_turn_writes_turn_recorded_event` — add_turn() writes TURN_RECORDED to ledger
- `test_turn_recorded_contains_user_message` — metadata has user_message field
- `test_turn_recorded_contains_response` — metadata has response field
- `test_turn_recorded_has_turn_number` — metadata has turn_number field
- `test_turn_recorded_has_session_id` — submission_id is the session_id

**PKG-ADMIN-001** — update `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`:

Add new test class `TestQueryLedgerEnrichment`:
- `test_query_ledger_returns_event_type` — entries have event_type field
- `test_query_ledger_returns_timestamp` — entries have timestamp field
- `test_query_ledger_returns_submission_id` — entries have submission_id field
- `test_query_ledger_returns_metadata_keys` — entries have metadata_keys list
- `test_query_ledger_reason_truncated` — reason field truncated to 200 chars

**PKG-HO1-EXECUTOR-001** — update `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py`:

Add to `TestTraceWriting` class:
- `test_llm_call_entry_has_prompts_used` — LLM_CALL entry has non-empty prompts_used
- `test_prompts_used_contains_prompt_pack_id` — prompts_used[0] matches prompt_pack_id from contract
- `test_prompts_used_empty_for_tool_call_wo` — tool_call WO type has empty prompts_used (no contract)

### Step 5: Governance cycle

1. Update `manifest.json` hashes for all three packages
2. Delete `.DS_Store` files, rebuild archives with `pack()`
3. Rebuild `CP_BOOTSTRAP.tar.gz`
4. Clean-room install to temp dir
5. `pytest` -- all tests pass
6. Run 8/8 governance gates

## 5. Package Plan

**No new packages.** Three existing packages modified:

### PKG-HO2-SUPERVISOR-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO2-SUPERVISOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho2 |

Modified assets:
- `HO2/kernel/session_manager.py` -- add TURN_RECORDED ledger write
- `HO2/tests/test_ho2_supervisor.py` -- new tests for turn persistence

Dependencies: unchanged (PKG-KERNEL-001, PKG-WORK-ORDER-001)

### PKG-ADMIN-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-ADMIN-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/admin/main.py` -- enrich query_ledger output
- `HOT/tests/test_admin.py` -- new tests for enriched output

Dependencies: unchanged

### PKG-HO1-EXECUTOR-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO1-EXECUTOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho1 |

Modified assets:
- `HO1/kernel/ho1_executor.py` -- populate prompts_used in _log_event()
- `HO1/tests/test_ho1_executor.py` -- new tests for prompts_used

Dependencies: unchanged (PKG-KERNEL-001, PKG-TOKEN-BUDGETER-001, PKG-LLM-GATEWAY-001)

## 6. Test Plan

### PKG-HO2-SUPERVISOR-001 new tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_add_turn_writes_turn_recorded_event` | add_turn() writes to ledger | TURN_RECORDED event in ledger |
| `test_turn_recorded_contains_user_message` | Event metadata has user text | metadata["user_message"] == input |
| `test_turn_recorded_contains_response` | Event metadata has response text | metadata["response"] == output |
| `test_turn_recorded_has_turn_number` | Event metadata has turn count | metadata["turn_number"] == N |
| `test_turn_recorded_has_session_id` | Event submission_id is session | submission_id starts with "SES-" |

### PKG-ADMIN-001 new tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_query_ledger_returns_event_type` | Enriched entries have event_type | entry["event_type"] is string |
| `test_query_ledger_returns_timestamp` | Enriched entries have timestamp | entry["timestamp"] is ISO string |
| `test_query_ledger_returns_submission_id` | Entries have submission_id | entry["submission_id"] is string |
| `test_query_ledger_returns_metadata_keys` | Entries list metadata keys | entry["metadata_keys"] is list |
| `test_query_ledger_reason_truncated` | Long reasons truncated to 200 chars | len(entry["reason"]) <= 200 |

### PKG-HO1-EXECUTOR-001 new tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_llm_call_entry_has_prompts_used` | LLM_CALL entry prompts_used non-empty | len(prompts_used) >= 1 |
| `test_prompts_used_contains_prompt_pack_id` | prompts_used[0] matches contract | "PRM-CLASSIFY-001" in prompts_used |
| `test_prompts_used_empty_for_tool_call_wo` | tool_call WO has no contract | prompts_used == [] |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| SessionManager (current) | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/session_manager.py` | add_turn() to modify |
| HO2 tests (current) | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` | Test patterns, MockLedgerClient |
| Admin main.py (current) | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | query_ledger to modify |
| Admin tests (current) | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` | Test patterns |
| HO1 executor (current) | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | _log_event() to modify |
| HO1 tests (current) | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | Test patterns |
| LedgerEntry definition | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py:104` | prompts_used field at line 111 |
| LLM Gateway exchange | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py:493` | How prompt/response is already stored in metadata |
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

# 4. E2E with real API (requires ANTHROPIC_API_KEY)
cd "$TMPDIR" && python3 -m admin.main --root "$TMPDIR" --dev
# Test sequence:
#   admin> hello
#   admin> what did I just say?
#   admin> query the ledger for TURN_RECORDED events
#   admin> /exit
# Expected:
#   - "hello" gets natural language response
#   - "what did I just say?" — system can't answer from memory alone yet,
#     but TURN_RECORDED event is now in the ledger
#   - query_ledger returns enriched entries with event_type, timestamp, metadata_keys
#   - After exit, HO2m ledger contains TURN_RECORDED entries with user_message + response
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `session_manager.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY (hashes) |
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (hashes) |
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | MODIFY |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY (hashes) |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_24.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Conversations are data.** If it happened, it's in the ledger. In-memory-only history is a bug, not a feature.
2. **Tools return useful content.** Entry IDs with no context force the LLM to guess. Give it event_type, timestamp, and metadata keys so it can answer questions.
3. **Dead fields carry data or get removed.** `prompts_used` exists on every ledger entry. Either populate it or delete it. Populating is cheaper.
4. **Truncate at the boundary, not the source.** Store full content in the ledger. Truncate in the tool response (reason[:200]) to keep LLM context manageable.
5. **Append-only is your friend.** TURN_RECORDED events are cheap, immutable, and auditable. No new infrastructure needed.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-24** -- Conversation observability: turn persistence + ledger enrichment

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_24_conversation_observability.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` -- NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir -> run install.sh -> install YOUR changes on top -> ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_24.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
10. This is a targeted fix. Do NOT refactor surrounding code. Do NOT add new abstractions. Do NOT touch files outside the 14 listed in the Files Summary.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the THREE gaps this handoff fixes? Name each with the package it touches.
2. Where does conversation history currently live, and why is that a problem? (File, line, data structure)
3. What event_type does the new turn persistence use? What fields go in its metadata?
4. What does `query_ledger` currently return? What does it return after the fix? What is NOT included and why?
5. What is `prompts_used` on LedgerEntry? Why is it always empty? Where does the prompt_pack_id come from?
6. How many new tests are you adding to each package? List them by name.
7. The HO1 `_log_event()` change calls `contract_loader.load()`. Why is this safe (not expensive)? What happens for tool_call WOs?
8. Which THREE manifest.json files need updated hashes? Which THREE .tar.gz archives need rebuilding?
9. What tar format command do you use for archive rebuilds? What format do SHA256 hashes use in manifests?
10. After all changes, what admin shell command sequence would verify turn persistence is working?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. (a) Turn persistence — PKG-HO2-SUPERVISOR-001 (session_manager.py), (b) Ledger enrichment — PKG-ADMIN-001 (main.py), (c) prompts_used population — PKG-HO1-EXECUTOR-001 (ho1_executor.py)
2. `SessionManager._history` (in-memory list, session_manager.py:46). Problem: garbage collected on session end. No persistence.
3. `TURN_RECORDED`. Metadata: provenance (agent_id, agent_class, session_id), turn_number, user_message, response.
4. Currently: `{"entries": [e.id for e in entries]}` — IDs only. After: each entry includes id, event_type, submission_id, decision, reason (truncated to 200), timestamp, metadata_keys. Full metadata NOT included because EXCHANGE entries can contain huge prompt text.
5. `prompts_used: List[str]` field on LedgerEntry (ledger_client.py:111). Default is empty list. Always empty because no writer passes it. prompt_pack_id comes from the contract loaded via `constraints.prompt_contract_id`.
6. HO2: 5 tests (turn_recorded_event, user_message, response, turn_number, session_id). ADMIN: 5 tests (event_type, timestamp, submission_id, metadata_keys, reason_truncated). HO1: 3 tests (prompts_used_non_empty, contains_pack_id, empty_for_tool_call).
7. ContractLoader caches loaded contracts. For tool_call WOs, `prompt_contract_id` is empty string -> try block catches exception -> prompts stays `[]`.
8. Manifests: PKG-HO2-SUPERVISOR-001, PKG-ADMIN-001, PKG-HO1-EXECUTOR-001. Archives: same three .tar.gz plus CP_BOOTSTRAP.tar.gz.
9. `tar czf ... -C dir $(ls dir)`. SHA256 format: `sha256:<64hex>` (71 chars).
10. `admin> hello` -> get response -> `admin> query the ledger for TURN_RECORDED events` -> see enriched entries with event_type and metadata_keys -> verify TURN_RECORDED exists. Or after exit, inspect HO2m ledger file directly.
