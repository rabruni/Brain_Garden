# BUILDER_HANDOFF_24: Staging Test Cleanup — Zero Pre-Existing Failures

## 1. Mission

Fix 26 pre-existing test failures in the staging regression suite. These failures are caused by test files using hardcoded path resolution that breaks when tests run from `_staging/PKG-*/` directories instead of the installed root. Apply the dual-context detection pattern (from HANDOFF-20) to 5 package test files + fix 1 non-package test file. Also exclude the deprecated V1 PKG-SESSION-HOST-001 from regression scope. **Test-only changes — no production code modified.**

Modifies test files in: **PKG-LAYOUT-001**, **PKG-SPEC-CONFORMANCE-001**, **PKG-VOCABULARY-001**, **PKG-FRAMEWORK-WIRING-001**, **PKG-LLM-GATEWAY-001**, plus the non-package `_staging/tests/test_bootstrap_sequence.py`.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Verify each test file's failures BEFORE fixing, confirm they pass AFTER.
3. **Package everything.** Updated test files require `manifest.json` hash updates. Use `compute_sha256()` and `pack()`.
4. **End-to-end verification.** Clean-room install → all gates pass. PLUS: full staging regression shows 0 new failures.
5. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`.
6. **Results file.** `_staging/handoffs/RESULTS_HANDOFF_24.md`.
7. **Full regression.** ALL staged tests. The GOAL of this handoff is 0 failures in staging regression (excluding PKG-ATTENTION-001 and PKG-SESSION-HOST-001).
8. **Baseline:** 23 packages, 807+ installed tests, 8/8 gates (from RESULTS_HANDOFF_31C.md).
9. **Test-only changes.** Do NOT modify production code (kernel files, supervisors, executors, etc.). Only test files and manifests.
10. **One pattern.** All fixes use the same dual-context detection pattern. Do not invent a new approach.
11. **Precedent**: HANDOFF-20 set the pattern for multi-package test cleanup. This handoff follows the same structure.

## 3. Architecture / Design

### Root Cause

Tests in 5 packages use hardcoded `Path(__file__).parents[N]` to find the project root. This works in the installed root (where all packages merge into `HOT/`, `HO1/`, `HO2/`) but fails in staging (where packages are isolated in `_staging/PKG-*/` directories).

Additionally, `_staging/tests/test_bootstrap_sequence.py` has a doubled-path bug, and PKG-SESSION-HOST-001 is a V1 relic importing the dead PKG-PROMPT-ROUTER-001.

### The Dual-Context Detection Pattern (from HANDOFF-20)

```python
_HERE = Path(__file__).resolve().parent     # .../tests/
_HOT  = _HERE.parent                        # .../HOT/

if (_HOT / "kernel" / "ledger_client.py").exists():
    # ── Installed layout: all packages merged under HOT/ ──
    CP_ROOT = _HOT.parent
    _paths = [_HOT / "kernel", _HOT, _HOT / "scripts"]
else:
    # ── Staging layout: sibling packages under _staging/ ──
    _STAGING = _HERE.parents[2]             # 3 levels: tests → HOT → PKG-* → _staging
    CP_ROOT = _STAGING.parent               # Control_Plane_v2/
    _paths = [
        _STAGING / "PKG-KERNEL-001" / "HOT" / "kernel",
        _STAGING / "PKG-KERNEL-001" / "HOT",
        # ... other sibling package paths as needed
    ]

