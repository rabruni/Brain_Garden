# BUILDER_CLEANUP_2: Remove V1 Packages and Consolidate LLM Gateway

## 1. Mission

Remove four obsolete packages from the bootstrap — PKG-FLOW-RUNNER-001, PKG-SESSION-HOST-001, PKG-ATTENTION-001, PKG-PROMPT-ROUTER-001 — and consolidate the LLM provider protocol into PKG-LLM-GATEWAY-001. The V2 Kitchener stack (Shell → SH-V2 → HO2 → HO1 → Gateway) is fully self-contained. The V1 fallback path in main.py is dead weight: SH-V2 already degrades to a direct Gateway call when HO2 fails. A second fallback to an entirely separate V1 stack adds no value and keeps 4 packages alive for nothing.

**Packages removed:** PKG-FLOW-RUNNER-001, PKG-SESSION-HOST-001, PKG-ATTENTION-001, PKG-PROMPT-ROUTER-001
**Packages modified:** PKG-LLM-GATEWAY-001, PKG-ANTHROPIC-PROVIDER-001, PKG-ADMIN-001, PKG-SESSION-HOST-V2-001, PKG-HO1-EXECUTOR-001
**Net result:** 24 → 20 packages in bootstrap.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`.** Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** Modified code ships as packages in `_staging/PKG-<NAME>/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → run `install.sh --root "$TMPDIR/INSTALL_ROOT" --dev` → ALL gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`). Better yet: use `packages.py:pack()`.
8. **Results file.** When finished, write `_staging/handoffs/RESULTS_CLEANUP_2.md` (see BUILDER_HANDOFF_STANDARD.md Results File section).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results. New failures you introduced are blockers. Pre-existing failures from unvalidated packages are noted but not blockers.
10. **Baseline snapshot.** Your results file must include a baseline snapshot (package count, file_ownership rows, total tests, all gate results) so the next agent can diff against it.
11. **Use kernel tools.** `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar.
12. **Hash format.** All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
13. **This is a REMOVAL + CONSOLIDATION task.** You are deleting code paths and absorbing one file (provider.py) into an existing package. You are NOT writing new features, new abstractions, or new modules. Resist scope creep.
14. **Do NOT delete the PKG-* directories from disk.** They stay in `_staging/` as historical artifacts. You are only removing their `.tar.gz` archives from `CP_BOOTSTRAP.tar.gz`.
15. **163 unit tests must still pass.** That is the current baseline. Any drop in pass count means you broke something. (The 4 removed packages' own tests no longer run — that's expected and not a regression. Subtract their counts from the total.)

---

## 3. Architecture / Design

### What's Being Removed and Why

| Package | Role | Why It's Dead |
|---------|------|---------------|
| **PKG-FLOW-RUNNER-001** | Pipeline orchestration | Explicitly killed. HO2 IS the orchestrator. Zero imports. Zero deps. Already cleaned up by CLEANUP-1 but the .tar.gz is still in bootstrap. |
| **PKG-SESSION-HOST-001** | V1 flat session loop | Replaced by PKG-SESSION-HOST-V2-001. Only consumer is `build_session_host()` in main.py. That function is the V1 fallback — being deleted. |
| **PKG-ATTENTION-001** | V1 context assembly | Absorbed into HO2 Supervisor's `attention.py`. Only consumer is PKG-SESSION-HOST-001 — dying with it. |
| **PKG-PROMPT-ROUTER-001** | LLM routing implementation | Renamed to PKG-LLM-GATEWAY-001. Gateway already has the full implementation in `llm_gateway.py` and a backward-compat `prompt_router.py` shim. The only thing Router has that Gateway doesn't is `provider.py`. Move that file, then Router is empty. |

### What's Being Consolidated

**provider.py** (currently in PKG-PROMPT-ROUTER-001) contains:
- `ProviderResponse` — frozen dataclass (response from LLM)
- `ProviderError` — exception class
- `LLMProvider` — runtime-checkable Protocol (the interface Anthropic implements)
- `MockProvider` — test fixture for testing without real LLM calls

