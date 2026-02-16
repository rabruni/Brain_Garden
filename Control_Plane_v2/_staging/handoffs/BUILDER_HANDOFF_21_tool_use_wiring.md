# BUILDER_HANDOFF_21 — Tool-Use Wiring (Validation + Governance)

## 1. Mission

Validate and govern pre-written code changes that wire tool-use through the Kitchener inner loop. The code modifications were made directly to 4 packages in `_staging/` by a previous agent who **did not follow the governance standard**. Your job is to:

1. **Verify** every code change matches the approved design (Section 3)
2. **Run the full governance cycle** using ONLY the kernel tools specified in BUILDER_HANDOFF_STANDARD.md
3. **Write RESULTS_HANDOFF_21.md** with full baseline snapshot

If any code change does NOT match the approved design, or introduces a defect, you MUST fix it before proceeding to governance.

**Packages modified:** PKG-HO2-SUPERVISOR-001, PKG-HO1-EXECUTOR-001, PKG-LLM-GATEWAY-001, PKG-ADMIN-001

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`.** Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT was partially bypassed.** Tests were written alongside code, not before. Your job is to verify the tests are correct and sufficient, not re-do DTT from scratch. If tests are missing or wrong, fix them.
3. **Package everything using kernel tools ONLY.**
   - **Hashes:** `hashing.py:compute_sha256(path)` — produces `sha256:<64hex>` (71 chars). Location: `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py`. **NEVER use `shasum`, `hashlib`, or any other method.**
   - **Archives:** `packages.py:pack(src_path, dest_path)` — deterministic tar.gz (mtime=0, uid=0, sorted, PAX). Location: `_staging/PKG-KERNEL-001/HOT/kernel/packages.py`. **NEVER use shell `tar`.**
   - **`pack()` takes `Path` objects, not strings.** Will error on `str.resolve()`.
4. **End-to-end verification.** Clean-room install: extract `CP_BOOTSTRAP.tar.gz` → `install.sh --root "$TMPDIR/INSTALL_ROOT" --dev` → all gates pass.
5. **No file replacement.** Packages must NEVER overwrite another package's files.
6. **Tar archive format:** `pack()` handles this. Do NOT use shell tar.
7. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_21.md` following the FULL template in `BUILDER_HANDOFF_STANDARD.md`. ALL sections required: Files Modified, Archives Built, Test Results, Full Regression, Gate Check, Clean-Room Verification, Baseline Snapshot.
8. **Full regression test.** Run ALL staged package tests (not just the 4 modified). Report total count, pass/fail, and whether any NEW failures were introduced.
9. **Baseline snapshot.** Package count, file_ownership rows, total tests, all gate results.
10. **Gate check.** Run `gate_check.py --all --enforce` from installed root. All gates must pass.

---

## 3. Architecture / Design (Approved Plan)

### What was wired

The Kitchener inner loop (Steps 2-3-4) works for plain text but the LLM cannot use tools. The infrastructure exists (ToolDispatcher, get_api_tools(), PromptRequest.tools, AnthropicProvider tool support) but 5 gaps prevent tool definitions from reaching the API and tool responses from flowing back.

### GAP 1: HO2 never passes tool config to WOs
- **File:** `PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py`
- **Change:** Added `tools_allowed: List[str] = field(default_factory=list)` to `HO2Config`. Passed it into synthesize and retry WO constraints. Set `turn_limit=10` when tools_allowed is non-empty. Classify WO does NOT get tools_allowed.

### GAP 2: HO1 never passes tools to Gateway
- **File:** `PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`
- **Change:** Added `_resolve_tools()` method that reads `tools_allowed` from WO constraints, calls `tool_dispatcher.get_api_tools()`, filters to allowed tool IDs. Sets `request.tools` in `_build_prompt_request()`. When tools are present, `structured_output` is set to None (tools and structured_output are mutually exclusive in Anthropic API).

### GAP 3: HO1 tool loop double-executes tools
- **File:** `PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`
- **Change:** Tool results are now cached from first execution. Follow-up prompt built from cached results instead of re-executing.

