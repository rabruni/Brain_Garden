# BUILDER_HANDOFF_26A: Pristine Memory + Budget Modes

## 1. Mission

Make the Control Plane's memory truly pristine: every execution path produces a complete, reconstructable ledger record, and budget never silently kills a development session. Fix the six logging gaps that make conversation history feel broken, move all hardcoded budget constants to config, and add budget modes (enforce/warn/off) so development sessions survive.

Four packages modified: PKG-HO2-SUPERVISOR-001, PKG-HO1-EXECUTOR-001, PKG-LLM-GATEWAY-001, PKG-ADMIN-001 (config only).

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write/update tests FIRST. Every change gets test coverage.
3. **Package everything.** Modified packages get updated `manifest.json` SHA256 hashes. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> `install.sh` -> all gates pass.
5. **No hardcoding.** ALL budget values must come from config. Zero budget literals in HO2/HO1/Gateway logic after this handoff.
6. **No file replacement.** These are in-package modifications, no cross-package file changes.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` -- never with `./` prefix.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_26A.md`.
9. **Full regression test.** Run ALL staged package tests. Report pass/fail.
10. **Baseline snapshot.** Include in results file.
11. **Budget modes must be wired consistently** across HO2 (WO creation), HO1 (tool loop budget check), and Gateway (pre-check/debit). All three must respect the same mode.
12. **TURN_RECORDED must fire on EVERY terminal path** -- success, quality-gate reject, retry exhausted, degradation/exception, and budget failure. No path may exit handle_turn() without persisting the turn.

## 3. Architecture / Design

### The Six Logging Gaps (Current State)

```
Gap 1: TURN_RECORDED skipped on degradation
  ho2_supervisor.py:286-300 — except block returns TurnResult
  without calling self._session_mgr.add_turn()
  IMPACT: conversation turns vanish when exceptions occur

Gap 2: Tool args/results truncated
  ho1_executor.py:197 — args_summary capped at 200 chars
  ho1_executor.py:198 — result_summary capped at 500 chars
  IMPACT: forensic replay loses detail for large payloads

Gap 3: Tool errors not captured in TOOL_CALL events
  ho1_executor.py:199 — logs tool_id + status but not error detail
  IMPACT: failures look opaque in ledger

Gap 4: _handle_tool_call logs sparse metadata
  ho1_executor.py:277 — only logs tool_id + status, no args/result
  IMPACT: tool_call WOs have less forensic detail than tool-loop calls

Gap 5: query_ledger hides metadata values
  main.py:142 — returns metadata_keys, not metadata values
  main.py:140 — truncates reason to 200 chars
  IMPACT: looks like memory is missing even when raw ledger has it

Gap 6: Budget failures produce opaque errors
  ho1_executor.py:207 — "Only N tokens remain" with no structured event
  Gateway budget check returns generic string
  IMPACT: can't trace why a turn died without reading raw logs
```

### Budget Architecture (Current vs Target)

**Current hardcoded values:**
| Value | Location | Current |
|-------|----------|---------|
| classify_budget | ho2_supervisor.py:153 | `2000` literal |
| synthesize_budget | HO2Config:62 default | `16000` |
| followup_min_remaining | ho1_executor.py:207 | `500` literal |
| session_token_limit | admin_config.json:114 | `200000` (already config) |
| enforcement_hard_limit | BudgetConfig:141 | `True` (exists but NOT wired into check()) |

**Target:** All values in admin_config.json, wired through build_session_host_v2 -> HO2Config -> WO constraints.

### Budget Mode Design

```
admin_config.json:
  "budget": {
    "session_token_limit": 200000,
    "classify_budget": 2000,
    "synthesize_budget": 16000,
    "followup_min_remaining": 500,
    "budget_mode": "warn",    // enforce | warn | off
    "turn_limit": 50,
    "timeout_seconds": 7200
  }
```

Mode behavior across all three enforcement points:

| Mode | HO2 WO creation | HO1 tool loop check | Gateway pre-check/debit |
|------|------------------|---------------------|------------------------|
| enforce | Use budget values as-is | Fail if remaining < min | Reject if over budget |
| warn | Use budget values, log warnings | Log warning, continue | Debit + log warning, never reject |
| off | Use budget values (still allocate for tracking) | Skip check entirely | Debit for tracking, never reject |