for _p in _paths:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
```

**Why `ledger_client.py`?** It's from PKG-KERNEL-001 and only exists under `HOT/kernel/` in the installed root. In staging, each package's `HOT/` directory only has its OWN files — no cross-package files. This makes it an unambiguous probe (confirmed in HANDOFF-20, documented in MEMORY.md).

### Failure Breakdown (26 total)

| Cluster | Tests | Package | Root Cause |
|---------|-------|---------|------------|
| HO3 tier layout | 6 | PKG-LAYOUT-001 | `CP_ROOT` wrong → can't find layout.json tiers, can't import kernel.* |
| Governance baselines | 7 | PKG-SPEC-CONFORMANCE-001 | `CP_ROOT` wrong → `SPEC_PACKS`, schemas, frameworks all point to wrong dirs |
| Registry/bootstrap paths | 9 | PKG-VOCABULARY-001 + test_bootstrap_sequence | Doubled `_staging/_staging/` path + can't import `scripts.gate_check` |
| Framework count | 1 | PKG-FRAMEWORK-WIRING-001 | `HOT_ROOT` wrong → framework glob empty; also expects 5 frameworks but 6 exist |
| Import shim | 1 | PKG-LLM-GATEWAY-001 | Staging paths hardcoded to `parents[3]`, breaks in installed context |
| V1 session host | 2 | PKG-SESSION-HOST-001 | Imports dead PKG-PROMPT-ROUTER-001 → ImportError |
| **Total** | **26** | | |

### Special Cases

**test_bootstrap_sequence.py** (9 failures): This is a non-package test at `_staging/tests/test_bootstrap_sequence.py`. Line 23-24:
```python
STAGING = Path(__file__).resolve().parent.parent  # Actually resolves to _staging/, not Control_Plane_v2/
STAGING_DIR = STAGING / "_staging"                 # Becomes _staging/_staging/ — DOUBLED
```
The comment is wrong. `parent.parent` from `_staging/tests/` = `_staging/`, not `Control_Plane_v2/`. Fix: `STAGING_DIR = Path(__file__).resolve().parent.parent` directly (it's already `_staging/`).

**PKG-FRAMEWORK-WIRING-001** (1 failure): `test_exactly_five_frameworks` asserts 5 frameworks but PKG-ATTENTION-001 ships FMWK-004, making 6. After fixing path resolution so the glob actually finds frameworks, update the expected list to include FMWK-004:
```python
assert "FMWK-004" in fmwk_ids or len(fmwk_ids) == 5  # Accept either 5 or 6
```
Or update the expected list to 6 frameworks. The test documents REALITY, not a wish.

**PKG-SESSION-HOST-001** (2 failures): V1 package, superseded by PKG-SESSION-HOST-V2-001. Imports `PKG-PROMPT-ROUTER-001` which was removed in CLEANUP-2. Do NOT fix — add to the `--ignore` list for staging regression alongside PKG-ATTENTION-001.

### Adversarial Analysis: Multi-Package Test Cleanup

**Hurdles**: 5 packages modified = 5 manifests, 5 archives, 1 bootstrap rebuild. That's a lot of governance churn for test-only changes.
**Not Enough**: Only fixing 1-2 packages leaves the rest noisy. Every future handoff still reports "N pre-existing failures." Signal-to-noise stays bad.
**Too Much**: Refactoring all test infrastructure to use a shared conftest.py or test fixture. Over-engineering for a path resolution fix.
**Synthesis**: Apply the same 10-line pattern to all 5 files in one pass. Yes, it's 5 governance cycles, but the pattern is identical and mechanical. HANDOFF-20 set this precedent successfully.

## 4. Implementation Steps

### Step 1: Verify current failures

Run the staging regression and confirm exactly 26 failures across the 6 clusters listed above:
```bash
python3 -m pytest Control_Plane_v2/_staging/ -q --import-mode=importlib \
  --ignore=Control_Plane_v2/_staging/PKG-ATTENTION-001 --tb=line