This file is imported by:
- `llm_gateway.py` (Gateway itself) — `from provider import ProviderError`
- `anthropic_provider.py` — `from provider import ProviderError, ProviderResponse`
- Test files — `from provider import MockProvider`

**Action:** Copy `provider.py` from PKG-PROMPT-ROUTER-001 into PKG-LLM-GATEWAY-001 as a new asset. No modifications to the file content. Update the Gateway manifest to declare it. Update PKG-ANTHROPIC-PROVIDER-001's dependency from PKG-PROMPT-ROUTER-001 → PKG-LLM-GATEWAY-001.

### Dependency Graph: Before and After

**BEFORE (V1 still wired):**
```
ADMIN-001 → SESSION-HOST-001 → PROMPT-ROUTER-001 → (4 deps)
                               ATTENTION-001
         → SESSION-HOST-V2-001 → HO2-SUPERVISOR-001
                                 HO1-EXECUTOR-001
                                 LLM-GATEWAY-001 → PROMPT-ROUTER-001
         → PROMPT-ROUTER-001
         → ATTENTION-001
         → LLM-GATEWAY-001

ANTHROPIC-PROVIDER-001 → PROMPT-ROUTER-001
```

**AFTER (V1 removed):**
```
ADMIN-001 → SESSION-HOST-V2-001 → HO2-SUPERVISOR-001
                                   HO1-EXECUTOR-001
                                   LLM-GATEWAY-001
          → ANTHROPIC-PROVIDER-001
          → LLM-GATEWAY-001
          → SHELL-001

ANTHROPIC-PROVIDER-001 → LLM-GATEWAY-001

LLM-GATEWAY-001 → KERNEL-001, TOKEN-BUDGETER-001
                   (no more PROMPT-ROUTER-001 dep)
```

### Adversarial Analysis: Removing V1 Fallback

**Hurdles**: main.py's V1 fallback is the only code path that uses these 4 packages. If any file outside main.py imports from them, the removal will break. The agent must grep exhaustively before deleting. The `from prompt_router import PromptRequest` in session_host_v2.py line 78 works because LLM-GATEWAY-001 ships a `prompt_router.py` shim — that shim stays, so this import still resolves.

**Not Enough**: If we leave these packages in bootstrap, every future builder agent wastes time understanding dead code. The dependency graph stays polluted. Future cleanup gets harder as more code accumulates around the obsolete packages.

**Too Much**: We could try to also rename the prompt_router.py shim in LLM-GATEWAY-001 or refactor session_host_v2's degradation path. That's scope creep. The shim works. Leave it.

**Synthesis**: Remove the 4 packages, consolidate provider.py, delete the V1 fallback. Don't touch anything else.

---

## 4. Implementation Steps

### Step 1: Absorb provider.py into PKG-LLM-GATEWAY-001

1. Copy `PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` → `PKG-LLM-GATEWAY-001/HOT/kernel/provider.py`
2. The file content is identical — no modifications.
3. Compute SHA256 of the new file with `compute_sha256()`.
4. Add the new asset to `PKG-LLM-GATEWAY-001/manifest.json`:
   ```json
   {
     "path": "HOT/kernel/provider.py",
     "sha256": "sha256:<computed>",
     "classification": "library"
   }
   ```
