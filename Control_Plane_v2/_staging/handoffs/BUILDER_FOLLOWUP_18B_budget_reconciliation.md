# BUILDER_FOLLOWUP_18B — Budget Reconciliation Fix

## 1. Mission

Fix the E2E dispatch failure ("Quality gate failed: response_text is empty") by reconciling the budget/max_tokens mismatch in **PKG-HO1-EXECUTOR-001**. HO1 allocates budget from `constraints.token_budget` but sends `boundary.max_tokens` to the Gateway. When the contract's max_tokens exceeds the constraint's token_budget, the Gateway rejects silently and HO1 wraps empty content as completed. Two changes: (1) cap max_tokens to available budget, (2) check response.outcome after gateway calls.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`.** Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** Modified code ships with updated manifest.json SHA256 hashes. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install via `install.sh --root --dev` → ALL gates must pass.
5. **No hardcoding.** The max_tokens cap uses `min()` of two existing config values. No new magic constants.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`.
8. **Results file.** When finished, write `_staging/handoffs/RESULTS_FOLLOWUP_18B.md`.
9. **Full regression test.** Run ALL staged package tests and report results.
10. **Baseline snapshot.** Results file must include baseline snapshot.
11. **E2E smoke test is the acceptance test.** The fix is proven when `echo "hello" | python3 main.py --root $IR --dev` returns a non-empty assistant response (not "[Quality gate failed: ...]").
12. **Only modify PKG-HO1-EXECUTOR-001.** Do not change HO2, Gateway, contracts, or budgeter. The fix belongs in HO1 because HO1 owns the bridge between budget constraints and contract boundaries.

## 3. Architecture / Design

### Root Cause

```
HO2 creates synthesize WO:
  constraints.token_budget = 4000

HO1 allocates budget:
  BudgetAllocation(token_limit=4000)       ← from constraints

HO1 builds PromptRequest:
  max_tokens = boundary.max_tokens = 4096  ← from contract PRC-SYNTHESIZE-001

Gateway budget check:
  requested_tokens = request.max_tokens = 4096
  allocation.remaining = 4000
  4096 > 4000 → BUDGET_EXHAUSTED → REJECTED → content=""

HO1 reads content="", wraps as {"response_text": ""}, marks WO "completed"
Quality gate: response_text is empty → reject
```

Classify WO works by coincidence: contract max_tokens=500 < token_budget=2000.

### Fix Design

**Change 1 — Cap max_tokens (the root cause fix):**

In `_build_prompt_request()`, compute `effective_max_tokens = min(boundary.max_tokens, constraints.token_budget)`. Use this for the PromptRequest. The Gateway will never see a request larger than the allocation.

Both code paths (PromptRequest and SimpleNamespace fallback) need this fix.

**Change 2 — Check response.outcome (defense-in-depth):**

After `gateway.route(request)` returns, check `response.outcome`. If it's REJECTED or ERROR, fail the WO explicitly with the error code and message from the response. Don't silently pass through empty content.

### Adversarial Analysis: Capping max_tokens in HO1

**Hurdles**: Minimal. One `min()` call. The two values already exist in scope. No new imports, no new config.

**Not Enough**: If we only fix the cap without the outcome check, future Gateway rejections (auth, circuit breaker, provider error) would still silently produce empty responses. Both fixes are needed.

**Too Much**: We could add budget reconciliation to HO2 or the Gateway instead. But HO1 is the bridge — it reads both the constraint and the contract. Adding logic elsewhere spreads responsibility.

**Synthesis**: Fix in HO1 only. Cap max_tokens + check outcome. Two surgical changes.

## 4. Implementation Steps

### Step 1: Write new tests (DTT)

Add these tests to `PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py`:

1. `test_max_tokens_capped_to_budget` — Create a WO with token_budget=1000 and a contract with boundary.max_tokens=4096. Execute. Verify the PromptRequest sent to the gateway has max_tokens=1000 (not 4096).

2. `test_max_tokens_uses_contract_when_budget_larger` — WO with token_budget=10000, contract max_tokens=500. Verify PromptRequest has max_tokens=500.

3. `test_gateway_rejection_fails_wo` — Mock gateway to return a PromptResponse with outcome=REJECTED, content="", error_code="BUDGET_EXHAUSTED". Execute WO. Verify WO state is "failed" (not "completed") and error contains "BUDGET_EXHAUSTED".

4. `test_gateway_error_fails_wo` — Mock gateway to return outcome=ERROR, error_code="PROVIDER_ERROR". Verify WO fails.

5. `test_gateway_success_completes_wo` — Mock gateway to return outcome=SUCCESS, content="some text". Verify WO completes normally.

### Step 2: Implement Change 1 — Cap max_tokens

In `ho1_executor.py`, method `_build_prompt_request()`:

**Before (both PromptRequest path and SimpleNamespace path):**
```python
max_tokens=boundary.get("max_tokens", 4096),
```

**After:**
```python
max_tokens=min(
    boundary.get("max_tokens", 4096),
    wo.get("constraints", {}).get("token_budget", 100000),
),
```

