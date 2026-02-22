# BUILDER_HANDOFF_23: Fix Admin Shell UX — Synthesize Response + Budget

## 1. Mission

Fix the admin shell so it works like every other LLM CLI: tools for actions, text for conversation. Currently broken in two ways: (1) synthesize responses come back as JSON in markdown fences instead of natural language, (2) tool queries fail with "Quality gate failed: output_result is empty" due to double budget debits and insufficient token budget.

Modify **PKG-HO1-EXECUTOR-001** (prompt pack + executor) and **PKG-HO2-SUPERVISOR-001** (budget + error surfacing). No new packages.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write/update tests FIRST. Every change gets test coverage.
3. **Package everything.** Modified packages get updated `manifest.json` SHA256 hashes. Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> `install.sh` -> all gates pass.
5. **No hardcoding.** Token budget of 16000 should come from HO2Config, not a magic constant.
6. **No file replacement.** These are in-package modifications, no cross-package file changes.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never with `./` prefix.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_23.md`.
9. **Full regression test.** Run ALL staged package tests. Report pass/fail.
10. **Baseline snapshot.** Include in results file.
11. **This is a hotfix.** Scope is narrow. Do NOT refactor surrounding code. Do NOT add new abstractions.

## 3. Architecture / Design

### Root Cause

```
User -> Shell -> SH-V2 -> HO2 -> synthesize WO -> HO1 -> Gateway -> Anthropic
                                    |
                                    +-- tools_allowed: ["gate_check", "read_file", "query_ledger", "list_packages"]
                                    |  (global on HO2Config -- set for EVERY synthesize WO)
                                    |
                                    +-- structured_output: None
                                    |  (disabled at ho1_executor.py:337 because tools is truthy)
                                    |
                                    +-- Prompt says: "Respond with valid JSON only"
                                    |  (no structural enforcement -- LLM wraps in markdown fences)
                                    |
                                    +-- token_budget: 4000 (double-debited -> effective ~2000)
                                       (tool loop needs 2+ LLM turns with 10k attention context)
```

### How Claude Code / Codex / Gemini CLI do it

Tools for actions, text for conversation. None ask the LLM to wrap conversational output in JSON. The response IS the text. The system wraps it in whatever internal structure it needs.

### Fix Design

Four targeted changes:

| Fix | File | What | Why |
|-----|------|------|-----|
| 1 | `PRM-SYNTHESIZE-001.txt` | Stop demanding JSON, ask for natural language | structured_output is always off when tools present |
| 2a | `ho1_executor.py` | Remove HO1 budget debit (line 159-161) | Gateway already debits -- double debit halves budget |
| 2b | `ho1_executor.py` | Strip markdown fences before json.loads | Defensive -- handles LLMs that still fence-wrap |
| 2c | `ho1_executor.py` | Check remaining budget before follow-up LLM call in tool loop | Fail fast with clear message instead of silent gateway rejection |
| 3a | `ho2_supervisor.py` | Raise synthesize token_budget 4000->16000 (from HO2Config) | Tool loops need headroom for attention context + multi-turn |
| 3b | `ho2_supervisor.py` | Surface WO error before quality gate | "output_result is empty" hides the real failure |

### Adversarial Analysis: Removing HO1 Debit

**Hurdles**: HO1 tests may assert budgeter.debit() was called. Those tests need updating.
**Not Enough**: If we only raise the budget without fixing double-debit, we waste tokens and the problem recurs at higher loads.
**Too Much**: We could redesign budget ownership entirely (single-writer pattern). Overkill for a hotfix.
**Synthesis**: Remove HO1 debit, update tests, keep Gateway as single debit source. Revisit budget architecture in a future handoff.

## 4. Implementation Steps

### Step 1: Update PRM-SYNTHESIZE-001.txt

In `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-SYNTHESIZE-001.txt`, replace lines 17-21:

**Before:**
```
Respond with valid JSON only matching this schema:
{
  "response_text": "your synthesized response string"
}

Do not include any text outside the JSON object.
```

**After:**
```
Respond with a clear, helpful answer in natural language.
Do not wrap your response in JSON or code fences.
```

### Step 2: Remove double debit in HO1

In `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`, delete lines 159-161:

```python
                # Debit budget
                if self.budgeter:
                    self._debit_budget(wo, response)
```

Keep the local cost tracking at lines 146-148 (that's for WO cost reporting, not budget debiting).

### Step 3: Add fence stripping in HO1

In `ho1_executor.py`, add method to `HO1Executor` class:

```python
def _strip_code_fences(self, content: str) -> str:
    """Strip markdown code fences (with or without language tag) if present."""
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return content
```

Replace lines 218-221 (Step 8: Set output) with:

```python
            # Step 8: Set output -- strip fences, parse JSON, fallback to text
            cleaned = self._strip_code_fences(final_content) if final_content else ""
            try:
                wo["output_result"] = json.loads(cleaned) if cleaned else {"response_text": ""}
            except (json.JSONDecodeError, TypeError):
                wo["output_result"] = {"response_text": final_content}