**Key insight:** Even in `off` mode, we still allocate and debit for tracking purposes. The mode only controls whether violations cause failures.

### Adversarial Analysis: Budget Mode Wiring

**Hurdles**: Three separate codepaths must respect budget_mode. If any one doesn't, behavior is inconsistent. Gateway is the trickiest — it currently returns a rejection PromptResponse that HO1 treats as a hard failure.
**Not Enough**: Just raising budget numbers doesn't fix the structural problem. Large forensic requests will always exceed any fixed limit. Mode=warn is the only way to guarantee dev sessions survive.
**Too Much**: We could redesign the entire budget system (streaming budget, predictive allocation). Overkill — the current hierarchical model is sound, it just needs a mode switch.
**Synthesis**: Thread budget_mode through the existing check/debit pipeline. Gateway in warn/off mode returns SUCCESS with a warning annotation instead of REJECTED. HO1 checks the mode before failing on remaining < min. HO2 passes the mode into WO constraints so HO1 and Gateway can read it.

## 4. Implementation Steps

### Step 1: Add budget fields to admin_config.json

In `_staging/PKG-ADMIN-001/HOT/config/admin_config.json`, replace the budget section:

**Before:**
```json
"budget": {
    "session_token_limit": 200000,
    "turn_limit": 50,
    "timeout_seconds": 7200
}
```

**After:**
```json
"budget": {
    "session_token_limit": 200000,
    "classify_budget": 2000,
    "synthesize_budget": 100000,
    "followup_min_remaining": 500,
    "budget_mode": "warn",
    "turn_limit": 50,
    "timeout_seconds": 7200
}
```

Note: synthesize_budget set to 100000 for dev (was 16000). Production can lower it.

### Step 2: Wire budget config through build_session_host_v2

In `_staging/PKG-ADMIN-001/HOT/admin/main.py`, update `build_session_host_v2()`:

**2a**: Pass new budget fields into HO2Config (around line 288):
```python
ho2_config = HO2Config(
    ...
    synthesize_budget=budget_cfg.get("synthesize_budget", 16000),
    classify_budget=budget_cfg.get("classify_budget", 2000),
    followup_min_remaining=budget_cfg.get("followup_min_remaining", 500),
    budget_mode=budget_cfg.get("budget_mode", "enforce"),
    ...
)
```

**2b**: Pass budget_mode to HO1 config (around line 271):
```python
ho1_config = {
    ...
    "budget_mode": budget_cfg.get("budget_mode", "enforce"),
    "followup_min_remaining": budget_cfg.get("followup_min_remaining", 500),
}
```

### Step 3: Add config fields to HO2Config

In `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py`, add to HO2Config dataclass (around line 62):

```python
classify_budget: int = 2000
followup_min_remaining: int = 500
budget_mode: str = "enforce"  # enforce | warn | off
```

### Step 4: Replace hardcoded budget in classify WO

In `ho2_supervisor.py`, line 153, replace:
```python
"token_budget": 2000,
```
With:
```python
"token_budget": self._config.classify_budget,
```

### Step 5: Add TURN_RECORDED to degradation path

In `ho2_supervisor.py`, in the `except` block (around line 286-300), add `add_turn` call before the return:

```python
except Exception as exc:
    self._log_degradation(session_id, str(exc))
    degradation_response = f"[Degradation: {exc}]"
    self._session_mgr.add_turn(user_message, degradation_response)
    return TurnResult(
        response=degradation_response,
        ...
    )
```

### Step 6: Add budget_mode to HO1 tool loop

In `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`:

**6a**: Read budget_mode from config in execute() (after line 84):
```python
budget_mode = self.config.get("budget_mode", "enforce")
followup_min = self.config.get("followup_min_remaining", 500)
```

**6b**: Replace the hardcoded 500 check (line 206-214) with mode-aware logic:
```python
remaining_budget = token_budget - cost.get("total_tokens", 0)
if remaining_budget < followup_min:
    if budget_mode == "enforce":
        return self._fail_wo(wo, cost, start_time, "budget_exhausted",
            f"Only {remaining_budget} tokens remain after tool calls")
    elif budget_mode == "warn":
        self._log_event("BUDGET_WARNING", wo,
            remaining=remaining_budget, followup_min=followup_min,
            message=f"Budget low: {remaining_budget} < {followup_min}, continuing in warn mode")
    # off mode: skip entirely
```

