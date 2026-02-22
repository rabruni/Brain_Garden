# BUILDER HANDOFF 22 — Fix Gateway Tool-Use Passthrough + E2E Verification

## 1. Mission

Fix the critical bug where `PromptResponse` (in PKG-LLM-GATEWAY-001) does not carry `content_blocks` or `finish_reason` from the provider response, rendering HO1's entire tool loop dead code in production. Then verify the full dispatch path works end-to-end with a real Anthropic API call.

**Packages modified**: PKG-LLM-GATEWAY-001 (primary fix), PKG-HO1-EXECUTOR-001 (integration test)

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`.** Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **Red-Green-Refactor per-behavior cycles.** Write one failing test, make it pass, refactor. Not batch-all-tests then batch-all-code.
3. **Package everything.** Modified code → update manifest SHA256 hashes → rebuild archives with `pack()`.
4. **E2E verification is MANDATORY.** This handoff touches the dispatch path. A real prompt must enter the system and a real response must come back via the Anthropic API. "All tests pass" is necessary but NOT sufficient.
5. **No hardcoding.** Every threshold, timeout, retry count — all config-driven.
6. **No file replacement.** Packages must NEVER overwrite another package's files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`
8. **Results file.** When finished, write `_staging/handoffs/RESULTS_HANDOFF_22.md` following the full template in BUILDER_HANDOFF_STANDARD.md.
9. **Full regression test.** Run ALL staged package tests from a clean-room installed root. Report total, pass/fail, and whether you introduced new failures.
10. **Baseline snapshot.** Your results file must include a baseline snapshot so the next agent can diff against it.
11. **Mock Boundary.** Mocks are permitted ONLY in unit tests (red-green-refactor). Integration tests must use real components. MockProvider is a red-green fixture, not an integration answer.
12. **Do NOT modify PKG-ANTHROPIC-PROVIDER-001.** The provider is correct. The bug is in the Gateway's `PromptResponse` and `route()` method.

## 3. Architecture / Design

### The Bug

The LLM Gateway wraps provider responses in `PromptResponse` before returning them to HO1. `PromptResponse` has **no `content_blocks` field** and **no `finish_reason` field**:

```python
# llm_gateway.py lines 62-82 — CURRENT (broken)
@dataclass
class PromptResponse:
    content: str
    outcome: RouteOutcome
    input_tokens: int
    output_tokens: int
    model_id: str
    provider_id: str
    latency_ms: float
    timestamp: str
    exchange_entry_id: str
    dispatch_entry_id: str = ""
    output_valid: Optional[bool] = None
    output_validation_errors: list[str] = field(default_factory=list)
    context_hash: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    cost_incurred: float = 0.0
    budget_remaining: Optional[int] = None
    # ← NO content_blocks
    # ← NO finish_reason
```

HO1's `_extract_tool_uses()` depends on both fields:

```python
# ho1_executor.py lines 338-360 — tool extraction
finish_reason = getattr(response, "finish_reason", None)    # → None (field missing)
content_blocks = getattr(response, "content_blocks", None)  # → None (field missing)
```

**Both extraction paths fail:**

1. **Primary (content_blocks)**: `None` — PromptResponse doesn't have the field.
2. **Fast signal (finish_reason)**: `None` — PromptResponse doesn't have the field.
3. **Fallback (string parse)**: When LLM calls a tool, `content = json.dumps(tool_use_parts[0].input)` — just the tool's INPUT dict (e.g., `{}`). The fallback looks for `{"type": "tool_use"}` in the parsed JSON, which isn't there.

**Result:** Tool calls from the LLM are NEVER detected. The tool loop is dead code. HO1 sees `{}` as the final content, wraps it as `{"response_text": "{}"}`, and returns. No tool is ever executed.

### Why the 19 Existing Tool-Use Tests Pass

The HANDOFF-21 tests create mock responses with `content_blocks` directly on the response object, bypassing the Gateway. They test HO1's extraction logic in isolation, not the Gateway→HO1 integration path. This is the classic mock-hides-integration-bug pattern.

### The Fix

Two changes to PKG-LLM-GATEWAY-001:

1. **Add fields to `PromptResponse`** (after line 82):
   ```python
   finish_reason: str = "stop"
   content_blocks: Optional[tuple] = None
   ```

2. **Pass them through in `route()` success path** (around line 385):
   ```python
   return PromptResponse(
       content=provider_response.content,
       ...existing fields...
       finish_reason=getattr(provider_response, "finish_reason", "stop"),
       content_blocks=getattr(provider_response, "content_blocks", None),
   )
   ```