```

### Step 4: Add budget guard in tool loop

In `ho1_executor.py`, inside the tool loop after tool execution (around line 199), before building the follow-up request, add:

```python
                    # Check remaining budget before follow-up call
                    remaining_budget = token_budget - cost.get("total_tokens", 0)
                    if remaining_budget < 500:
                        return self._fail_wo(wo, cost, start_time, "budget_exhausted",
                            f"Only {remaining_budget} tokens remain after tool calls")
```

### Step 5: Raise synthesize token_budget in HO2

In `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py`:

**5a**: Add `synthesize_budget` field to `HO2Config` (line 59 area):
```python
    synthesize_budget: int = 16000
```

**5b**: At line 179, change:
```python
                    "token_budget": 4000,
```
To:
```python
                    "token_budget": self._config.synthesize_budget,
```

**5c**: Same change in the retry loop (line 219):
```python
                        "token_budget": 4000,
```
To:
```python
                        "token_budget": self._config.synthesize_budget,
```

### Step 6: Surface WO errors in HO2

In `ho2_supervisor.py`, after line 196 (`output_result = synth_result.get(...)`), before the quality gate call at line 197, add:

```python
            # Surface HO1 failure before quality gate
            if synth_result.get("state") == "failed" and synth_result.get("error"):
                wo_error = synth_result["error"]
                error_result = {"response_text": f"[Error: {wo_error}]", "error": wo_error}
                output_result = error_result
                synth_result["output_result"] = error_result
```

Both `output_result` (local) and `synth_result["output_result"]` (WO dict) are set so downstream reads (retry loop, chain logging) see the same value.

### Step 7: Update tests

Update `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py`:
- Remove/update any assertions that `budgeter.debit()` was called from HO1
- Add test: `test_strip_code_fences_json` -- fenced JSON -> clean JSON
- Add test: `test_strip_code_fences_with_language_tag` -- ` ```json ` variant
- Add test: `test_strip_code_fences_passthrough` -- plain text unchanged
- Add test: `test_budget_guard_in_tool_loop` -- remaining < 500 -> fail_wo

Update `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py`:
- Add test: `test_wo_error_surfaced_before_quality_gate` -- failed WO with error -> error_result set
- Add test: `test_synthesize_budget_from_config` -- verify token_budget reads from config
- Update any tests that hardcode `token_budget: 4000` to expect 16000

### Step 8: Governance cycle

1. Update `manifest.json` hashes for PKG-HO1-EXECUTOR-001 and PKG-HO2-SUPERVISOR-001
2. Delete `.DS_Store` files, rebuild archives with `pack()`
3. Rebuild `CP_BOOTSTRAP.tar.gz`
4. Clean-room install to temp dir
5. `pytest` -- all tests pass
6. Run 8/8 governance gates

## 5. Package Plan

**No new packages.** Two existing packages modified:

### PKG-HO1-EXECUTOR-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO1-EXECUTOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho1 |

Modified assets:
- `HO1/kernel/ho1_executor.py` -- remove debit, add fence strip, add budget guard
- `HO1/prompt_packs/PRM-SYNTHESIZE-001.txt` -- natural language instruction
- `HO1/tests/test_ho1_executor.py` -- updated + new tests

Dependencies: unchanged (PKG-KERNEL-001, PKG-TOKEN-BUDGETER-001, PKG-LLM-GATEWAY-001)

### PKG-HO2-SUPERVISOR-001 (modified)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO2-SUPERVISOR-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HO2/kernel/ho2_supervisor.py` -- budget from config, error surfacing
- `HO2/tests/test_ho2_supervisor.py` -- updated + new tests

Dependencies: unchanged

## 6. Test Plan