```

### Step 2: Fix test_bootstrap_sequence.py (9 failures)

File: `_staging/tests/test_bootstrap_sequence.py`

Replace lines 22-24:
```python
# Paths relative to the repo
STAGING = Path(__file__).resolve().parent.parent  # _staging/..  → Control_Plane_v2
STAGING_DIR = STAGING / "_staging"
```
With:
```python
# _staging/ is the direct parent of tests/
STAGING_DIR = Path(__file__).resolve().parent.parent
```

Then update all references from `STAGING` to `STAGING_DIR` where needed (check for uses of the old `STAGING` variable).

### Step 3: Fix PKG-LAYOUT-001 test_layout.py (6 failures)

File: `_staging/PKG-LAYOUT-001/HOT/tests/test_layout.py`

Replace the path resolution block (approx lines 20-23) with the dual-context pattern. Staging branch needs:
```python
_STAGING / "PKG-KERNEL-001" / "HOT" / "kernel"   # for kernel.* imports
_STAGING / "PKG-KERNEL-001" / "HOT"               # for scripts.*
_STAGING / "PKG-LAYOUT-001" / "HOT"               # for own modules
_STAGING / "PKG-LAYOUT-002" / "HOT"               # if layout.json is in PKG-LAYOUT-002
```

Ensure `HOT_ROOT` in staging points to the correct location for framework/config/schema globs. If tests glob `HOT_ROOT / "config" / "layout.json"`, in staging `HOT_ROOT` must point to the package's own `HOT/` directory where layout.json lives.

### Step 4: Fix PKG-SPEC-CONFORMANCE-001 test_spec_conformance.py (7 failures)

File: `_staging/PKG-SPEC-CONFORMANCE-001/HOT/tests/test_spec_conformance.py`

Replace path resolution with dual-context pattern. The critical variables are:
- `CP_ROOT` — must resolve to `Control_Plane_v2/` (installed) or allow staging-aware paths
- `SPEC_PACKS` — must find `HOT/spec_packs/` in the installed root
- `HOT_ROOT` — for schema and framework globs

In staging, `SPEC_PACKS` and schema/framework directories don't exist in individual packages. Tests that glob for governance artifacts must either:
1. Point to the installed root's HOT/ (if accessible), or
2. Skip with `pytest.mark.skipif` when running in staging context (these tests validate the INSTALLED system, not staging layout)

Recommended: Use `pytest.mark.skipif(not (_HOT / "kernel" / "ledger_client.py").exists(), reason="installed-root-only test")` for tests that require merged governance artifacts.

### Step 5: Fix PKG-VOCABULARY-001 test_vocabulary.py (2-3 failures)

File: `_staging/PKG-VOCABULARY-001/HOT/tests/test_vocabulary.py`

Replace path resolution with dual-context pattern. Staging branch needs:
```python
_STAGING / "PKG-KERNEL-001" / "HOT" / "kernel"   # for kernel.* imports
_STAGING / "PKG-KERNEL-001" / "HOT"               # for scripts.gate_check
```

`CP_ROOT` must resolve correctly so `check_g1_chain(CP_ROOT)` finds `HOT/registries/specs_registry.csv`. In staging, skip G1 chain tests if registries aren't accessible (they require an installed/merged root):
```python
@pytest.mark.skipif(not _INSTALLED, reason="G1 chain requires installed root")
```

### Step 6: Fix PKG-FRAMEWORK-WIRING-001 test_framework_wiring.py (1 failure)

File: `_staging/PKG-FRAMEWORK-WIRING-001/HOT/tests/test_framework_wiring.py`

Two changes:
1. **Path fix:** Replace path resolution with dual-context pattern. `HOT_ROOT` must point to the location where framework directories (`FMWK-*/`) are installed.
2. **Framework count fix:** Update `test_exactly_five_frameworks` to expect 6 frameworks (add FMWK-004 to the expected list). PKG-ATTENTION-001 ships FMWK-004 and is in the bootstrap.

In staging, framework dirs may not be accessible. Apply same skip pattern as Step 5 for glob-dependent tests.

### Step 7: Fix PKG-LLM-GATEWAY-001 test_llm_gateway.py (1 failure)

File: `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py`

Replace the hardcoded `parents[3]` resolution with the dual-context pattern. Currently works in staging but breaks in installed. The fix makes it work in BOTH contexts.

### Step 8: Exclude PKG-SESSION-HOST-001 from regression

Do NOT modify PKG-SESSION-HOST-001. It's V1 deprecated and imports dead PKG-PROMPT-ROUTER-001. Add it to the standard `--ignore` list in regression commands:
```bash
python3 -m pytest Control_Plane_v2/_staging/ -q --import-mode=importlib \
  --ignore=Control_Plane_v2/_staging/PKG-ATTENTION-001 \
  --ignore=Control_Plane_v2/_staging/PKG-SESSION-HOST-001 \
  --ignore=Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001
```

### Step 9: Governance cycle (5 packages)

For each of the 5 modified packages:
1. Delete `.DS_Store` files
2. Update `manifest.json` SHA256 hashes for modified test files using `compute_sha256()`
3. Rebuild package archive using `pack()`

Then rebuild `CP_BOOTSTRAP.tar.gz`.

### Step 10: Verification

1. **Staging regression:** Run with updated `--ignore` list. Target: **0 failures** (excluding ignored V1 packages).
2. **Clean-room install:** Extract CP_BOOTSTRAP → install.sh → pytest → gates.
3. **Clean-room regression:** All installed tests pass (1 pre-existing failure in `test_exactly_five_frameworks` is now FIXED — expect 0 or 1 depending on FMWK-004 handling).

## 5. Package Plan

### PKG-LAYOUT-001 (modified — test file only)

| Field | Value |
|-------|-------|
| Package ID | PKG-LAYOUT-001 |
| Layer | 1 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/tests/test_layout.py` — dual-context path detection