That's it for the code fix. The rest of the tool loop (HO1's `_extract_tool_uses`, tool execution, follow-up request building) is already correct — it just never receives the data it needs.

### Adversarial Analysis: Adding Fields to PromptResponse

**Hurdles**: Every place that constructs a PromptResponse must be checked. The Gateway has multiple return paths (error, provider not found, success). Error paths should use defaults (`finish_reason="stop"`, `content_blocks=None`) since they don't have real provider responses.

**Not Enough**: Just adding the fields isn't enough. We need integration tests that prove the full Gateway→HO1→Tool path works, not just unit tests of each component. And we need E2E to prove the Anthropic API actually returns tool_use blocks that flow through correctly.

**Too Much**: We could redesign the response chain to pass the raw provider response through. That's over-engineering — the two-field addition is minimal and targeted.

**Synthesis**: Add the two fields, update the success return path, write integration tests that wire real Gateway + MockProvider, verify E2E. Minimal change, maximum confidence.

### Data Flow After Fix

```
User: "list all installed packages"
│
▼
Shell → SH-V2 → HO2.handle_turn()
│
├── Classify WO (no tools, structured_output enforced)
│   → HO1 → Gateway → Anthropic API
│   → Returns: {"speech_act": "command", "ambiguity": "low"}
│
├── Synthesize WO (tools_allowed: [gate_check, read_file, query_ledger, list_packages])
│   → HO1._build_prompt_request() → tools=[4 defs], structured_output=None
│   → Gateway → Anthropic API (tool_choice=auto)
│   → API returns: content_blocks=[{type: "tool_use", name: "list_packages", input: {}}]
│   → Gateway wraps in PromptResponse WITH content_blocks + finish_reason  ← THE FIX
│   → HO1._extract_tool_uses() finds tool_use block                       ← NOW WORKS
│   → HO1 executes list_packages via ToolDispatcher
│   → HO1 builds follow-up with tool results
│   → Gateway → Anthropic API (second call)
│   → API returns: text response with package list
│   → HO1 wraps as {"response_text": "..."}
│
├── Quality Gate → accept
│
└── Response → Shell → User
```

## 4. Implementation Steps

### Step 1: RED — Write failing test for PromptResponse fields

In `test_llm_gateway.py`, add a test that checks PromptResponse has `finish_reason` and `content_blocks` fields.

### Step 2: GREEN — Add fields to PromptResponse

Add `finish_reason: str = "stop"` and `content_blocks: Optional[tuple] = None` to the PromptResponse dataclass in `llm_gateway.py`, after line 82.

### Step 3: RED — Write failing test for route() passthrough

In `test_llm_gateway.py`, add a test that:
1. Creates a MockProvider with a response that has `finish_reason="tool_use"`
2. Calls `gateway.route()`
3. Asserts `response.finish_reason == "tool_use"`

This test should fail because route() doesn't pass finish_reason through yet.

### Step 4: GREEN — Update route() success path

In `llm_gateway.py`, in the success return path (around line 385), add:
```python
finish_reason=getattr(provider_response, "finish_reason", "stop"),
content_blocks=getattr(provider_response, "content_blocks", None),
```

### Step 5: RED — Write failing integration test for Gateway→HO1 tool extraction

In `test_ho1_executor.py`, add an integration test that:
1. Creates a real Gateway (not mocked) with a MockProvider that returns a `ProviderResponse` with `finish_reason="tool_use"` AND an `AnthropicResponse` with `content_blocks` containing a tool_use block
2. Creates a real HO1Executor with the real Gateway
3. Executes a WO with tools_allowed
4. Asserts that the tool was executed (tool_dispatcher.execute was called)

**Note**: This test uses MockProvider for the LLM call (external dependency) but real Gateway, real HO1, real ToolDispatcher, real LedgerClient, real ContractLoader. This is the integration test level — NOT an all-mock unit test.

### Step 6: GREEN — Verify the integration test passes

With the PromptResponse fix from Step 4, the integration test should pass. If it doesn't, debug the path.

### Step 7: RED — Write failing test for content_blocks passthrough

In `test_llm_gateway.py`, add a test that:
1. Creates an `AnthropicResponse` (from provider.py) with `content_blocks=({...tool_use dict...},)`
2. Registers a mock provider that returns it
3. Calls `gateway.route()`
4. Asserts `response.content_blocks` contains the tool_use dict