5. Remove `"PKG-PROMPT-ROUTER-001"` from the Gateway's `dependencies` array.
6. Recompute all manifest asset hashes (the other files haven't changed, but verify).
7. Repack `PKG-LLM-GATEWAY-001.tar.gz` using `packages.py:pack()`.

### Step 2: Update PKG-ANTHROPIC-PROVIDER-001 dependency

1. Open `PKG-ANTHROPIC-PROVIDER-001/manifest.json`.
2. Replace `"PKG-PROMPT-ROUTER-001"` with `"PKG-LLM-GATEWAY-001"` in the `dependencies` array.
3. No code changes — `from provider import ...` still resolves because provider.py is now in LLM-GATEWAY-001 which is on sys.path.
4. Repack `PKG-ANTHROPIC-PROVIDER-001.tar.gz` using `packages.py:pack()`.

### Step 3: Simplify PKG-HO1-EXECUTOR-001 import chain

1. Open `PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`.
2. In `_build_prompt_request()`, the current try/except chain is:
   ```python
   try:
       from prompt_router import PromptRequest
   except ImportError:
       try:
           from llm_gateway import PromptRequest
       except ImportError:
           # SimpleNamespace fallback
   ```
3. Simplify to:
   ```python
   try:
       from llm_gateway import PromptRequest
   except ImportError:
       # SimpleNamespace fallback
   ```
   The `prompt_router` import path is no longer the primary — `llm_gateway` is the canonical source. The shim in LLM-GATEWAY-001 still makes `from prompt_router import PromptRequest` work, but there's no reason to try it first.
4. Recompute SHA256 of ho1_executor.py.
5. Update `PKG-HO1-EXECUTOR-001/manifest.json` with new hash.
6. Repack `PKG-HO1-EXECUTOR-001.tar.gz`.

### Step 4: Update session_host_v2.py degradation import

1. Open `PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py`.
2. Line 78: change `from prompt_router import PromptRequest` → `from llm_gateway import PromptRequest`.
3. This is the degradation path (`_degrade()` method). `PromptRequest` is defined in `llm_gateway.py`. Direct import, no shim needed.
4. Recompute SHA256, update manifest, repack.

### Step 5: Rewire PKG-ADMIN-001

This is the largest change. Three sub-steps:

#### 5a. Remove V1 import paths from `_ensure_import_paths()`

Current lines to **remove** from the `add` list:
```python
staging / "PKG-PROMPT-ROUTER-001" / "HOT" / "kernel",    # line 41
staging / "PKG-ATTENTION-001" / "HOT" / "kernel",         # line 43
staging / "PKG-SESSION-HOST-001" / "HOT" / "kernel",      # line 44
staging / "PKG-ATTENTION-001" / "HOT",                     # line 48
```

Also **remove** the module alias hack (lines 68-75):
```python
# In source-tree tests, attention modules are not yet installed into
# kernel/. Alias them so attention_service can import kernel.attention_stages.
if "kernel.attention_stages" not in sys.modules:
    try:
        mod = importlib.import_module("attention_stages")
        sys.modules["kernel.attention_stages"] = mod
    except Exception:
        pass
```

And remove the `importlib` import (line 15) if nothing else uses it. Check first.

#### 5b. Delete `build_session_host()` function entirely

Remove lines 150-191 (the entire `build_session_host()` function). This was the V1 composition function.

#### 5c. Rewrite `run_cli()` to remove V1 fallback

Current structure:
```python
def run_cli(...):
    ...
    try:
        shell = build_session_host_v2(...)
        shell.run()
        return 0
    except Exception as exc:
        output_fn(f"WARNING: V2 Kitchener loop failed ({exc}), falling back to V1")
    # V1 fallback below...
```

New structure — V2 only, no fallback to dead code:
```python
def run_cli(...):
    ...
    shell = build_session_host_v2(root, config_path, dev_mode, input_fn, output_fn)
    shell.run()
    if pristine_patch is not None:
        pristine_patch.stop()
    return 0
```

If V2 raises an exception, it propagates. That's correct — the V2 stack has its own degradation (SH-V2 → Gateway). If the entire stack can't even be *constructed*, that's a real error, not something to paper over with V1.

#### 5d. Update ADMIN manifest dependencies

Remove from `PKG-ADMIN-001/manifest.json` dependencies:
- `"PKG-SESSION-HOST-001"`
- `"PKG-ATTENTION-001"`
- `"PKG-PROMPT-ROUTER-001"`

Keep all V2 dependencies.

#### 5e. Recompute, repack

Recompute SHA256 for main.py, update manifest hashes, repack `PKG-ADMIN-001.tar.gz`.

### Step 6: Update LLM Gateway test sys.path

1. Open `PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py`.
2. Remove the sys.path line that adds `PKG-PROMPT-ROUTER-001`:
   ```python
   sys.path.insert(0, str(_staging / "PKG-PROMPT-ROUTER-001" / "HOT" / "kernel"))
   ```
   Provider.py is now in LLM-GATEWAY-001 itself, so this line is no longer needed.
3. Recompute SHA256 of the test file, update manifest, repack (already done in Step 1).

### Step 7: Rebuild CP_BOOTSTRAP.tar.gz

1. Remove 4 archives from the bootstrap build:
   - `PKG-FLOW-RUNNER-001.tar.gz`
   - `PKG-SESSION-HOST-001.tar.gz`
   - `PKG-ATTENTION-001.tar.gz`
   - `PKG-PROMPT-ROUTER-001.tar.gz`
2. Include the 5 repacked archives from Steps 1-5.
3. Keep `install.sh` and `resolve_install_order.py` from the existing bootstrap.
4. Verify: 20 package archives + install.sh + resolve_install_order.py = 22 entries.

### Step 8: Clean-room install verification

```bash
TMPDIR=$(mktemp -d)
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
```

**Expected:**
- 20 packages installed (was 24)
- 8/8 gates PASS
- `resolve_install_order.py` resolves 18 packages (20 minus GENESIS and KERNEL which are pre-installed)
- No package references a removed package as a dependency

### Step 9: Run unit tests

```bash
cd Control_Plane_v2/_staging
python3 -m pytest PKG-WORK-ORDER-001 PKG-HO1-EXECUTOR-001 \
    PKG-HO2-SUPERVISOR-001 PKG-LLM-GATEWAY-001 \
    PKG-SESSION-HOST-V2-001 PKG-SHELL-001 PKG-ADMIN-001 \
    PKG-ANTHROPIC-PROVIDER-001 PKG-TOKEN-BUDGETER-001 -v
```

The removed packages' tests (PKG-SESSION-HOST-001, PKG-ATTENTION-001, PKG-PROMPT-ROUTER-001) are no longer in scope. PKG-FLOW-RUNNER-001 had no unpacked directory.

**Accounting:**
- Previous total: 163 tests (across 6 code packages)
- Removed package tests: PKG-SESSION-HOST-001 (had tests), PKG-ATTENTION-001 (had tests), PKG-PROMPT-ROUTER-001 (had tests)
- Remaining tests: count will be reported in results. The 6 code packages (WO, HO1, HO2, GW, SH-V2, Shell) plus ADMIN and Anthropic Provider must all pass.

---

## 5. Package Plan

This handoff modifies 5 existing packages. No new packages.

### PKG-LLM-GATEWAY-001 (modified)

- **Package ID:** PKG-LLM-GATEWAY-001
- **Layer:** 3
- **spec_id:** SPEC-GATE-001
- **framework_id:** FMWK-000
- **plane_id:** hot
- **Assets** (after):
  - `HOT/kernel/llm_gateway.py` — classification: library (unchanged)
  - `HOT/kernel/prompt_router.py` — classification: library (backward-compat shim, unchanged)
  - `HOT/kernel/provider.py` — classification: library **(NEW — absorbed from PKG-PROMPT-ROUTER-001)**
  - `HOT/tests/test_llm_gateway.py` — classification: test (sys.path fix)
- **Dependencies** (after): `PKG-KERNEL-001`, `PKG-TOKEN-BUDGETER-001`
  - Removed: `PKG-PROMPT-ROUTER-001`

### PKG-ANTHROPIC-PROVIDER-001 (modified)

- **Dependencies** (after): `PKG-LLM-GATEWAY-001`
  - Changed: `PKG-PROMPT-ROUTER-001` → `PKG-LLM-GATEWAY-001`

### PKG-HO1-EXECUTOR-001 (modified)

- **Change:** Simplified import chain in `ho1_executor.py`
- **Dependencies:** unchanged (`PKG-KERNEL-001`, `PKG-LLM-GATEWAY-001`, `PKG-TOKEN-BUDGETER-001`)

### PKG-SESSION-HOST-V2-001 (modified)

- **Change:** `from prompt_router import` → `from llm_gateway import` in degradation path
- **Dependencies:** unchanged (`PKG-HO2-SUPERVISOR-001`, `PKG-HO1-EXECUTOR-001`, `PKG-LLM-GATEWAY-001`, `PKG-KERNEL-001`)

### PKG-ADMIN-001 (modified)

- **Changes:** Removed `build_session_host()`, V1 fallback, V1 import paths, attention module alias
- **Dependencies** (after): `PKG-KERNEL-001`, `PKG-ANTHROPIC-PROVIDER-001`, `PKG-WORK-ORDER-001`, `PKG-LLM-GATEWAY-001`, `PKG-HO1-EXECUTOR-001`, `PKG-HO2-SUPERVISOR-001`, `PKG-SESSION-HOST-V2-001`, `PKG-SHELL-001`
  - Removed: `PKG-SESSION-HOST-001`, `PKG-ATTENTION-001`, `PKG-PROMPT-ROUTER-001`

---

## 6. Test Plan

This is a removal task. No new source modules are created, so the test plan focuses on verifying nothing broke.

### Existing tests that must still pass

| Package | Test File | Expected |
|---------|-----------|----------|
| PKG-WORK-ORDER-001 | `HOT/tests/test_work_order.py` | All pass (unchanged) |
| PKG-HO1-EXECUTOR-001 | `HO1/tests/test_ho1_executor.py` | All pass (import simplification only) |
| PKG-HO2-SUPERVISOR-001 | `HO2/tests/test_ho2_supervisor.py` | All pass (unchanged) |
| PKG-LLM-GATEWAY-001 | `HOT/tests/test_llm_gateway.py` | All pass (sys.path fix, provider.py now local) |
| PKG-SESSION-HOST-V2-001 | `HOT/tests/test_session_host_v2.py` | All pass (import source change only) |
| PKG-SHELL-001 | `HOT/tests/test_shell.py` | All pass (unchanged) |
| PKG-ADMIN-001 | `HOT/tests/test_admin.py` | All pass (V1 paths removed, tests may need V1 references removed) |
| PKG-ANTHROPIC-PROVIDER-001 | `HOT/tests/test_anthropic_provider.py` | All pass (dependency change only) |
| PKG-TOKEN-BUDGETER-001 | `HOT/tests/test_token_budgeter.py` | All pass (unchanged) |

### Tests that should be verified manually

1. **LLM Gateway can import provider.py from its own package** — `from provider import MockProvider, ProviderError, LLMProvider` resolves without PKG-PROMPT-ROUTER-001 on sys.path.
2. **Anthropic Provider can import from provider.py** — `from provider import ProviderError, ProviderResponse` resolves through LLM-GATEWAY-001's path.
3. **HO1 Executor import chain** — `from llm_gateway import PromptRequest` succeeds as primary import.
4. **Session Host V2 degradation** — `from llm_gateway import PromptRequest` succeeds in `_degrade()`.
5. **ADMIN main.py** — `build_session_host_v2()` still constructs the full Kitchener stack without V1 imports.

### Tests that no longer run (expected)

| Package | Why |
|---------|-----|
| PKG-SESSION-HOST-001 tests | Package removed from bootstrap |
| PKG-ATTENTION-001 tests | Package removed from bootstrap |
| PKG-PROMPT-ROUTER-001 tests | Package removed from bootstrap |
| PKG-FLOW-RUNNER-001 tests | Already cleaned up, no unpacked directory |

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| provider.py (source) | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` | File being absorbed into LLM Gateway |
| LLM Gateway implementation | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` | Already imports `from provider import ProviderError` |
| LLM Gateway shim | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/prompt_router.py` | 3-line backward-compat shim — stays |
| ADMIN main.py | `_staging/PKG-ADMIN-001/HOT/admin/main.py` | V1 fallback being removed |
| Session Host V2 | `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/session_host_v2.py` | Degradation import to update |
| HO1 Executor | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | Import chain to simplify |
| HO2 attention.py | `_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/attention.py` | Confirms absorption is complete (comments say "Absorbed from attention_service.py") |
| CLEANUP-1 results | `_staging/handoffs/RESULTS_CLEANUP_1.md` | Prior cleanup of Flow Runner — confirms directory already deleted |
| BUILDER_HANDOFF_STANDARD.md | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Results file format, reviewer checklist |

---

## 8. End-to-End Verification

### Clean-room install

```bash
cd Control_Plane_v2/_staging

# 1. Extract bootstrap
TMPDIR=$(mktemp -d)
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"

# 2. Verify 20 packages
ls "$TMPDIR/packages/" | wc -l
# Expected: 20

# 3. Verify removed packages are NOT present
ls "$TMPDIR/packages/" | grep -E "(FLOW-RUNNER|SESSION-HOST-001|ATTENTION-001|PROMPT-ROUTER)"
# Expected: no output (exit code 1)

# 4. Install
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
# Expected: 20 packages, 8/8 gates PASS

# 5. Verify no removed package in install receipts
ls "$TMPDIR/INSTALL_ROOT/HOT/installed/" | grep -E "(FLOW-RUNNER|SESSION-HOST-001|ATTENTION-001|PROMPT-ROUTER)"
# Expected: no output
```

### Unit tests

```bash
cd Control_Plane_v2/_staging
python3 -m pytest PKG-WORK-ORDER-001 PKG-HO1-EXECUTOR-001 \
    PKG-HO2-SUPERVISOR-001 PKG-LLM-GATEWAY-001 \
    PKG-SESSION-HOST-V2-001 PKG-SHELL-001 PKG-ADMIN-001 \
    PKG-ANTHROPIC-PROVIDER-001 PKG-TOKEN-BUDGETER-001 -v
# Expected: all pass, zero failures
```

### Import verification

```bash
cd Control_Plane_v2/_staging
python3 -c "
import sys
sys.path.insert(0, 'PKG-LLM-GATEWAY-001/HOT/kernel')
from provider import LLMProvider, ProviderResponse, ProviderError, MockProvider
from llm_gateway import PromptRequest, LLMGateway, RouteOutcome
from prompt_router import PromptRouter  # shim still works
print('All imports resolve from LLM-GATEWAY-001 alone')
"
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `provider.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/` | COPY from PKG-PROMPT-ROUTER-001 (identical content) |
| `manifest.json` | `_staging/PKG-LLM-GATEWAY-001/` | MODIFY (add provider.py asset, remove PROMPT-ROUTER dep) |
| `test_llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/` | MODIFY (remove PROMPT-ROUTER sys.path line) |
| `PKG-LLM-GATEWAY-001.tar.gz` | `_staging/` | REBUILD |
| `manifest.json` | `_staging/PKG-ANTHROPIC-PROVIDER-001/` | MODIFY (dep change: PROMPT-ROUTER → LLM-GATEWAY) |
| `PKG-ANTHROPIC-PROVIDER-001.tar.gz` | `_staging/` | REBUILD |
| `ho1_executor.py` | `_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/` | MODIFY (simplify import chain) |
| `manifest.json` | `_staging/PKG-HO1-EXECUTOR-001/` | MODIFY (update ho1_executor.py hash) |
| `PKG-HO1-EXECUTOR-001.tar.gz` | `_staging/` | REBUILD |
| `session_host_v2.py` | `_staging/PKG-SESSION-HOST-V2-001/HOT/kernel/` | MODIFY (change import source) |
| `manifest.json` | `_staging/PKG-SESSION-HOST-V2-001/` | MODIFY (update session_host_v2.py hash) |
| `PKG-SESSION-HOST-V2-001.tar.gz` | `_staging/` | REBUILD |
| `main.py` | `_staging/PKG-ADMIN-001/HOT/admin/` | MODIFY (remove V1 fallback, V1 paths, module alias) |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (remove 3 V1 deps, update main.py hash) |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (20 packages, was 24) |

---

## 10. Design Principles

1. **Dead code is dead.** If no runtime code path reaches a package, it does not belong in the bootstrap. "Fallback" is not an argument when the fallback is to a separate architecture that nobody tests or maintains.
2. **One package, one role.** provider.py belongs in the package that uses it (LLM Gateway), not in the package it was historically created with (Prompt Router). Dependencies should point to where code lives now, not where it was born.
3. **Import from the canonical source.** `from llm_gateway import PromptRequest` is correct. `from prompt_router import PromptRequest` works (via shim) but should not be the primary import path in any file we're touching.
4. **Don't break the shim.** The `prompt_router.py` shim in LLM-GATEWAY-001 (`from llm_gateway import *; PromptRouter = LLMGateway`) stays. It's 3 lines. It prevents breakage in files we're not touching. Leave it alone.
5. **Smaller bootstrap = faster boot = fewer things to break.** 20 packages is better than 24 when the extra 4 contribute nothing.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: CLEANUP-2** — Remove 4 obsolete V1 packages from bootstrap, consolidate provider.py into LLM Gateway.

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_CLEANUP_2_v1_package_removal.md`

**Also read before answering:**
- `Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` — results file format, reviewer checklist
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py` — the V1 fallback being removed
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/manifest.json` — current Gateway manifest
- `Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` — file being absorbed

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: use `packages.py:pack()` — NEVER shell tar.
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_CLEANUP_2.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section. Missing sections = incomplete handoff.
8. Registry updates: If removing packages changes governance chains, update registry CSVs.
9. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz with 20 packages (not 24). Report member count and SHA256.
10. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar. Import path: `sys.path.insert(0, 'PKG-KERNEL-001/HOT/kernel'); sys.path.insert(0, 'PKG-KERNEL-001/HOT')`.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. Which 4 packages are you removing from CP_BOOTSTRAP.tar.gz, and why is each one dead?
2. Which file are you copying from PKG-PROMPT-ROUTER-001 into PKG-LLM-GATEWAY-001, and what 4 symbols does it export?
3. In main.py, what is the name of the V1 composition function you are deleting, and what lines does it span?
4. After removing the V1 fallback from run_cli(), what happens if build_session_host_v2() raises an exception?
5. What import line are you changing in session_host_v2.py, and in which method?
6. What import simplification are you making in ho1_executor.py's _build_prompt_request()?
7. How many packages will be in CP_BOOTSTRAP.tar.gz after your changes?
8. What dependency change are you making in PKG-ANTHROPIC-PROVIDER-001's manifest, and why?
9. What is the current unit test baseline (total tests, all pass), and what test files will no longer be in scope after removal?
10. Does the prompt_router.py shim in PKG-LLM-GATEWAY-001 get deleted or stay? Why?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

### Expected Answers (for reviewer)

1. PKG-FLOW-RUNNER-001 (dead, HO2 replaced it), PKG-SESSION-HOST-001 (superseded by V2), PKG-ATTENTION-001 (absorbed into HO2), PKG-PROMPT-ROUTER-001 (renamed to LLM Gateway, provider.py absorbed).
2. `provider.py` — exports `ProviderResponse`, `ProviderError`, `LLMProvider`, `MockProvider`.
3. `build_session_host()`, lines 150-191.
4. The exception propagates. This is correct — V2 has its own degradation (SH-V2 → Gateway). If the stack can't even be constructed, that's a real error.
5. Line 78: `from prompt_router import PromptRequest` → `from llm_gateway import PromptRequest`, in `_degrade()` method.
6. Remove the outer `try: from prompt_router import PromptRequest` — go directly to `from llm_gateway import PromptRequest` as primary.
7. 20.
8. `PKG-PROMPT-ROUTER-001` → `PKG-LLM-GATEWAY-001`, because provider.py (which Anthropic imports from) now lives in LLM Gateway.
9. 163 tests, all pass. PKG-SESSION-HOST-001, PKG-ATTENTION-001, PKG-PROMPT-ROUTER-001 test files drop out of scope.
10. Stays. It's a 3-line backward-compat shim (`from llm_gateway import *; PromptRouter = LLMGateway`). Prevents breakage in code we're not touching. No reason to delete it.