### PKG-SPEC-CONFORMANCE-001 (modified — test file only)

| Field | Value |
|-------|-------|
| Package ID | PKG-SPEC-CONFORMANCE-001 |
| Layer | 2 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/tests/test_spec_conformance.py` — dual-context path detection + skipif for installed-only tests

### PKG-VOCABULARY-001 (modified — test file only)

| Field | Value |
|-------|-------|
| Package ID | PKG-VOCABULARY-001 |
| Layer | 1 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/tests/test_vocabulary.py` — dual-context path detection + skipif for G1 chain tests

### PKG-FRAMEWORK-WIRING-001 (modified — test file only)

| Field | Value |
|-------|-------|
| Package ID | PKG-FRAMEWORK-WIRING-001 |
| Layer | 2 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/tests/test_framework_wiring.py` — dual-context path detection + FMWK-004 in expected list

### PKG-LLM-GATEWAY-001 (modified — test file only)

| Field | Value |
|-------|-------|
| Package ID | PKG-LLM-GATEWAY-001 |
| Layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |

Modified assets:
- `HOT/tests/test_llm_gateway.py` — dual-context path detection (replaces hardcoded parents[3])

## 6. Test Plan

This handoff is unique: the tests ARE the deliverable. Success is measured by regression counts, not new test additions.

### Verification Tests (per file)

| File | Pre-Fix Failures | Post-Fix Target | Verification |
|------|-----------------|-----------------|--------------|
| `test_bootstrap_sequence.py` | 9 | 0 | Run in staging: all pass |
| `test_layout.py` | 6 | 0 | Run in staging: all pass (or skipped with reason) |
| `test_spec_conformance.py` | 7 | 0 | Run in staging: all pass (or skipped with reason) |
| `test_vocabulary.py` | 2-3 | 0 | Run in staging: all pass (or skipped with reason) |
| `test_framework_wiring.py` | 1 | 0 | Run in staging: all pass; installed: FMWK-004 included |
| `test_llm_gateway.py` | 1 | 0 | Run in staging AND installed: all pass |
| **Total** | **26** | **0** | Full staging regression: 0 failures |

### Acceptance Criteria

1. Staging regression: `python3 -m pytest Control_Plane_v2/_staging/ -q --import-mode=importlib --ignore=...PKG-ATTENTION-001 --ignore=...PKG-SESSION-HOST-001 --ignore=...PKG-PROMPT-ROUTER-001` → **0 failed**
2. Clean-room installed regression: `pytest HOT/tests HO1/tests HO2/tests` → **0 failed** (or document any remaining)
3. All 8/8 gates pass

### Tests that MAY be skipped in staging (acceptable)

Some tests validate the installed/merged system (governance artifacts, registry chains). These CAN be `skipif`-decorated in staging context as long as they still run and pass in the installed clean-room. The results file must document which tests are skip-decorated and confirm they pass in clean-room.

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Dual-context pattern (reference) | `_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py:14-31` | THE pattern to copy |
| Dual-context pattern (reference) | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py:15-42` | Second example |
| HANDOFF-20 results | `_staging/handoffs/RESULTS_HANDOFF_20.md` | Precedent for multi-package test cleanup |
| Bootstrap sequence test | `_staging/tests/test_bootstrap_sequence.py:22-24` | Doubled path bug to fix |
| Layout test | `_staging/PKG-LAYOUT-001/HOT/tests/test_layout.py` | Path resolution to fix |
| Spec conformance test | `_staging/PKG-SPEC-CONFORMANCE-001/HOT/tests/test_spec_conformance.py` | Path resolution to fix |
| Vocabulary test | `_staging/PKG-VOCABULARY-001/HOT/tests/test_vocabulary.py` | Path resolution to fix |
| Framework wiring test | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/tests/test_framework_wiring.py` | Path + count to fix |
| LLM Gateway test | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` | Path resolution to fix |
| Kernel hashing | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | compute_sha256() for manifests |
| Kernel packages | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | pack() for archives |

## 8. End-to-End Verification