### Step 8: GREEN — Verify passthrough works

Should already pass from Step 4. If not, fix.

### Step 9: Refactor — Clean up any duplication in tests

### Step 10: Governance cycle

1. Compute SHA256 hashes for all modified files: `hashing.py:compute_sha256()`
2. Update `manifest.json` in PKG-LLM-GATEWAY-001 and PKG-HO1-EXECUTOR-001 (if tests modified)
3. Rebuild archives: `packages.py:pack()`
4. Rebuild CP_BOOTSTRAP.tar.gz

### Step 11: Clean-room install

```bash
TMPDIR=$(mktemp -d)
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
```

### Step 12: Gate check

```bash
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 "$IR/HOT/scripts/gate_check.py" --root "$IR" --all --enforce
```

### Step 13: Full regression test

```bash
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 -m pytest "$IR/HOT/tests/" "$IR/HO1/tests/" "$IR/HO2/tests/" -v
```

Expected: 487+ tests, 0 failures.

### Step 14: E2E smoke test — MANDATORY

**Requires**: `ANTHROPIC_API_KEY` environment variable set.

```bash
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel"

# Test 1: Basic text (no tools needed)
echo "hello" | python3 "$IR/HOT/admin/main.py" --root "$IR" --dev
# Expected: LLM responds with a greeting. No tool calls.

# Test 2: Tool use (should trigger list_packages)
echo "list all installed packages" | python3 "$IR/HOT/admin/main.py" --root "$IR" --dev
# Expected: LLM calls list_packages tool, returns actual package list.

# Test 3: Verify ledger has tool events
python3 -c "
from pathlib import Path
import json
ledger = Path('$IR/HO1/ledger/ho1m.jsonl')
if ledger.exists():
    lines = ledger.read_text().strip().split('\n')
    tool_calls = [json.loads(l) for l in lines if 'TOOL_CALL' in l]
    print(f'TOOL_CALL events: {len(tool_calls)}')
    for tc in tool_calls:
        print(f'  {tc.get(\"metadata\", {}).get(\"tool_id\", \"unknown\")}')
else:
    print('WARNING: No HO1 ledger found')
"
```

If Test 2 returns `{}` or fails to show package names, the tool loop is still broken.

### Step 15: Write RESULTS_HANDOFF_22.md

Follow the full template from BUILDER_HANDOFF_STANDARD.md.

## 5. Package Plan

### PKG-LLM-GATEWAY-001 (MODIFY)

| Field | Value |
|-------|-------|
| Package ID | PKG-LLM-GATEWAY-001 |
| Layer | 2 (KERNEL.syntactic) |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

**Files modified:**
| File | Path | Action |
|------|------|--------|
| `llm_gateway.py` | `HOT/kernel/llm_gateway.py` | MODIFY (add 2 fields to PromptResponse + pass through in route) |
| `test_llm_gateway.py` | `HOT/tests/test_llm_gateway.py` | MODIFY (add 4 passthrough tests) |
| `manifest.json` | `manifest.json` | UPDATE SHA256 hashes |

### PKG-HO1-EXECUTOR-001 (MODIFY — tests only)

| Field | Value |
|-------|-------|
| Package ID | PKG-HO1-EXECUTOR-001 |
| Layer | 3 (cognitive process) |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | ho1 |

**Files modified:**
| File | Path | Action |
|------|------|--------|
| `test_ho1_executor.py` | `HO1/tests/test_ho1_executor.py` | MODIFY (add 2 integration tests) |
| `manifest.json` | `manifest.json` | UPDATE SHA256 hashes |

## 6. Test Plan

### PKG-LLM-GATEWAY-001 tests (4 new)

| Test | Validates |
|------|-----------|
| `test_prompt_response_has_finish_reason_field` | PromptResponse dataclass has finish_reason with default "stop" |
| `test_prompt_response_has_content_blocks_field` | PromptResponse dataclass has content_blocks with default None |
| `test_route_passes_finish_reason_from_provider` | route() sets response.finish_reason from provider_response.finish_reason |
| `test_route_passes_content_blocks_from_provider` | route() sets response.content_blocks from provider_response.content_blocks (via getattr) |

### PKG-HO1-EXECUTOR-001 tests (2 new)