### GAP 4: Provider content format mismatch
- **File:** `PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`
- **Change:** `_extract_tool_uses()` now takes an optional `response` parameter. Checks `response.content_blocks` first (populated by AnthropicProvider with full `{type, id, name, input}` dicts). Falls back to string parsing for non-Anthropic providers.

### GAP 5: Tool logging lacks detail
- **File (HO1):** `PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`
- **Change:** TOOL_CALL events now include `args_summary` (truncated to 200 chars) and `result_summary` (truncated to 500 chars).
- **File (Gateway):** `PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py`
- **Change:** EXCHANGE metadata now includes `tools_offered` (count) and `tool_use_in_response` (bool).

### Admin wiring
- **File:** `PKG-ADMIN-001/HOT/admin/main.py`
- **Change:** `HO2Config` constructor now receives `tools_allowed=[t["tool_id"] for t in cfg_dict.get("tools", [])]`.

---

## 4. Implementation Steps

The code changes are already in `_staging/`. Your steps are: **verify, hash, pack, install, test, report.**

### Step 1: Read and verify all code changes

Read each modified file and confirm it matches the design in Section 3. Specifically verify:

| File | Verify |
|------|--------|
| `PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` | `tools_allowed` field on HO2Config. Present in synthesize + retry constraints. Absent from classify constraints. turn_limit=10 when tools present, 1 otherwise. |
| `PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | `_resolve_tools()` exists and filters by allowed set. `_build_prompt_request()` sets `request.tools`. `structured_output=None` when tools present. Tool loop caches results (no double-exec). `_extract_tool_uses()` checks content_blocks first. TOOL_CALL has args_summary + result_summary. |
| `PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` | `_write_exchange()` metadata has `tools_offered` and `tool_use_in_response`. |
| `PKG-ADMIN-001/HOT/admin/main.py` | `HO2Config()` constructor has `tools_allowed=` kwarg pulling from `cfg_dict["tools"]`. |

Read each test file and confirm coverage:

| Test File | Expected New Tests |
|-----------|-------------------|
| `PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` | 7 tests in `TestToolUseWiring` class |
| `PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | 9 tests in `TestToolUseWiring` class |
| `PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` | 2 tests in `TestToolUseObservability` class |
| `PKG-ADMIN-001/HOT/tests/test_admin.py` | 1 test in `TestToolUseWiring` class |

If any code or test is wrong/missing, fix it before proceeding.

### Step 2: Run package-local tests (fast confidence check)

Run each modified package's tests individually. All must pass before proceeding.

```bash
# HO2 Supervisor (expect 54 pass)
PYTHONPATH="$STAGING/PKG-KERNEL-001/HOT/kernel:$STAGING/PKG-KERNEL-001/HOT:$STAGING/PKG-WORK-ORDER-001/HOT/kernel:$STAGING/PKG-HO2-SUPERVISOR-001/HO2/kernel" \
  python3 -m pytest $STAGING/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py -v

# HO1 Executor (expect 59 pass)
PYTHONPATH="$STAGING/PKG-KERNEL-001/HOT/kernel:$STAGING/PKG-KERNEL-001/HOT:$STAGING/PKG-LLM-GATEWAY-001/HOT/kernel:$STAGING/PKG-TOKEN-BUDGETER-001/HOT/kernel:$STAGING/PKG-HO1-EXECUTOR-001/HO1/kernel" \
  python3 -m pytest $STAGING/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py -v

# LLM Gateway (expect 20 pass)
PYTHONPATH="$STAGING/PKG-KERNEL-001/HOT/kernel:$STAGING/PKG-KERNEL-001/HOT:$STAGING/PKG-TOKEN-BUDGETER-001/HOT/kernel:$STAGING/PKG-LLM-GATEWAY-001/HOT/kernel" \
  python3 -m pytest $STAGING/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py -v

# Admin (expect 14+ pass)
python3 -m pytest $STAGING/PKG-ADMIN-001/HOT/tests/test_admin.py -v
```

### Step 3: Update manifest SHA256 hashes

For EACH modified file in EACH package's `manifest.json`, recompute the hash using the kernel tool:

```python
import sys
from pathlib import Path

staging = Path("Control_Plane_v2/_staging")
sys.path.insert(0, str(staging / "PKG-KERNEL-001" / "HOT" / "kernel"))

from hashing import compute_sha256

# Example — do this for EVERY modified asset in each manifest:
print(compute_sha256(staging / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel" / "ho2_supervisor.py"))
# Output: sha256:<64hex>
```