```bash
# 1. Staging regression (THE primary success metric)
python3 -m pytest Control_Plane_v2/_staging/ -q --import-mode=importlib \
  --ignore=Control_Plane_v2/_staging/PKG-ATTENTION-001 \
  --ignore=Control_Plane_v2/_staging/PKG-SESSION-HOST-001 \
  --ignore=Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001
# Expected: 0 failed

# 2. Clean-room install
TMPDIR=$(mktemp -d)
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR/bootstrap"
bash "$TMPDIR/bootstrap/install.sh" --root "$TMPDIR/CP_2.1" --dev

# 3. Clean-room tests
ROOT="$TMPDIR/CP_2.1"
PYTHONPATH="$ROOT/HOT/kernel:$ROOT/HOT:$ROOT/HOT/scripts:$ROOT/HOT/admin:$ROOT/HO1/kernel:$ROOT/HO2/kernel" \
  python3 -m pytest "$ROOT/HOT/tests" "$ROOT/HO1/tests" "$ROOT/HO2/tests" -q
# Expected: 0 failed

# 4. Gates
python3 "$ROOT/HOT/scripts/gate_check.py" --root "$ROOT" --all
# Expected: 8/8 PASS
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `test_bootstrap_sequence.py` | `_staging/tests/` | MODIFY (fix doubled path) |
| `test_layout.py` | `_staging/PKG-LAYOUT-001/HOT/tests/` | MODIFY (dual-context) |
| `test_spec_conformance.py` | `_staging/PKG-SPEC-CONFORMANCE-001/HOT/tests/` | MODIFY (dual-context + skipif) |
| `test_vocabulary.py` | `_staging/PKG-VOCABULARY-001/HOT/tests/` | MODIFY (dual-context + skipif) |
| `test_framework_wiring.py` | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/tests/` | MODIFY (dual-context + count fix) |
| `test_llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/` | MODIFY (dual-context) |
| `manifest.json` | `_staging/PKG-LAYOUT-001/` | MODIFY (hash update) |
| `manifest.json` | `_staging/PKG-SPEC-CONFORMANCE-001/` | MODIFY (hash update) |
| `manifest.json` | `_staging/PKG-VOCABULARY-001/` | MODIFY (hash update) |
| `manifest.json` | `_staging/PKG-FRAMEWORK-WIRING-001/` | MODIFY (hash update) |
| `manifest.json` | `_staging/PKG-LLM-GATEWAY-001/` | MODIFY (hash update) |
| `PKG-LAYOUT-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-SPEC-CONFORMANCE-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-VOCABULARY-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-FRAMEWORK-WIRING-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-LLM-GATEWAY-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_24.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

1. **One pattern everywhere.** The `ledger_client.py` probe is proven (HANDOFF-20). Apply it identically. No variants, no creativity.
2. **Tests document reality.** If 6 frameworks exist, the test expects 6. Tests that assert false expectations are bugs, not features.
3. **Skip over lie.** When a test CANNOT run in staging (needs merged artifacts), skip it with a clear reason. Do NOT make it return a fake PASS.
4. **Exclude the dead.** V1 packages (PKG-SESSION-HOST-001, PKG-PROMPT-ROUTER-001) are excluded from regression, not fixed. They're dead code.
5. **Zero is the target.** After this handoff, `--ignore` for V1+ATTENTION is the only exclusion needed. Every other staged test passes.
6. **Test-only scope.** No production code changes. If a test can't be fixed without changing production code, flag it in the results file — don't expand scope.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-24** — Staging test cleanup: zero pre-existing failures

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_24_staging_test_cleanup.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Verify failures BEFORE fixing. Confirm 0 failures AFTER fixing. Run before/after for each file.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL staged package tests. Target: 0 failures (with --ignore for ATTENTION, SESSION-HOST-001, PROMPT-ROUTER-001).
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_24.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md.
8. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz after all 5 package archives are rebuilt.
9. Built-in tools: Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER raw hashlib or shell tar.
10. Test-only changes. Do NOT modify production code. Only test files and manifests.

**Reference file to read FIRST:**
`Control_Plane_v2/_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py` lines 14-31 — this is THE dual-context pattern you must replicate.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What is the dual-context detection probe? What file does it check? Why is it unambiguous?
2. How many test files are you modifying? List all 6 with their full paths.
3. What is the doubled-path bug in test_bootstrap_sequence.py? What do lines 23-24 resolve to?
4. Why is PKG-SESSION-HOST-001 excluded instead of fixed? What dead package does it import?
5. What does `test_exactly_five_frameworks` currently expect? What should it expect after your fix?
6. For tests that can't run in staging (need merged governance artifacts), what do you do? Give the exact decorator.
7. How many package manifests do you update? How many package archives do you rebuild?
8. What is the staging regression command WITH the correct --ignore flags? What is the target failure count?
9. After your fix, name 3 tests that should PASS in staging that previously FAILED.
10. What tar format and hash format do you use? Where are compute_sha256() and pack()?

**Adversarial:**
11. You're modifying 5 packages. If you accidentally change a production file (not a test), what gate catches it?
12. In the dual-context probe, what happens if someone creates a file called `ledger_client.py` inside PKG-LAYOUT-001's HOT/kernel/? How would you guard against this?
13. test_bootstrap_sequence.py is NOT inside a package — it's in `_staging/tests/`. Does it need a manifest hash update? Does it go into CP_BOOTSTRAP?

STOP AFTER ANSWERING. Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. Probe: `(_HOT / "kernel" / "ledger_client.py").exists()`. Checks for ledger_client.py from PKG-KERNEL-001. Unambiguous because: in installed root, all PKG-KERNEL-001 files merge into HOT/kernel/ so the file exists. In staging, each package's HOT/ only has its OWN files — no cross-package files. Do NOT use admin/main.py (ambiguous for PKG-ADMIN-001).
2. Six files: (1) `_staging/tests/test_bootstrap_sequence.py`, (2) `_staging/PKG-LAYOUT-001/HOT/tests/test_layout.py`, (3) `_staging/PKG-SPEC-CONFORMANCE-001/HOT/tests/test_spec_conformance.py`, (4) `_staging/PKG-VOCABULARY-001/HOT/tests/test_vocabulary.py`, (5) `_staging/PKG-FRAMEWORK-WIRING-001/HOT/tests/test_framework_wiring.py`, (6) `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py`.
3. Line 23: `STAGING = Path(__file__).resolve().parent.parent` resolves to `_staging/` (not `Control_Plane_v2/` as the comment claims). Line 24: `STAGING_DIR = STAGING / "_staging"` becomes `_staging/_staging/` — doubled. Fix: `STAGING_DIR = Path(__file__).resolve().parent.parent` directly (it's already `_staging/`).
4. PKG-SESSION-HOST-001 is V1, superseded by PKG-SESSION-HOST-V2-001. It imports `PKG-PROMPT-ROUTER-001` which was removed in CLEANUP-2. Fixing it means resurrecting a dead dependency or rewriting V1 code that nobody uses. Cheaper and correct to exclude.
5. Currently expects exactly 5 frameworks: FMWK-000, FMWK-001, FMWK-002, FMWK-005, FMWK-007. After fix: expect 6 frameworks (add FMWK-004 from PKG-ATTENTION-001, which is in the bootstrap).
6. `@pytest.mark.skipif(not (_HOT / "kernel" / "ledger_client.py").exists(), reason="requires installed/merged root")`. Skip with reason, not fake pass. These tests still run in clean-room installed verification.
7. 5 manifests (one per package). 5 package archives + 1 CP_BOOTSTRAP = 6 archives total.
8. `python3 -m pytest Control_Plane_v2/_staging/ -q --import-mode=importlib --ignore=Control_Plane_v2/_staging/PKG-ATTENTION-001 --ignore=Control_Plane_v2/_staging/PKG-SESSION-HOST-001 --ignore=Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001`. Target: **0 failed**.
9. Any 3 from: `test_seed_csvs_readable` (bootstrap), `test_has_tiers` (layout), `test_baseline_schemas_present` (spec conformance), `test_g1_passes_with_real_registries` (vocabulary), `test_exactly_five_frameworks` (framework wiring), `test_backward_compat_import_shim` (LLM gateway).
10. Tar: `pack()` from `_staging/PKG-KERNEL-001/HOT/kernel/packages.py`. Hash: `compute_sha256()` from `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py`. Format: `sha256:<64hex>` (71 chars).
11. G0A (manifest integrity) would catch it if the production file's hash changes but isn't updated in the manifest. Also G0B (orphan detection) if a file exists that no manifest claims. Both gates validate file-to-manifest correspondence.
12. This would be a governance violation — no package should create `kernel/ledger_client.py` because that file is owned by PKG-KERNEL-001 (tracked in file_ownership.csv). The probe would give a false positive for that package. Guard: file_ownership.csv prevents this at install time. At test time, the risk is theoretical — only exists if someone manually creates the file in a staging package, which would fail G0B.
13. No manifest update needed — it's not inside a package directory. It's NOT in CP_BOOTSTRAP (bootstrap only contains packages, not loose test files). The file is part of the staging test infrastructure, not a governed package asset.