| Test | Validates |
|------|-----------|
| `test_tool_extraction_works_through_gateway` | End-to-end: Gateway wraps AnthropicResponse-style content_blocks in PromptResponse → HO1 extracts tool_uses → executes tool via real ToolDispatcher. Uses MockProvider for LLM but real Gateway, real HO1, real ToolDispatcher, real LedgerClient. |
| `test_tool_loop_completes_after_tool_execution` | Full loop: first LLM call returns tool_use → tool executes → second LLM call returns text → HO1 returns completed WO with response_text. Uses real Gateway. |

**Total new tests: 6**
**Existing tests (baseline): 487**
**Expected after: 493+**

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| PromptResponse dataclass | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py:62` | The dataclass to modify — add finish_reason and content_blocks |
| Gateway route() success path | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py:385` | Where to pass through the new fields |
| ProviderResponse base class | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/provider.py:16` | Has `finish_reason` field (line 26). content_blocks is only on AnthropicResponse. |
| AnthropicResponse subclass | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py:29` | Has `content_blocks: tuple = ()` — the data source |
| HO1 _extract_tool_uses() | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py:338` | Consumer of content_blocks and finish_reason — already correct |
| HO1 tool loop | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py:172` | Already correct — caches results, builds follow-up |
| Existing tool-use tests (HO2) | `_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` | Pattern reference for tool-use test setup |
| Existing tool-use tests (HO1) | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | Pattern reference — note these bypass Gateway |
| Admin tool registration | `_staging/PKG-ADMIN-001/HOT/admin/main.py:77` | Where tools get registered — 4 handlers |
| Admin config | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | 4 tools defined with schemas |
| Synthesize prompt template | `_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-SYNTHESIZE-001.txt` | The LLM prompt — requests JSON response |
| Synthesize contract | `_staging/PKG-HO1-EXECUTOR-001/HO1/contracts/synthesize.json` | boundary.structured_output — note it's nulled when tools present (line 331 of ho1_executor.py) — this is correct behavior |
| Design Philosophy | `_staging/architecture/DESIGN_PHILOSOPHY.md` | Section 8 (Build Lifecycle) defines the mock boundary and E2E mandate |
| BUILDER_HANDOFF_STANDARD.md | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Results file template, reviewer checklist |

## 8. End-to-End Verification

```bash
# 1. Clean-room install
TMPDIR=$(mktemp -d)
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev

# 2. Gate check (expect 8/8 PASS)
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 "$IR/HOT/scripts/gate_check.py" --root "$IR" --all --enforce

# 3. Full regression (expect 493+ tests, 0 failures)
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 -m pytest "$IR/HOT/tests/" "$IR/HO1/tests/" "$IR/HO2/tests/" -v

# 4. E2E smoke — text only (expect greeting response)
echo "hello" | \
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 "$IR/HOT/admin/main.py" --root "$IR" --dev

# 5. E2E smoke — tool use (expect LLM to call list_packages, return package names)
echo "list all installed packages" | \
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 "$IR/HOT/admin/main.py" --root "$IR" --dev

# 6. Verify tool events in HO1 ledger
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
python3 -c "
from pathlib import Path; import json
ledger = Path('$IR/HO1/ledger/ho1m.jsonl')
lines = ledger.read_text().strip().split('\n') if ledger.exists() else []
tool_calls = [json.loads(l) for l in lines if 'TOOL_CALL' in l]
print(f'TOOL_CALL events: {len(tool_calls)}')
for tc in tool_calls:
    print(f'  tool_id={tc.get(\"metadata\", {}).get(\"tool_id\", \"?\")}')
assert len(tool_calls) >= 1, 'FAIL: No TOOL_CALL events in ledger — tool loop is still broken'
print('PASS: Tool loop verified via ledger')
"
```

**Acceptance criteria:**
- Step 4: System responds with a greeting (not an error)
- Step 5: Response mentions actual package names (PKG-GENESIS-000, etc.)
- Step 6: At least 1 TOOL_CALL event in the HO1 ledger with tool_id=list_packages

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/` | MODIFY (add finish_reason + content_blocks to PromptResponse, pass through in route) |
| `test_llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/` | MODIFY (add 4 passthrough tests) |
| `manifest.json` | `_staging/PKG-LLM-GATEWAY-001/` | UPDATE SHA256 |
| `test_ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/tests/` | MODIFY (add 2 integration tests) |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | UPDATE SHA256 |
| `PKG-LLM-GATEWAY-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_22.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