**Files that need hash updates:**

| Package | Asset Path | Why |
|---------|-----------|-----|
| PKG-HO2-SUPERVISOR-001 | `HO2/kernel/ho2_supervisor.py` | Added tools_allowed |
| PKG-HO2-SUPERVISOR-001 | `HO2/tests/test_ho2_supervisor.py` | Added 7 tests |
| PKG-HO1-EXECUTOR-001 | `HO1/kernel/ho1_executor.py` | Tool wiring + bug fixes |
| PKG-HO1-EXECUTOR-001 | `HO1/tests/test_ho1_executor.py` | Added 9 tests |
| PKG-LLM-GATEWAY-001 | `HOT/kernel/llm_gateway.py` | EXCHANGE logging |
| PKG-LLM-GATEWAY-001 | `HOT/tests/test_llm_gateway.py` | Added 2 tests |
| PKG-ADMIN-001 | `HOT/admin/main.py` | tools_allowed wiring |
| PKG-ADMIN-001 | `HOT/tests/test_admin.py` | Added 1 test |

Update each `manifest.json` with the new `sha256:<64hex>` value. Only change the hash for modified files — do not touch hashes for unmodified assets.

### Step 4: Remove __pycache__ from package directories

```bash
find Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001 -type d -name __pycache__ -exec rm -rf {} +
find Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001 -type d -name __pycache__ -exec rm -rf {} +
find Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001 -type d -name __pycache__ -exec rm -rf {} +
find Control_Plane_v2/_staging/PKG-ADMIN-001 -type d -name __pycache__ -exec rm -rf {} +
```

### Step 5: Rebuild 4 package archives

Use `packages.py:pack()` — **NEVER shell tar**:

```python
import sys
from pathlib import Path

staging = Path("Control_Plane_v2/_staging")
sys.path.insert(0, str(staging / "PKG-KERNEL-001" / "HOT" / "kernel"))

from packages import pack

# Rebuild each modified package archive
for pkg_id in [
    "PKG-HO2-SUPERVISOR-001",
    "PKG-HO1-EXECUTOR-001",
    "PKG-LLM-GATEWAY-001",
    "PKG-ADMIN-001",
]:
    src = staging / pkg_id
    dest = staging / f"{pkg_id}.tar.gz"
    pack(src, dest)
    print(f"Packed {pkg_id} -> {dest}")
```

### Step 6: Rebuild CP_BOOTSTRAP.tar.gz

The CP_BOOTSTRAP archive contains all 21 packages. Rebuild it using `pack()`:

```python
from pathlib import Path
from packages import pack

staging = Path("Control_Plane_v2/_staging")
bootstrap_src = staging / "CP_BOOTSTRAP"  # directory with install.sh + all packages
bootstrap_dest = staging / "CP_BOOTSTRAP.tar.gz"
pack(bootstrap_src, bootstrap_dest)
```

**Important:** Before packing, ensure the 4 updated `.tar.gz` archives from Step 5 are copied into the CP_BOOTSTRAP directory (wherever the individual package archives live within it).

### Step 7: Clean-room install

```bash
TMPDIR=$(mktemp -d)
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
```

All 21 packages must install. All gates must pass.

### Step 8: Gate check from installed root

```bash
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 "$IR/HOT/scripts/gate_check.py" --root "$IR" --all --enforce
```

All gates must pass. If any gate fails, diagnose and fix before continuing.

### Step 9: Full regression test from installed root

```bash
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 -m pytest "$IR/HOT/tests/" "$IR/HO1/tests/" "$IR/HO2/tests/" -v
```

Expected: 468+ tests (19 new from this handoff). Report total, passed, failed. If any NEW failures (not pre-existing), fix before continuing.

### Step 10: Write RESULTS_HANDOFF_21.md

Location: `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_21.md`

Follow the FULL template from `BUILDER_HANDOFF_STANDARD.md`. ALL sections required:
- Files Modified (with before/after SHA256)
- Archives Built (with SHA256)
- Test Results — per-package and full regression
- Gate Check Results
- Clean-Room Verification
- Baseline Snapshot
- Issues Encountered
- Notes for Reviewer