This requires passing `wo` to `_build_prompt_request` — it's already passed (first argument). The `constraints` dict is on the WO. No new parameters needed.

### Step 3: Implement Change 2 — Check response.outcome

In `ho1_executor.py`, method `execute()`, after line `content = getattr(response, "content", "")` (current line 163):

**Add:**
```python
# Check for gateway rejection/error
outcome = getattr(response, "outcome", None)
if outcome is not None and str(outcome) not in ("SUCCESS", "RouteOutcome.SUCCESS"):
    error_code = getattr(response, "error_code", "gateway_rejected")
    error_msg = getattr(response, "error_message", f"Gateway returned {outcome}")
    return self._fail_wo(wo, cost, start_time, str(error_code), str(error_msg))
```

Use `str(outcome)` comparison because RouteOutcome is an enum and HO1 shouldn't import Gateway internals. String comparison is duck-typing safe.

### Step 4: Update manifest hash

Recompute SHA256 of modified `ho1_executor.py` using `hashing.py:compute_sha256()`. Update the hash in `PKG-HO1-EXECUTOR-001/manifest.json`. Also update the test file hash if tests were modified.

### Step 5: Repack PKG-HO1-EXECUTOR-001.tar.gz

Use `packages.py:pack()`. Clean `__pycache__` and `.DS_Store` first.

### Step 6: Rebuild CP_BOOTSTRAP.tar.gz

Current bootstrap has 21 packages. The package list doesn't change — only the contents of PKG-HO1-EXECUTOR-001 are updated. Rebuild using the standard bootstrap assembly process.

### Step 7: Clean-room verification

```bash
TMPDIR=$(mktemp -d)
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
# Expected: 21 packages, 8/8 gates PASS
```

### Step 8: E2E smoke test

```bash
IR="$TMPDIR/INSTALL_ROOT"
echo "hello" | timeout 60 python3 "$IR/HOT/admin/main.py" --root "$IR" --dev
# Expected: Non-empty assistant response (NOT "[Quality gate failed: ...]")
# If ANTHROPIC_API_KEY is not set, provider init will fail — that's expected.
# The test passes if: no budget rejection, no empty response_text wrapping.
```

If ANTHROPIC_API_KEY is unavailable, verify with unit tests only. The budget fix is testable without a live API — mock the gateway and verify the PromptRequest max_tokens value and the outcome check behavior.

### Step 9: Write results file

Write `_staging/handoffs/RESULTS_FOLLOWUP_18B.md` with all required sections.

## 5. Package Plan

**Modified package:** PKG-HO1-EXECUTOR-001

| Field | Value |
|-------|-------|
| Package ID | PKG-HO1-EXECUTOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho1 |

**Modified assets:**

| Path | Classification | Change |
|------|---------------|--------|
| `HO1/kernel/ho1_executor.py` | library | MODIFY — add max_tokens cap + outcome check |
| `HO1/tests/test_ho1_executor.py` | test | MODIFY — add 5 new tests |

**Dependencies (unchanged):**
- PKG-KERNEL-001
- PKG-LLM-GATEWAY-001
- PKG-TOKEN-BUDGETER-001

## 6. Test Plan

### New tests (5)

| Test | Validates | Expected |
|------|-----------|----------|
| `test_max_tokens_capped_to_budget` | max_tokens = min(boundary, budget) when budget < boundary | PromptRequest.max_tokens == 1000 (not 4096) |
| `test_max_tokens_uses_contract_when_budget_larger` | max_tokens = min(boundary, budget) when boundary < budget | PromptRequest.max_tokens == 500 (not 10000) |
| `test_gateway_rejection_fails_wo` | outcome=REJECTED triggers _fail_wo | WO state="failed", error contains "BUDGET_EXHAUSTED" |
| `test_gateway_error_fails_wo` | outcome=ERROR triggers _fail_wo | WO state="failed", error contains "PROVIDER_ERROR" |
| `test_gateway_success_completes_wo` | outcome=SUCCESS proceeds normally | WO state="completed", output_result non-empty |

### Existing tests

All existing tests in `test_ho1_executor.py` must continue to pass. Current count: 35 tests. Expected after: 40 tests.

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| HO1 Executor (modify) | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | The file being changed |
| HO1 tests (modify) | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | Add new tests here |
| LLM Gateway | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` | RouteOutcome enum, PromptResponse fields — understand what HO1 receives |
| Token Budgeter | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | BudgetScope.scope_key, check() logic — understand why 4096 > 4000 fails |
| Synthesize contract | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/synthesize.json` | boundary.max_tokens = 4096 — the value that exceeds the budget |
| HO2 Supervisor | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Lines 172-182: synthesize WO with token_budget=4000 — the other value |
| Quality Gate | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/quality_gate.py` | Where "response_text is empty" originates |
| Manifest | `_staging/PKG-HO1-EXECUTOR-001/manifest.json` | Update hashes after changes |
| Hashing tool | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | compute_sha256() for manifest hashes |
| Package tool | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | pack() for archive rebuild |

## 8. End-to-End Verification

```bash
# 1. Clean-room install
TMPDIR=$(mktemp -d)
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev 2>&1 | tee "$TMPDIR/install.log"
# Expect: 21 packages installed, 8/8 gates PASS

