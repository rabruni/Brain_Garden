# BUILDER_FOLLOWUP_18A — Root Cause E2E "response_text is empty"

## 1. Mission

Root cause and fix the end-to-end failure where `admin> hello` through the full Kitchener loop (Shell → SessionHostV2 → HO2Supervisor → HO1Executor → LLMGateway → AnthropicProvider) returns **"Quality gate failed: response_text is empty"** instead of an LLM response. The bug is in the wiring between components, NOT in individual components — each tested in isolation works.

**Package(s) affected:** PKG-HO1-EXECUTOR-001, PKG-HO2-SUPERVISOR-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-ADMIN-001

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree.
2. **Root cause FIRST.** Do NOT guess. Trace the actual data flow from `admin>` input to quality gate failure. Instrument if needed.
3. **Minimal fix.** Once root cause is identified, fix the minimum necessary. Do not refactor.
4. **Revert bad changes if needed.** A prior agent added `_build_prompt_text()` to `ho1_executor.py` — this may be wrong. Evaluate it as part of root cause. If it's not needed, revert it.
5. **Package everything.** Rehash, repack any modified packages using kernel tools (`hashing.py:compute_sha256()`, `packages.py:pack()`).
6. **End-to-end verification.** The fix is only valid if `echo "hello" | python3 $IR/HOT/admin/main.py --root $IR --dev` produces a real LLM response (not a quality gate failure).
7. **Full regression.** All 163+ staged tests must still pass.
8. **Results file.** Write `_staging/RESULTS_FOLLOWUP_18A.md`.
9. **No file replacement.** No overwriting another package's files.
10. **Built-in tools.** Use `hashing.py:compute_sha256()` and `packages.py:pack()`. Never raw hashlib or shell tar.

## 3. The Bug

### Symptom

```
$ echo "hello" | python3 $IR/HOT/admin/main.py --root $IR --dev
[materialize] ...
Session started: SES-XXXXXXXX
admin> assistant: [Quality gate failed: response_text is empty]
admin> Session ended.
```

### What works in isolation

| Test | Result |
|------|--------|
| Gateway direct (dev_mode=True, budget allocated) | SUCCESS — LLM returns content |
| HO1 direct (staging paths, classify WO) | SUCCESS — `{"speech_act": "greeting"}` |
| HO1 direct (staging paths, synthesize WO) | SUCCESS — `{"response_text": "Hello!"}` |
| Unit tests (163 total across 6 packages) | ALL PASS |
| Clean-room install (24 packages, 8/8 gates) | ALL PASS |
| Full stack E2E (admin> hello) | **FAIL — "response_text is empty"** |

### Key observation

HO1 works when called directly from staging with real LLM. HO1 fails when called through the full installed stack. **The bug is in the wiring, not in HO1's logic.**

## 4. Evidence Trail

### Quality gate check (where the error surfaces)

`PKG-HO2-SUPERVISOR-001/HO2/kernel/quality_gate.py`:
- `verify()` checks `output_result.get("response_text")`
- If None → "output_result missing response_text"
- If empty string → "response_text is empty"

### HO2 dispatch chain

`PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py`:
- `handle_turn()` at line ~129: classify → attention → synthesize → verify
- Line ~194: `output_result = synth_result.get("output_result", {}) or {}`
- Line ~195-199: quality gate checks output_result

### HO1 Executor

`PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`:
- Line 141: `response = self.gateway.route(request)`
- Line 163: `content = getattr(response, "content", "")`
- Lines 197-201: wraps content into `output_result` dict

### Gateway

`PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py`:
- `route()` line 208: 10-step pipeline
- Line 228-234: Auth check — **skipped when `dev_mode=True`**
- Line 237-243: Budget check — calls `self._budgeter.check(scope)`
- Line 385-401: Success path returns `PromptResponse(content=provider_response.content, ...)`
- **Rejection paths** (auth, budget, circuit breaker, provider error) ALL return `content=""`