---

## 5. Package Plan

No new packages. 4 existing packages modified:

| Package ID | Modified Files | Dependencies (unchanged) |
|-----------|---------------|------------------------|
| PKG-HO2-SUPERVISOR-001 | ho2_supervisor.py, test_ho2_supervisor.py | PKG-KERNEL-001, PKG-WORK-ORDER-001 |
| PKG-HO1-EXECUTOR-001 | ho1_executor.py, test_ho1_executor.py | PKG-KERNEL-001, PKG-LLM-GATEWAY-001, PKG-TOKEN-BUDGETER-001 |
| PKG-LLM-GATEWAY-001 | llm_gateway.py, test_llm_gateway.py | PKG-KERNEL-001, PKG-TOKEN-BUDGETER-001 |
| PKG-ADMIN-001 | main.py, test_admin.py | PKG-KERNEL-001, PKG-ANTHROPIC-PROVIDER-001, + 6 others |

---

## 6. Test Plan

### New tests added (19 total)

#### PKG-HO2-SUPERVISOR-001 — TestToolUseWiring (7 tests)

| Test | Validates |
|------|-----------|
| `test_ho2_config_tools_allowed_default_empty` | HO2Config().tools_allowed == [] |
| `test_ho2_config_tools_allowed_set` | HO2Config(tools_allowed=["gate_check"]).tools_allowed == ["gate_check"] |
| `test_synthesize_wo_includes_tools_allowed` | Synthesize WO constraints contain tools_allowed when set |
| `test_synthesize_wo_turn_limit_raised_with_tools` | turn_limit=10 when tools_allowed non-empty |
| `test_classify_wo_excludes_tools_allowed` | Classify WO constraints never contain tools_allowed |
| `test_retry_wo_includes_tools_allowed` | Retry WOs carry tools_allowed from config |
| `test_tools_allowed_empty_means_no_tools` | tools_allowed=[] explicit in constraints, turn_limit=1 |

#### PKG-HO1-EXECUTOR-001 — TestToolUseWiring (9 tests)

| Test | Validates |
|------|-----------|
| `test_prompt_request_includes_tools_when_allowed` | PromptRequest.tools populated from get_api_tools() |
| `test_prompt_request_no_tools_when_empty` | tools_allowed=[] → PromptRequest.tools is None |
| `test_prompt_request_no_tools_when_missing` | No tools_allowed key → PromptRequest.tools is None |
| `test_prompt_request_tools_filtered_to_allowed` | Only allowed tool IDs appear in PromptRequest.tools |
| `test_tool_loop_no_double_execution` | tool_dispatcher.execute called exactly once per tool |
| `test_tool_loop_uses_content_blocks` | Extracts tool_use from content_blocks, not content string |
| `test_tool_loop_fallback_to_string_parsing` | Falls back to string parsing when no content_blocks |
| `test_tool_call_event_has_args_summary` | TOOL_CALL metadata includes args_summary |
| `test_tool_call_event_has_result_summary` | TOOL_CALL metadata includes result_summary |

#### PKG-LLM-GATEWAY-001 — TestToolUseObservability (2 tests)

| Test | Validates |
|------|-----------|
| `test_exchange_logs_tools_offered_count` | EXCHANGE metadata includes tools_offered count |
| `test_exchange_logs_tool_use_in_response` | EXCHANGE metadata includes tool_use_in_response flag |

#### PKG-ADMIN-001 — TestToolUseWiring (1 test)

| Test | Validates |
|------|-----------|
| `test_ho2_config_receives_tool_ids` | build_session_host_v2() passes tool IDs to HO2Config |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| BUILDER_HANDOFF_STANDARD.md | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Governance rules. READ THIS FIRST. |
| compute_sha256() | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | ONLY tool for SHA256 hashes |
| pack() | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | ONLY tool for archive creation |
| install.sh | Inside CP_BOOTSTRAP.tar.gz | Bootstrap orchestrator |
| gate_check.py | `_staging/PKG-KERNEL-001/HOT/scripts/gate_check.py` | Post-install gate verification |
| admin_config.json | `_staging/PKG-ADMIN-001/HOT/config/admin_config.json` | 4 tools defined with schemas |
| tool_dispatch.py | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/tool_dispatch.py` | get_api_tools() returns Anthropic format |
| anthropic_provider.py | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py` | AnthropicResponse.content_blocks |