- **Minimal change, maximum confidence.** Two fields added to one dataclass + one return statement updated. The rest of the tool loop is already correct.
- **Don't mock the boundary you're testing.** The integration tests use MockProvider for the LLM (external dependency) but real Gateway, real HO1, real ToolDispatcher, real LedgerClient. The whole point of this handoff is that mocking the Gateway hid this bug.
- **E2E is the ground truth.** All 487 tests pass with the current broken code. The only way to catch this class of bug is to send a real prompt through the real system.
- **Error paths get safe defaults.** Gateway error returns use `finish_reason="stop"` and `content_blocks=None`. Only the success path copies from the provider response.
- **content_blocks is a tuple, not a list.** AnthropicResponse uses `tuple` (frozen dataclass). PromptResponse should use `Optional[tuple]` for consistency. HO1's iteration works with either.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-22** — Fix Gateway tool-use passthrough so HO1 can detect and execute LLM tool calls.

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_22_fix_gateway_tool_passthrough.md`

**Also read (required context):**
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` — the file you're modifying
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/kernel/provider.py` — ProviderResponse base class
- `Control_Plane_v2/_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py` — AnthropicResponse with content_blocks
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` — _extract_tool_uses() consumer
- `Control_Plane_v2/_staging/architecture/DESIGN_PHILOSOPHY.md` — Section 8 (mock boundary, E2E mandate)
- `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` — results file template, governance tools

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. Red-Green-Refactor: Write one failing test → make it pass → refactor. Per-behavior cycles, not batch.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_22.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section. Missing sections = incomplete handoff.
8. Registry updates: If your package introduces new frameworks, specs, or modifies governance chain, update the corresponding registry CSVs.
9. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz and report the new SHA256.
10. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What two fields are missing from PromptResponse, and what are their types and defaults?
2. Which line(s) in llm_gateway.py's route() method need to be modified to pass these fields through?
3. Why does HO1's _extract_tool_uses() currently return an empty list for every tool_use response from the Anthropic API?
4. What is the difference between ProviderResponse.finish_reason and AnthropicResponse.content_blocks? Which base class has which field?
5. Where exactly (file, line number) does the Gateway construct the success PromptResponse that needs the new fields?
6. How many PromptResponse error-path returns exist in route()? Do they need the new fields?
7. What does the integration test in test_ho1_executor.py need to wire REAL (not mocked) to prove the fix works? What can remain a mock?
8. What are the exact E2E smoke test acceptance criteria from Section 8 of the handoff?
9. How many total tests do you expect after this handoff (baseline was 487)?
10. After modifying llm_gateway.py and test files, what is the exact sequence of governance steps before you can claim "done"?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers (for reviewer)

1. `finish_reason: str = "stop"` and `content_blocks: Optional[tuple] = None`
2. The success return around line 385-401 — add `finish_reason=getattr(provider_response, "finish_reason", "stop")` and `content_blocks=getattr(provider_response, "content_blocks", None)`
3. Because PromptResponse has no content_blocks (primary path returns None) and no finish_reason (fast signal returns None), and the fallback string parse sees the tool's INPUT dict (e.g., `{}`), not a `{"type": "tool_use"}` wrapper.
4. ProviderResponse (base) has `finish_reason: str = "stop"` at line 26. AnthropicResponse (subclass) adds `content_blocks: tuple = ()` at line 32. MockProvider returns base ProviderResponse (no content_blocks). Use `getattr` for content_blocks since it's only on the subclass.
5. `llm_gateway.py` around line 385-401, the `return PromptResponse(...)` in the success path after `# Step 11: Return`.
6. At least 2 error-path returns (provider not found ~line 276, provider error ~line 327). They should use defaults (`finish_reason="stop"`, `content_blocks=None`) since there's no real provider response.
7. Real: Gateway, HO1Executor, ToolDispatcher (with a registered handler), LedgerClient, ContractLoader. Mock: Only the LLM provider (MockProvider) — because we can't call the real Anthropic API in tests.
8. (a) `echo "hello"` returns a greeting; (b) `echo "list all installed packages"` returns actual package names; (c) HO1 ledger contains at least 1 TOOL_CALL event with tool_id=list_packages.
9. 493+ (487 baseline + 6 new: 4 Gateway + 2 HO1 integration)
10. compute_sha256 on modified files → update manifest.json → pack() archives → rebuild CP_BOOTSTRAP → clean-room install → gate_check --all --enforce → full regression pytest → E2E smoke test → write RESULTS_HANDOFF_22.md