# 2. Gate check
python3 "$TMPDIR/INSTALL_ROOT/HOT/scripts/gate_check.py" --root "$TMPDIR/INSTALL_ROOT" --all 2>&1 | tee "$TMPDIR/gates.log"
# Expect: All gates PASS

# 3. Package-local tests
python3 -m pytest Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/ -v 2>&1 | tee "$TMPDIR/ho1_tests.log"
# Expect: 40 tests, all pass

# 4. Full regression
python3 -m pytest Control_Plane_v2/_staging/PKG-WORK-ORDER-001 \
    Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001 \
    Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001 \
    Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001 \
    Control_Plane_v2/_staging/PKG-SESSION-HOST-V2-001 \
    Control_Plane_v2/_staging/PKG-SHELL-001 -v 2>&1 | tee "$TMPDIR/regression.log"
# Expect: ~170 tests, all pass, 0 new failures

# 5. E2E smoke (requires ANTHROPIC_API_KEY)
IR="$TMPDIR/INSTALL_ROOT"
echo "hello" | timeout 60 python3 "$IR/HOT/admin/main.py" --root "$IR" --dev 2>&1 | tee "$TMPDIR/e2e.log"
# Expect: "assistant: <non-empty response>" (NOT "[Quality gate failed: ...]")
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | MODIFY |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY (update hashes) |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_FOLLOWUP_18B.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

- **min() is the only reconciliation needed.** The contract says what it wants. The budget says what's allowed. Take the smaller value. No negotiation protocol, no callback, no retry logic.
- **Fail loud on rejection.** A Gateway rejection is a WO failure. Mark it failed, include the error code. Don't wrap empty content as "completed."
- **Fix in HO1 only.** HO1 owns the bridge between HO2's constraints and the contract's boundaries. Don't spread budget reconciliation across multiple packages.
- **Duck-type the outcome check.** Compare `str(outcome)` instead of importing RouteOutcome. HO1 shouldn't depend on Gateway internals. String comparison is safe for enum values.
- **Don't change HO2's budget numbers.** The mismatch is a symptom. The fix is making HO1 handle mismatches gracefully, not tweaking numbers until they happen to align.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: FOLLOWUP-18B** — Fix budget/max_tokens mismatch in HO1 Executor that causes E2E failure.

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_FOLLOWUP_18B_budget_reconciliation.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → ALL gates must pass.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_FOLLOWUP_18B.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md.
8. Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
9. CP_BOOTSTRAP.tar.gz must be rebuilt with the updated PKG-HO1-EXECUTOR-001. Report new SHA256.
10. E2E smoke test is the acceptance criterion. If ANTHROPIC_API_KEY is available, run it. If not, verify via unit tests that (a) max_tokens is capped and (b) gateway rejections fail the WO.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is the root cause of the E2E failure "Quality gate failed: response_text is empty"?
2. Which single file are you modifying (source code, not tests)?
3. What does the `min()` fix do, and which two values does it compare?
4. What does the outcome check fix do, and what WO state should result from a Gateway rejection?
5. How many new tests are you adding, and what do they cover?
6. What is the current SHA256 hash of ho1_executor.py in the manifest?
7. After modifying ho1_executor.py, how do you compute the new hash for the manifest?
8. What tar format do you use for repacking, and what must you clean first?
9. How many packages should the clean-room install report, and how many gates must pass?
10. If ANTHROPIC_API_KEY is not available, how do you verify the fix works?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. HO2 sets token_budget=4000 for synthesize WO. Contract PRC-SYNTHESIZE-001 has boundary.max_tokens=4096. HO1 allocates 4000 but sends 4096 to Gateway. Gateway checks 4096 > 4000 → BUDGET_EXHAUSTED → rejects → content="" → quality gate fails.
2. `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`
3. `min(boundary.max_tokens, constraints.token_budget)` — caps the PromptRequest max_tokens to the smaller of what the contract wants and what the budget allows. Prevents Gateway budget rejection.
4. After gateway.route(), check response.outcome. If REJECTED or ERROR, call _fail_wo() with the error_code and error_message. WO state becomes "failed" (not "completed").
5. Five new tests: max_tokens capped when budget < boundary, max_tokens uses contract when budget > boundary, gateway rejection fails WO, gateway error fails WO, gateway success completes WO.
6. `sha256:8fbfdc7323b5ccc0e563ef887eb157240b80407bc7ec5be45bdbc118ba6f4ef2` (current manifest value)
7. Using `hashing.py:compute_sha256(path)` which produces `sha256:<64hex>` format.
8. `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`. Clean `__pycache__`, `.DS_Store`, `.pyc` first.
9. 21 packages, 8/8 gates PASS.
10. Unit tests with mocked gateway. Test that PromptRequest.max_tokens is min(boundary, budget). Test that a mock response with outcome=REJECTED causes WO state="failed". No live API needed.