---

## 8. End-to-End Verification

```bash
# Set staging path
STAGING="Control_Plane_v2/_staging"

# Step 1: Package-local tests (fast check)
PYTHONPATH="$STAGING/PKG-KERNEL-001/HOT/kernel:$STAGING/PKG-KERNEL-001/HOT:$STAGING/PKG-WORK-ORDER-001/HOT/kernel:$STAGING/PKG-HO2-SUPERVISOR-001/HO2/kernel" \
  python3 -m pytest $STAGING/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py -v
# Expected: 54 passed

PYTHONPATH="$STAGING/PKG-KERNEL-001/HOT/kernel:$STAGING/PKG-KERNEL-001/HOT:$STAGING/PKG-LLM-GATEWAY-001/HOT/kernel:$STAGING/PKG-TOKEN-BUDGETER-001/HOT/kernel:$STAGING/PKG-HO1-EXECUTOR-001/HO1/kernel" \
  python3 -m pytest $STAGING/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py -v
# Expected: 59 passed

PYTHONPATH="$STAGING/PKG-KERNEL-001/HOT/kernel:$STAGING/PKG-KERNEL-001/HOT:$STAGING/PKG-TOKEN-BUDGETER-001/HOT/kernel:$STAGING/PKG-LLM-GATEWAY-001/HOT/kernel" \
  python3 -m pytest $STAGING/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py -v
# Expected: 20 passed

python3 -m pytest $STAGING/PKG-ADMIN-001/HOT/tests/test_admin.py -v
# Expected: 14+ passed

# Step 2: Clean-room install
TMPDIR=$(mktemp -d)
tar xzf $STAGING/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
# Expected: 21 packages installed, 8/8 gates pass

# Step 3: Gate check
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 "$IR/HOT/scripts/gate_check.py" --root "$IR" --all --enforce
# Expected: All gates PASS

# Step 4: Full regression from installed root
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 -m pytest "$IR/HOT/tests/" "$IR/HO1/tests/" "$IR/HO2/tests/" -v
# Expected: 487+ passed (468 baseline + 19 new), 0 failed
```

---

## 9. Files Summary

| File | Package | Action |
|------|---------|--------|
| `HO2/kernel/ho2_supervisor.py` | PKG-HO2-SUPERVISOR-001 | MODIFIED (pre-written, verify) |
| `HO2/tests/test_ho2_supervisor.py` | PKG-HO2-SUPERVISOR-001 | MODIFIED (pre-written, verify) |
| `HO1/kernel/ho1_executor.py` | PKG-HO1-EXECUTOR-001 | MODIFIED (pre-written, verify) |
| `HO1/tests/test_ho1_executor.py` | PKG-HO1-EXECUTOR-001 | MODIFIED (pre-written, verify) |
| `HOT/kernel/llm_gateway.py` | PKG-LLM-GATEWAY-001 | MODIFIED (pre-written, verify) |
| `HOT/tests/test_llm_gateway.py` | PKG-LLM-GATEWAY-001 | MODIFIED (pre-written, verify) |
| `HOT/admin/main.py` | PKG-ADMIN-001 | MODIFIED (pre-written, verify) |
| `HOT/tests/test_admin.py` | PKG-ADMIN-001 | MODIFIED (pre-written, verify) |
| `manifest.json` | PKG-HO2-SUPERVISOR-001 | UPDATE hashes (Step 3) |
| `manifest.json` | PKG-HO1-EXECUTOR-001 | UPDATE hashes (Step 3) |
| `manifest.json` | PKG-LLM-GATEWAY-001 | UPDATE hashes (Step 3) |
| `manifest.json` | PKG-ADMIN-001 | UPDATE hashes (Step 3) |
| `PKG-HO2-SUPERVISOR-001.tar.gz` | _staging/ | REBUILD with pack() (Step 5) |
| `PKG-HO1-EXECUTOR-001.tar.gz` | _staging/ | REBUILD with pack() (Step 5) |
| `PKG-LLM-GATEWAY-001.tar.gz` | _staging/ | REBUILD with pack() (Step 5) |
| `PKG-ADMIN-001.tar.gz` | _staging/ | REBUILD with pack() (Step 5) |
| `CP_BOOTSTRAP.tar.gz` | _staging/ | REBUILD with pack() (Step 6) |
| `RESULTS_HANDOFF_21.md` | _staging/handoffs/ | CREATE (Step 10) |