### Possible root causes to investigate

1. **Import path mismatch**: HO1's module-level `sys.path` setup (lines 18-25) uses `Path(__file__).resolve().parents[3]` to find staging. When installed at `$IR/HO1/kernel/ho1_executor.py`, `parents[3]` = `$IR` — but installed root has `$IR/HOT/kernel/` not `$IR/PKG-KERNEL-001/HOT/kernel/`. The `_kernel_dir` check (line 23) would fail silently, and imports might resolve to wrong versions or fail.

2. **Budget scope not allocated**: The gateway checks budget at line 237. If no scope is allocated for the WO, `check()` returns `allowed=False` → REJECTED response with `content=""`. A prior agent added `budgeter.allocate()` in HO1 (line 122-129), but: does the gateway create a scope with the SAME `scope_key`? Does `requested_tokens` differ?

3. **dev_mode propagation**: `main.py:338` passes `dev_mode` to `build_session_host_v2()`, which passes it to `LLMGateway` at line 252. Verify the flag actually reaches the gateway and auth is skipped.

4. **HO2 not passing WO correctly**: HO2's `_dispatch_wo()` calls `self._ho1.execute(wo)`. Does the WO dict have the right shape? Does `wo.constraints.prompt_contract_id` exist? Does the contract loader find the contract at the installed path?

5. **Contract loader path**: In staging, contracts are at `PKG-HO1-EXECUTOR-001/HO1/contracts/`. When installed, they're at `$IR/HO1/contracts/`. `main.py:236` creates `ContractLoader(contracts_dir=root / "HO1" / "contracts")`. Verify this resolves correctly.

6. **Gateway rejects silently**: The gateway returns a `PromptResponse` even on rejection. HO1 line 163 reads `response.content` which is `""` on rejection. HO1 then wraps `""` as `{"response_text": ""}`. **Check `response.outcome` and `response.error_code`** — HO1 currently ignores these.

## 5. What Was Already Changed (by prior agent)

The prior agent made these changes to `ho1_executor.py` (may or may not be correct):

1. **Line 337-344**: Changed `_make_budget_scope` from `SimpleNamespace` to `BudgetScope` (this fix IS valid — SimpleNamespace lacks `scope_key` property)
2. **Lines 122-129**: Added `budgeter.allocate()` before tool loop (probably valid)
3. **Lines 197-201**: Changed non-JSON wrapping key from `"raw"` to `"response_text"` (probably valid)
4. **Lines 239-265**: Added `_build_prompt_text()` method with JSON format instructions — **this is the suspect change**. The prior agent added this because the LLM returned prose instead of JSON. But the REAL question is: why did the E2E still fail even with this fix? The fix may be masking the real issue.

## 6. Debugging Strategy

### Step 1: Instrument the chain

Add temporary print/logging at these exact points and run E2E:

```python
# In ho1_executor.py execute(), after line 141:
print(f"[HO1-DEBUG] response.outcome={getattr(response, 'outcome', 'N/A')}")
print(f"[HO1-DEBUG] response.error_code={getattr(response, 'error_code', 'N/A')}")
print(f"[HO1-DEBUG] response.content[:100]={getattr(response, 'content', '')[:100]}")

# In ho2_supervisor.py _dispatch_wo(), after ho1.execute():
print(f"[HO2-DEBUG] wo_result.state={wo_result.get('state')}")
print(f"[HO2-DEBUG] wo_result.output_result={wo_result.get('output_result')}")
print(f"[HO2-DEBUG] wo_result.error={wo_result.get('error')}")
```

### Step 2: Check what `response.outcome` is

If `outcome` is `REJECTED` — the gateway rejected the request. Check `error_code` to find out why (AUTH_ERROR, BUDGET_EXHAUSTED, CIRCUIT_OPEN, INVALID_INPUT).

If `outcome` is `SUCCESS` — the LLM was called. Then the problem is in how HO1 parses the response.