**6c**: Replace the pre-loop budget check (line 134-137) with mode-aware logic:
```python
if self.budgeter:
    check = self.budgeter.check(self._make_budget_scope(wo, token_budget - cost.get("total_tokens", 0)))
    if not check.allowed:
        if budget_mode == "enforce":
            return self._fail_wo(wo, cost, start_time, "budget_exhausted", "Token budget exhausted")
        elif budget_mode == "warn":
            self._log_event("BUDGET_WARNING", wo,
                remaining=check.remaining, reason=str(check.reason),
                message="Budget check failed, continuing in warn mode")
        # off mode: skip entirely
```

### Step 7: Fix tool logging gaps in HO1

In `ho1_executor.py`:

**7a**: Remove truncation from tool call logging (lines 197-198). Replace with full payload + size tracking:
```python
args_full = json.dumps(tu.get("arguments", {}), default=str)
result_full = json.dumps(result_output, default=str) if result_output is not None else ""
self._log_event("TOOL_CALL", wo,
    tool_id=tu["tool_id"],
    status=getattr(tool_result, "status", "unknown"),
    arguments=tu.get("arguments", {}),
    result=result_output,
    args_bytes=len(args_full),
    result_bytes=len(result_full),
    tool_error=getattr(tool_result, "error", None),
)
```

**7b**: Fix _handle_tool_call sparse logging (line 277). Add full args/result:
```python
self._log_event("TOOL_CALL", wo,
    tool_id=tool_id,
    status=getattr(result, "status", "unknown"),
    arguments=input_context,
    result=getattr(result, "output", None),
    tool_error=getattr(result, "error", None),
)
```

### Step 8: Add budget_mode to Gateway

In `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py`:

**8a**: Accept budget_mode in __init__ (or read from a config attribute):
Add parameter: `budget_mode: str = "enforce"` to LLMGateway.__init__().
Store as `self._budget_mode = budget_mode`.

**8b**: Modify _check_budget (line 425-438):
```python
def _check_budget(self, request, model_id):
    ...
    result = self._budgeter.check(scope)
    if not result.allowed:
        if self._budget_mode == "enforce":
            return f"Budget check failed: {result.reason}"
        elif self._budget_mode == "warn":
            # Log warning but don't reject
            self._write_budget_warning(request, result)
            return None  # allow through
        else:  # off
            return None
    return None
```

**8c**: Add `_write_budget_warning` method to log BUDGET_WARNING events to ledger.

**8d**: Pass budget_mode when constructing Gateway in main.py build_session_host_v2():
```python
gateway = LLMGateway(
    ...
    budget_mode=budget_cfg.get("budget_mode", "enforce"),
)
```

### Step 9: Add common event fields

Ensure ALL ledger events across HO2, HO1, and Gateway include these fields in metadata.provenance:
- `session_id`
- `wo_id` (where applicable)
- `turn_number` (where applicable)
- `agent_id`

Most events already have session_id and agent_id. The gaps are:
- HO1 events missing turn_number (not available at HO1 level — acceptable, HO2 tracks turns)
- Gateway EXCHANGE events have session_id via request.session_id -- already present

### Step 10: Update tests

**PKG-HO2-SUPERVISOR-001** -- `test_ho2_supervisor.py`:
- `test_turn_recorded_on_degradation` -- exception path writes TURN_RECORDED
- `test_turn_recorded_on_quality_gate_reject` -- verify add_turn called even when gate rejects
- `test_turn_recorded_on_retry_exhausted` -- verify add_turn after max retries
- `test_classify_budget_from_config` -- verify classify WO uses config.classify_budget not literal 2000
- `test_budget_mode_propagated_to_wo` -- budget_mode in HO2Config accessible

**PKG-HO1-EXECUTOR-001** -- `test_ho1_executor.py`:
- `test_budget_mode_warn_continues_on_exhaustion` -- warn mode logs warning, doesn't fail WO
- `test_budget_mode_off_skips_check` -- off mode bypasses budget check entirely
- `test_budget_mode_enforce_fails` -- enforce mode fails as before (existing behavior)
- `test_tool_call_logs_full_arguments` -- no truncation in TOOL_CALL event
- `test_tool_call_logs_error_detail` -- tool_error field populated on failure
- `test_handle_tool_call_logs_full_metadata` -- _handle_tool_call path has args/result
- `test_followup_min_from_config` -- uses config value not hardcoded 500