---

## 10. Design Principles

1. **Kernel tools are the ONLY way.** `compute_sha256()` for hashes. `pack()` for archives. No exceptions. No "just this once." The standard exists because manual methods produce wrong formats.
2. **Verify before you govern.** The code was written outside the standard. Read every change. If something is wrong, fix it. Do not rubber-stamp.
3. **Clean-room is not optional.** The installed system must work, not just the staging tree. Extract, install, gate, test — from a temp directory.
4. **Full regression catches cross-package breaks.** Run ALL staged tests, not just the 4 modified packages. 468+ tests is the baseline.
5. **The RESULTS file IS the deliverable.** Without it, the work didn't happen. Every section in the template is required.
6. **Hashes are `sha256:<64hex>` (71 chars).** Bare hex fails G0A. compute_sha256() handles this — that's why you use it.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-21** — Validate pre-written tool-use wiring code and run full governance cycle.

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_21_tool_use_wiring.md`

**Also read before answering:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. Code changes are PRE-WRITTEN. Your job is to VERIFY them against the design, then run governance.
3. Tar archive format: Use `packages.py:pack(Path, Path)` — NEVER shell `tar`. pack() takes Path objects.
4. Hash format: Use `hashing.py:compute_sha256(Path)` — produces `sha256:<64hex>` (71 chars). NEVER use shasum, hashlib, or any other method. Bare hex fails G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just the 4 modified). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_21.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Files Modified, Archives Built, Test Results, Full Regression, Gate Check, Clean-Room Verification, Baseline Snapshot. Missing sections = incomplete handoff.
8. If any pre-written code is wrong or doesn't match the design in Section 3, FIX IT before governance.
9. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz with pack() and report new SHA256.
10. The only tools for hashes and archives are in PKG-KERNEL-001/HOT/kernel/. Use them. No alternatives.

**Before writing ANY code or running ANY commands, answer these 10 questions:**

1. How many packages were modified? List their IDs.
2. What is the ONLY function you will use to compute SHA256 hashes? Where is it located? What format does it produce?
3. What is the ONLY function you will use to create tar.gz archives? Where is it located? What type do its arguments require?
4. What are the 5 gaps that the code changes address? One sentence each.
5. How many new tests were added across all 4 packages? List the count per package.
6. What is the full path where you will write the RESULTS file?
7. What command do you run for clean-room verification? What does "clean-room" mean here?
8. What is the baseline test count you expect BEFORE your changes? What count AFTER?
9. What gate checks must pass? What is the command?
10. If you find a code change that doesn't match Section 3's design, what do you do?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers (for reviewer)

1. 4 packages: PKG-HO2-SUPERVISOR-001, PKG-HO1-EXECUTOR-001, PKG-LLM-GATEWAY-001, PKG-ADMIN-001
2. `compute_sha256(path)` from `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py`. Produces `sha256:<64hex>` (71 chars).
3. `pack(src, dest)` from `_staging/PKG-KERNEL-001/HOT/kernel/packages.py`. Arguments must be `Path` objects.
4. GAP1: HO2 doesn't pass tool config to WOs. GAP2: HO1 doesn't pass tools to Gateway. GAP3: Tool loop double-executes. GAP4: Content format mismatch with extraction. GAP5: Tool logging lacks args/results.
5. 19 total: HO2=7, HO1=9, Gateway=2, Admin=1.
6. `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_21.md`
7. Extract CP_BOOTSTRAP.tar.gz to temp dir, run install.sh, verify all gates. "Clean-room" = fresh temp directory, no pre-existing state.
8. Before: 468. After: 487+ (468 + 19 new).
9. All gates via `gate_check.py --root "$IR" --all --enforce`. G0B, G1, G1-COMPLETE at minimum.
10. Fix it before proceeding to governance. Do not rubber-stamp.