### PKG-HO1-EXECUTOR-001 new/updated tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_strip_code_fences_json` | Fenced ` ```json {"key":"val"} ``` ` -> clean JSON | Returns `{"key":"val"}` |
| `test_strip_code_fences_language_tag` | ` ```python ... ``` ` -> inner content | Returns inner content |
| `test_strip_code_fences_bare` | ` ``` ... ``` ` -> inner content | Returns inner content |
| `test_strip_code_fences_passthrough` | Plain text -> unchanged | Returns same text |
| `test_strip_code_fences_no_closing` | ` ``` no close ` -> unchanged | Returns same text (no stripping) |
| `test_no_double_debit` | Execute WO -> budgeter.debit NOT called from HO1 | Zero debit calls from executor |
| `test_budget_guard_tool_loop` | Remaining < 500 after tool call -> budget_exhausted | Returns failed WO with "budget_exhausted" |
| `test_natural_language_output_wrapped` | LLM returns plain text -> wrapped in `{"response_text": text}` | output_result has response_text key |
| `test_fenced_json_normalized` | LLM returns fenced JSON -> parsed correctly | output_result matches parsed JSON |

### PKG-HO2-SUPERVISOR-001 new/updated tests

| Test | Description | Expected |
|------|-------------|----------|
| `test_wo_error_surfaced` | synth WO fails with error -> output_result gets error | output_result contains "[Error: ...]" |
| `test_error_in_both_local_and_wo` | Failed WO -> both output_result and synth_result["output_result"] set | Both references match |
| `test_synthesize_budget_from_config` | HO2Config.synthesize_budget=16000 -> WO gets 16000 | constraints.token_budget == 16000 |
| `test_retry_budget_from_config` | Retry WO also uses config budget | retry WO constraints.token_budget == 16000 |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| HO1 executor (current) | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | Lines to modify |
| HO1 tests (current) | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | Test patterns |
| HO2 supervisor (current) | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | Lines to modify |
| HO2 tests (current) | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` | Test patterns |
| Synthesize prompt | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-SYNTHESIZE-001.txt` | File to modify |
| Gateway debit (keep) | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py:374` | Verify this is the single debit source |
| Token budgeter | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | Understand BudgetScope, debit() |
| Quality gate | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/quality_gate.py` | Unchanged -- verify it works with new error_result |
| Admin config | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | See tools_allowed list, budget config |
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
cd "$TMPDIR" && python3 -m admin.main
# Test:
#   admin> hello                          -> clean natural language
#   admin> do you always respond in JSON? -> clean natural language
#   admin> what frameworks are installed? -> tool executes, natural language response
#   admin> /exit
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `PRM-SYNTHESIZE-001.txt` | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/` | MODIFY |
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | MODIFY |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY (hashes) |
| `ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/` | MODIFY |
| `test_ho2_supervisor.py` | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/` | MODIFY |
| `manifest.json` | `_staging/PKG-HO2-SUPERVISOR-001/` | MODIFY (hashes) |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_23.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **Text for conversation, tools for actions.** Every working LLM CLI does this. Stop fighting the LLM.
2. **Single debit source.** Gateway debits budget. Nobody else. No double counting.
3. **Fail fast, fail clear.** Budget exhaustion surfaces as a typed error with remaining token count, not a generic "output_result is empty."
4. **Config over constants.** Budget values come from HO2Config, not hardcoded numbers.
5. **Defensive normalization.** Strip markdown fences even if the prompt doesn't ask for JSON. LLMs surprise you.
6. **One truth for error state.** When surfacing WO errors, set both the local variable and the WO dict. Downstream code reads from either -- both must agree.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-23** -- Fix admin shell UX: natural language responses + budget fix

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_23_admin_shell_ux_fix.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` -- NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir -> run install.sh -> install YOUR changes on top -> ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_23.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
9. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
10. This is a HOTFIX. Scope is narrow. Do NOT refactor surrounding code. Do NOT add new abstractions. Do NOT touch files outside the 7 listed in the Files Summary.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the TWO user-visible symptoms this handoff fixes? Name both.
2. What is the root cause of the JSON-wrapping symptom? (Hint: it's about tools_allowed being global)
3. Why does removing the HO1 budget debit NOT break budget tracking? What still debits?
4. What file and line contains the Gateway debit that we're keeping as the single source?
5. After this fix, what does HO1 do with plain text LLM responses (not JSON)? Which line wraps them?
6. What is the new synthesize token_budget value, and where does it come from (config field name)?
7. When HO2 surfaces a WO error, which TWO variables must BOTH be set? Why both?
8. How many new tests are you adding to HO1? To HO2? List them by name.
9. What tar format command do you use for archive rebuilds? What format do SHA256 hashes use in manifests?
10. After all changes, what three admin shell commands must work in E2E verification?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. (a) JSON in markdown fences for conversational responses, (b) "Quality gate failed: output_result is empty" for tool queries
2. tools_allowed is global on HO2Config (4 tools for ADMIN) -> every synthesize WO gets tools -> structured_output disabled at ho1_executor.py:337 -> prompt demands JSON but can't enforce it -> LLM wraps in markdown fences
3. Gateway debits at llm_gateway.py:374. HO1 local cost tracking (lines 146-148) still works for reporting but doesn't call budgeter.debit(). Single debit source = accurate budget.
4. `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py`, line 374
5. json.loads fails -> fallback at (new) line wraps in `{"response_text": final_content}`. Quality gate finds response_text -> accept.
6. 16000 tokens, from `HO2Config.synthesize_budget` field
7. `output_result` (local variable) AND `synth_result["output_result"]` (WO dict). Both must agree because downstream code (retry loop at line 233, chain logging) reads from the WO dict, not the local.
8. HO1: 9 tests (5 fence-strip, 1 no-double-debit, 1 budget-guard, 1 natural-language-wrap, 1 fenced-json-normalized). HO2: 4 tests (wo_error_surfaced, error_in_both, synthesize_budget_from_config, retry_budget_from_config).
9. `tar czf ... -C dir $(ls dir)`. SHA256 format: `sha256:<64hex>` (71 chars).
10. `admin> hello`, `admin> what frameworks are installed?`, `admin> /exit` (or any three including a greeting, a tool query, and exit)