**PKG-LLM-GATEWAY-001** -- `test_llm_gateway.py`:
- `test_budget_mode_warn_allows_request` -- warn mode doesn't reject
- `test_budget_mode_warn_logs_warning` -- BUDGET_WARNING event written
- `test_budget_mode_off_bypasses_check` -- off mode skips budget check
- `test_budget_mode_enforce_rejects` -- enforce mode rejects (existing behavior)

**PKG-ADMIN-001** -- `test_admin.py`:
- `test_budget_config_fields_passed_to_ho2` -- verify new fields reach HO2Config
- `test_budget_mode_passed_to_gateway` -- verify mode reaches Gateway
- `test_budget_mode_passed_to_ho1` -- verify mode reaches HO1 config

### Step 11: Governance cycle

1. Update `manifest.json` hashes for all 4 modified packages
2. Delete `.DS_Store` and `__pycache__`, rebuild archives with `pack()`
3. Rebuild `CP_BOOTSTRAP.tar.gz`
4. Clean-room install to temp dir
5. `pytest` -- all tests pass
6. Run 8/8 governance gates

## 5. Package Plan

**No new packages.** Four existing packages modified:

### PKG-HO2-SUPERVISOR-001 (modified)
| Field | Value |
|-------|-------|
| Package ID | PKG-HO2-SUPERVISOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HO2/kernel/ho2_supervisor.py` -- classify budget from config, add_turn on degradation, budget_mode field
- `HO2/tests/test_ho2_supervisor.py` -- new tests

### PKG-HO1-EXECUTOR-001 (modified)
| Field | Value |
|-------|-------|
| Package ID | PKG-HO1-EXECUTOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho1 |

Modified assets:
- `HO1/kernel/ho1_executor.py` -- budget mode-aware checks, full tool logging, no truncation
- `HO1/tests/test_ho1_executor.py` -- new tests

### PKG-LLM-GATEWAY-001 (modified)
| Field | Value |
|-------|-------|
| Package ID | PKG-LLM-GATEWAY-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/kernel/llm_gateway.py` -- budget_mode parameter, warn/off behavior
- `HOT/tests/test_llm_gateway.py` -- new tests