If `outcome` is `ERROR` — provider threw an exception.

### Step 3: Fix the actual root cause

Based on Step 2, fix the minimal code needed.

### Step 4: Remove instrumentation, retest

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| HO1 Executor | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | Primary suspect |
| HO2 Supervisor | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Dispatch chain |
| Quality Gate | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/quality_gate.py` | Where error surfaces |
| LLM Gateway | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` | Route pipeline |
| Session Host V2 | `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py` | SH → HO2 bridge |
| Shell | `_staging/PKG-SHELL-001/HOT/kernel/shell.py` | Entry point |
| Admin main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py:194-311` | V2 DI wiring |
| Token Budgeter | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | BudgetScope, check(), allocate() |
| Contract Loader | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/contract_loader.py` | Contract loading |
| Contracts | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/*.json` | classify, synthesize, execute |
| Anthropic Provider | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py` | LLM provider |
| Provider protocol | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` | ProviderResponse dataclass |

## 8. End-to-End Verification

```bash
# 1. Rebuild modified package(s)
cd Control_Plane_v2/_staging
python3 -c "
import sys; from pathlib import Path
sys.path.insert(0, 'PKG-KERNEL-001/HOT/kernel')
sys.path.insert(0, 'PKG-KERNEL-001/HOT')
from hashing import compute_sha256; from packages import pack
# ... rehash manifest, pack archive
"

# 2. Rebuild CP_BOOTSTRAP.tar.gz (24 packages in packages/ subdir)
# 3. Clean-room install
TMPDIR=$(mktemp -d)
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
# Expected: 24 packages, 8/8 gates PASS

# 4. E2E smoke test
echo "hello" | python3 "$TMPDIR/INSTALL_ROOT/HOT/admin/main.py" \
    --root "$TMPDIR/INSTALL_ROOT" --dev
# Expected: real LLM response (NOT "Quality gate failed")

# 5. Full regression
python3 -m pytest PKG-WORK-ORDER-001 PKG-HO1-EXECUTOR-001 \
    PKG-HO2-SUPERVISOR-001 PKG-LLM-GATEWAY-001 \
    PKG-SESSION-HOST-V2-001 PKG-SHELL-001 -v
# Expected: 163+ tests, 0 failures
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | MODIFY (fix root cause) |
| Possibly others | TBD based on root cause | MODIFY |
| `RESULTS_FOLLOWUP_18A.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

- **Trace before fix.** The bug is in the wiring between components. Instrument to see actual data flowing through the chain.
- **Check response.outcome.** HO1 currently ignores gateway rejection signals. If the gateway rejects, HO1 should fail the WO with the gateway's error, not silently produce empty output.
- **Minimal change.** The 6 packages are tested and passing. Don't restructure — find the wire that's loose.
- **Isolation test vs integration test.** HO1 works in isolation. The bug only manifests in the full stack. Focus on what's different between the two environments.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: FOLLOWUP-18A** — Root cause and fix E2E "response_text is empty" failure

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_FOLLOWUP_18A_e2e_root_cause.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. Root cause FIRST. Instrument the chain, trace actual data flow. Do NOT guess.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz → install.sh → ALL gates must pass. echo "hello" must produce a real response.
6. Full regression: Run ALL staged package tests. Report total count, pass/fail.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_FOLLOWUP_18A.md` following BUILDER_HANDOFF_STANDARD.md template.
8. Minimal fix. Do not refactor, restructure, or "improve" beyond the root cause.
9. If prior changes to ho1_executor.py (_build_prompt_text, budget allocate, response_text key) are wrong, revert them.
10. Built-in tools: Use `hashing.py:compute_sha256()` for hashes and `packages.py:pack()` for archives. NEVER use raw hashlib or shell tar.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is the exact symptom? What message does the user see, and which component produces it?
2. What is the data flow path from user input "hello" to the quality gate failure? Name every component in order.
3. The bug only manifests in the full stack, not in isolation. What are 3 things that differ between "HO1 tested directly from staging" and "HO1 called through admin> from install root"?
4. What does `PromptResponse.outcome` tell you, and where should you check it?
5. The gateway has 4 rejection paths (auth, budget, circuit breaker, provider error). For each: what `error_code` would you see, and which is most likely given `--dev` mode?
6. Where does the `ContractLoader` look for contracts when running from the install root? What path does `main.py:236` resolve to?
7. What file format and tool must you use for manifest hashes and archive creation?
8. A prior agent added `_build_prompt_text()` to ho1_executor.py. What does it do, and how would you determine if it's the right fix or a wrong-headed workaround?
9. After your fix, what is the E2E command to verify success, and what output proves it worked?
10. HO1 currently ignores `response.outcome` after calling `gateway.route()`. Is this a problem? What should happen if outcome is REJECTED?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. User sees `"assistant: [Quality gate failed: response_text is empty]"`. Produced by `quality_gate.py:verify()` in PKG-HO2-SUPERVISOR-001 when `output_result.response_text` is empty.
2. Shell.run() → SessionHostV2.handle_turn() → HO2Supervisor.handle_turn() → [classify WO → HO1.execute() → Gateway.route()] → [synthesize WO → HO1.execute() → Gateway.route()] → quality_gate.verify() → FAIL
3. Three differences: (a) import paths — staging uses PKG-* dirs, install root uses HOT/HO1/HO2 dirs; (b) contract loader path — staging vs install root; (c) sys.path setup — main.py's `_ensure_import_paths` vs ho1_executor.py's module-level path hacking
4. `PromptResponse.outcome` is a `RouteOutcome` enum: SUCCESS, REJECTED, TIMEOUT, ERROR. Check it at ho1_executor.py line 163 (after gateway.route returns). Currently HO1 only reads `.content` and ignores outcome.
5. AUTH_ERROR (skipped in dev_mode), BUDGET_EXHAUSTED (most likely — gateway checks budget independently), CIRCUIT_OPEN (unlikely on first call), PROVIDER_NOT_FOUND or PROVIDER_ERROR (if provider not registered). Budget is most likely.
6. `main.py:236`: `ContractLoader(contracts_dir=root / "HO1" / "contracts")`. With `root=$INSTALL_ROOT`, this becomes `$INSTALL_ROOT/HO1/contracts/`. The contracts are installed there by package_install.py from PKG-HO1-EXECUTOR-001.
7. `sha256:<64hex>` format via `hashing.py:compute_sha256()`. Archives via `packages.py:pack()` (deterministic: mtime=0, uid=0, sorted, PAX format).
8. `_build_prompt_text()` adds JSON format instructions to the prompt so the LLM knows to respond in JSON. To determine if it's right: check whether the E2E failure is caused by the LLM returning prose (prompt problem) or by the gateway not calling the LLM at all (wiring problem). If `response.outcome` is REJECTED, the prompt fix is irrelevant.
9. `echo "hello" | python3 $IR/HOT/admin/main.py --root $IR --dev`. Success = a natural language response from the LLM (e.g., "Hello! How can I help you?"), NOT "Quality gate failed".
10. Yes, it's a problem. If outcome is REJECTED, HO1 should fail the WO with the gateway's error_code/error_message, not silently pass through empty content. This would make debugging much easier.

### Common Mistakes

1. **Testing only from staging, not from install root.** The bug is in the installed stack. Always test from a clean-room install.
2. **Fixing symptoms instead of root cause.** Adding prompt instructions doesn't help if the gateway is rejecting the request.
3. **Not checking response.outcome.** The gateway returns rich error info. Don't ignore it.
4. **Forgetting pristine patch.** Temp ledger files outside governed root need `patch("kernel.pristine.assert_append_only", return_value=None)`.
5. **Bundling multiple fixes.** Fix one thing at a time. Verify after each change.