### PKG-ADMIN-001 (modified - config only)
| Field | Value |
|-------|-------|
| Package ID | PKG-ADMIN-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/admin/main.py` -- wire new budget fields through build_session_host_v2
- `HOT/config/admin_config.json` -- new budget fields
- `HOT/tests/test_admin.py` -- new tests

## 6. Test Plan

### PKG-HO2-SUPERVISOR-001 new tests (5)

| Test | Description | Expected |
|------|-------------|----------|
| `test_turn_recorded_on_degradation` | HO1 raises exception -> TURN_RECORDED still written | add_turn called with degradation message |
| `test_turn_recorded_on_quality_gate_reject` | Gate rejects after max retries -> TURN_RECORDED written | add_turn called with gate failure message |
| `test_turn_recorded_on_retry_exhausted` | All retries fail -> TURN_RECORDED written | add_turn called before return |
| `test_classify_budget_from_config` | HO2Config.classify_budget=5000 -> classify WO uses 5000 | classify WO constraints.token_budget == 5000 |
| `test_budget_mode_in_ho2_config` | HO2Config accepts budget_mode field | config.budget_mode == "warn" |

### PKG-HO1-EXECUTOR-001 new tests (7)

| Test | Description | Expected |
|------|-------------|----------|
| `test_budget_mode_warn_continues` | budget_mode=warn, remaining < min -> WO continues | WO completes, BUDGET_WARNING logged |
| `test_budget_mode_off_skips_check` | budget_mode=off -> no budget failure possible | WO completes regardless of budget |
| `test_budget_mode_enforce_fails` | budget_mode=enforce, remaining < min -> WO fails | budget_exhausted error |
| `test_tool_call_logs_full_arguments` | Tool call with large args -> full args in event | No truncation, args_bytes field present |
| `test_tool_call_logs_error_detail` | Tool returns error -> tool_error in event | tool_error field populated |
| `test_handle_tool_call_full_metadata` | _handle_tool_call path -> full args/result logged | arguments and result in TOOL_CALL event |
| `test_followup_min_from_config` | config.followup_min_remaining=1000 -> uses 1000 | Threshold is 1000, not 500 |

### PKG-LLM-GATEWAY-001 new tests (4)

| Test | Description | Expected |
|------|-------------|----------|
| `test_budget_mode_warn_allows` | warn mode, budget exceeded -> request proceeds | RouteOutcome.SUCCESS, not REJECTED |
| `test_budget_mode_warn_logs` | warn mode -> BUDGET_WARNING event in ledger | Ledger contains BUDGET_WARNING entry |
| `test_budget_mode_off_bypasses` | off mode -> budget check skipped entirely | No budget check call, request proceeds |
| `test_budget_mode_enforce_rejects` | enforce mode (default) -> budget rejected | RouteOutcome.REJECTED |

### PKG-ADMIN-001 new tests (3)

| Test | Description | Expected |
|------|-------------|----------|
| `test_budget_config_to_ho2` | New fields reach HO2Config | classify_budget, synthesize_budget, budget_mode set |
| `test_budget_mode_to_gateway` | budget_mode reaches Gateway | Gateway._budget_mode == config value |
| `test_budget_mode_to_ho1` | budget_mode reaches HO1 config | HO1 config["budget_mode"] == config value |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| HO2 Supervisor | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Degradation path :286, classify budget :153, synthesize :182 |
| HO2 Session Manager | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/session_manager.py` | add_turn() at :95 |
| HO1 Executor | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | Tool logging :197-204, budget check :206, _handle_tool_call :267 |
| LLM Gateway | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` | _check_budget :425, debit :374, __init__ :158 |
| Token Budgeter | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | check() :313, enforcement_hard_limit :141 |
| Admin main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | build_session_host_v2 :208, HO2Config construction :288 |
| Admin config | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | Budget section :113 |
| HO2 tests | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` | Test patterns |
| HO1 tests | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | Test patterns |
| Gateway tests | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` | Test patterns |
| Admin tests | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` | Test patterns |

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

# 4. Verify budget_mode=warn in config
python3 -c "import json; d=json.load(open('$TMPDIR/HOT/config/admin_config.json')); assert d['budget']['budget_mode']=='warn'; print('budget_mode=warn OK')"

# 5. E2E with real API (requires ANTHROPIC_API_KEY)
cd "$TMPDIR" && python3 -m admin.main --root "$TMPDIR" --dev
# Verification:
#   admin> hello
#     -> Verify: classify succeeds (output_json intercepted from H-25)
#     -> Verify: no budget_exhausted errors
#   admin> read the file HOT/kernel/llm_gateway.py
#     -> Verify: tool call with large result does NOT die on budget
#     -> Verify: BUDGET_WARNING may appear in logs but turn completes
#   admin> /exit
#     -> Verify: TURN_RECORDED events in ho2m for BOTH turns
#     -> Check: python3 -c "
#       from ledger_client import LedgerClient
#       lc = LedgerClient(ledger_path='$TMPDIR/HO2/ledger/ho2m.jsonl')
#       turns = [e for e in lc.read_all() if e.event_type == 'TURN_RECORDED']
#       print(f'TURN_RECORDED count: {len(turns)}')
#       assert len(turns) >= 2
#     "
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY (hashes) |
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | MODIFY |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY (hashes) |
| `llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/` | MODIFY |
| `test_llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-LLM-GATEWAY-001/` | MODIFY (hashes) |
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY |
| `admin_config.json` | `_staging/PKG-ADMIN-001/HOT/config/` | MODIFY |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (hashes) |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-LLM-GATEWAY-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_26A.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Every path persists.** No execution path may exit handle_turn() without a TURN_RECORDED event. Degradation, budget failure, quality gate reject -- all persist.
2. **No truncation without reference.** Full tool arguments and results logged. If payload is too large (>10KB), log the full content anyway -- artifact-based splitting is a future optimization, not a blocker.
3. **Budget is a policy, not a wall.** In development, budget warnings are informational. In production, budget failures are hard stops. The mode switch controls this -- same code, different config.
4. **Config drives behavior.** Zero budget literals in HO2/HO1/Gateway after this handoff. Every threshold comes from admin_config.json through the wiring chain.
5. **Consistent mode semantics.** enforce/warn/off means the same thing at every enforcement point. No partial modes where Gateway rejects but HO1 continues.
6. **Log errors explicitly.** Every tool failure, budget warning, and degradation event includes the specific error message, not just a status code.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-26A** -- Pristine memory logging + budget modes

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_26A_pristine_memory_and_budget.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` -- NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir -> run install.sh -> install YOUR changes on top -> ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_26A.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
10. Budget mode must be wired CONSISTENTLY across HO2, HO1, and Gateway. All three must respect the same mode value from admin_config.json. Test this explicitly.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the SIX logging gaps this handoff fixes? Name each with file and line number.
2. What happens today when handle_turn() hits the except block at ho2_supervisor.py:286? Why is this a problem for conversation memory?
3. What are the THREE budget modes? For each mode, what happens at (a) HO1 tool loop check, (b) Gateway pre-check?
4. Name all FOUR hardcoded budget values being moved to config. Give current file, line, and literal value for each.
5. After this handoff, where does Gateway read budget_mode from? How does it get there from admin_config.json?
6. What changes in tool call logging? What fields are added? What truncation is removed?
7. How many new tests are you adding per package? List them by name.
8. Which FOUR manifest.json files need updated hashes? Which FOUR .tar.gz archives plus CP_BOOTSTRAP need rebuilding?
9. In warn mode, what does Gateway return when budget is exceeded? How does HO1 know the call succeeded despite budget concerns?
10. After all changes, how would you verify that a degradation exception still produces a TURN_RECORDED event?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. (1) TURN_RECORDED skipped on degradation — ho2_supervisor.py:286-300. (2) Tool args truncated to 200 chars — ho1_executor.py:197. (3) Tool results truncated to 500 chars — ho1_executor.py:198. (4) Tool errors not captured — ho1_executor.py:199. (5) _handle_tool_call sparse logging — ho1_executor.py:277. (6) Budget failures produce opaque errors — ho1_executor.py:207 + Gateway check.
2. except block logs DEGRADATION event and returns TurnResult, but does NOT call self._session_mgr.add_turn(). The turn vanishes from conversation memory — no TURN_RECORDED in ho2m.jsonl, so reconstruct_session would have a gap.
3. **enforce**: (a) HO1 fails WO with budget_exhausted, (b) Gateway returns REJECTED. **warn**: (a) HO1 logs BUDGET_WARNING and continues, (b) Gateway logs warning, returns SUCCESS. **off**: (a) HO1 skips check entirely, (b) Gateway skips check entirely.
4. (1) classify_budget=2000 at ho2_supervisor.py:153. (2) synthesize_budget=16000 at HO2Config:62. (3) followup_min_remaining=500 at ho1_executor.py:207. (4) session_token_limit=200000 at admin_config.json:114 (already config, just keeping for completeness).
5. Gateway reads budget_mode from its constructor parameter. main.py:build_session_host_v2 reads budget_cfg["budget_mode"] from admin_config.json and passes it to LLMGateway(budget_mode=...).
6. Tool call logging adds: `arguments` (full dict), `result` (full dict), `tool_error` (error detail), `args_bytes`, `result_bytes`. Removes: 200-char truncation on args_summary, 500-char truncation on result_summary. _handle_tool_call path also gets full args/result.
7. HO2: 5. HO1: 7. Gateway: 4. Admin: 3. Total: 19.
8. Manifests: PKG-HO2-SUPERVISOR-001, PKG-HO1-EXECUTOR-001, PKG-LLM-GATEWAY-001, PKG-ADMIN-001. Archives: same four .tar.gz plus CP_BOOTSTRAP.tar.gz = 5 total.
9. In warn mode, Gateway returns a SUCCESS PromptResponse (not REJECTED) with the content from the provider. It logs a BUDGET_WARNING event to the ledger. HO1 sees outcome=SUCCESS and proceeds normally. The warning is visible in the ledger for forensics but doesn't block the turn.
10. Write a test that: (a) configures HO2 with a mock HO1 that raises an exception, (b) calls handle_turn(), (c) asserts that the HO2m ledger contains a TURN_RECORDED event with the degradation message, (d) asserts the returned TurnResult.response contains "[Degradation: ...]".
