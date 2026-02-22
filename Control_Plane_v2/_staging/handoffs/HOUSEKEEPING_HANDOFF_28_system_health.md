# HOUSEKEEPING_HANDOFF_28: System Health — Remove Orphan Package from Bootstrap

## 1. Mission

Remove PKG-ATTENTION-001 from CP_BOOTSTRAP (it's unused — HO2 has its own absorbed attention implementation), rebuild the bootstrap archive back to 21 packages, and verify via clean-room install that all tests pass and all gates clear. The `test_exactly_five_frameworks` pre-existing failure resolves automatically when PKG-ATTENTION-001 (which installs FMWK-004_Attention) is no longer in the bootstrap. No packages modified. No code changes.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`.** No exceptions. Nothing written to `CP_2.1/`, the conflated repo tree, or any other location outside `_staging/`. Clean-room verification uses ephemeral temp directories only.
2. **PKG-ATTENTION-001 stays in `_staging/`.** It is NOT deleted from the staging directory. It is only excluded from CP_BOOTSTRAP. It remains available for future integration if needed.
3. **No code changes.** No source files, test files, or manifests are modified. The only artifact that changes is CP_BOOTSTRAP.tar.gz (rebuilt without PKG-ATTENTION-001).
4. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
5. **Results file.** When finished, write `_staging/handoffs/RESULTS_HANDOFF_28.md` (see Results File section in BUILDER_HANDOFF_STANDARD.md).
6. **Full regression test.** Run ALL tests from clean-room install. The 1 pre-existing framework failure (test_exactly_five_frameworks) should be GONE now that PKG-ATTENTION-001 is not installed. Zero failures is the target.
7. **Baseline snapshot.** Your results file must include a baseline snapshot (package count, file_ownership rows, total tests, all gate results).
8. **CP_BOOTSTRAP rebuild is the primary deliverable.** Rebuild CP_BOOTSTRAP.tar.gz with 21 packages (excluding PKG-ATTENTION-001). Report the new member count and SHA256.
9. **Built-in tools:** Use `hashing.py:compute_sha256()` for the CP_BOOTSTRAP hash and `packages.py:pack()` for the archive rebuild. NEVER use raw hashlib or shell tar.
10. **This is HOUSEKEEPING.** Scope is narrow. Rebuild bootstrap, verify in clean room, report. Do NOT refactor, add features, fix unrelated tests, or modify any package source.

## 3. Architecture / Design

### Why PKG-ATTENTION-001 Is Being Removed from Bootstrap

PKG-ATTENTION-001 is a standalone attention service (HANDOFF-4, pre-dating the v2 architecture). It ships `HOT/FMWK-004_Attention/manifest.yaml`, creating a 6th framework directory in the installed root.

**Problem:** `test_exactly_five_frameworks` in PKG-FRAMEWORK-WIRING-001 expects exactly 5 framework directories (FMWK-000, -001, -002, -005, -007). PKG-ATTENTION-001 creates FMWK-004_Attention as a 6th → test fails.

**Root cause:** PKG-ATTENTION-001 is not integrated into the dispatch loop. HO2 has its own absorbed `attention.py` (inside PKG-HO2-SUPERVISOR-001) with `AttentionRetriever` that IS wired into the live system at `ho2_supervisor.py:111`. The standalone package is dead code in the installed system.

**Decision:** Remove from bootstrap. The package remains in `_staging/` for potential future use but is not installed.

### What Changes

```
BEFORE (H-27):  CP_BOOTSTRAP has 22 packages including PKG-ATTENTION-001
                test_exactly_five_frameworks FAILS (6 framework dirs)
                648 tests, 647 pass, 1 fail

AFTER (H-28):   CP_BOOTSTRAP has 21 packages without PKG-ATTENTION-001
                test_exactly_five_frameworks PASSES (5 framework dirs)
                ~640+ tests, all pass, 0 fail
```

Test count drops slightly because PKG-ATTENTION-001's tests are no longer in the installed tree. All remaining tests should pass.

### Adversarial Analysis: Removing PKG-ATTENTION-001 from Bootstrap

**Hurdles**: `resolve_install_order.py` auto-discovers packages from the bootstrap archive. If PKG-ATTENTION-001.tar.gz is simply absent from the archive, it won't be discovered or installed. No code change needed — just exclude the archive.

**Not Enough**: We could also delete the package from `_staging/` entirely. But it's legitimate code that may be useful when building the unified attention service later. Keeping it in staging but out of bootstrap is the right balance.

**Too Much**: We could fix the framework wiring test to accept 6 frameworks AND keep PKG-ATTENTION-001 in bootstrap. But installing dead code that nothing uses just to avoid a test update is backwards.

**Synthesis**: Remove from bootstrap. Keep in staging. The framework test passes. The installed system has no dead code.

## 4. Implementation Steps

### Step 1: Identify current CP_BOOTSTRAP membership

**1a**: Read the current CP_BOOTSTRAP.tar.gz member list to confirm PKG-ATTENTION-001.tar.gz is present.

**1b**: Confirm the 21 packages that SHOULD remain (all current minus PKG-ATTENTION-001):
```
PKG-GENESIS-000, PKG-KERNEL-001, PKG-REG-001, PKG-VOCABULARY-001,
PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001,
PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001,
PKG-VERIFY-001, PKG-WORK-ORDER-001, PKG-BOOT-MATERIALIZE-001,
PKG-HO2-SUPERVISOR-001, PKG-LLM-GATEWAY-001, PKG-ANTHROPIC-PROVIDER-001,
PKG-HO1-EXECUTOR-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-ADMIN-001
```

Plus: `install.sh`, `resolve_install_order.py`, `packages/` directory.

### Step 2: Rebuild CP_BOOTSTRAP.tar.gz without PKG-ATTENTION-001

**2a**: Use the existing bootstrap rebuild pattern. The CP_BOOTSTRAP is assembled from individual package archives in `_staging/`. Rebuild it with the 21-package set, excluding `PKG-ATTENTION-001.tar.gz`.

**2b**: Use `packages.py:pack()` for the archive. Delete `.DS_Store` and `__pycache__` from the staging directory immediately before packing.

**2c**: Compute and record the new CP_BOOTSTRAP SHA256 using `hashing.py:compute_sha256()`.

**2d**: Verify the archive member count: should be 21 package archives + `install.sh` + `resolve_install_order.py` + `packages/` = 24 total members.

### Step 3: Clean-room verification

**3a**: Extract to temp directory:
```bash
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev
```

**3b**: Run ALL tests — target zero failures:
```bash
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -q
```

**3c**: Run 8/8 governance gates:
```bash
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 "$TMPDIR/HOT/scripts/gate_check.py" --all --enforce --root "$TMPDIR"
```

**3d**: Verify `test_exactly_five_frameworks` specifically passes:
```bash
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests/test_framework_wiring.py::TestRemovedFrameworks::test_exactly_five_frameworks" -v
```

## 5. Package Plan

**No packages modified.** Only CP_BOOTSTRAP.tar.gz is rebuilt.

### CP_BOOTSTRAP changes

| Field | Before (H-27) | After (H-28) |
|-------|---------------|---------------|
| Package count | 22 | 21 |
| Removed | — | PKG-ATTENTION-001 |
| Total archive members | 25 | 24 |
| Expected test failures | 1 (framework count) | 0 |

### Packages remaining in bootstrap (21)

PKG-GENESIS-000, PKG-KERNEL-001, PKG-REG-001, PKG-VOCABULARY-001, PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001, PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001, PKG-VERIFY-001, PKG-WORK-ORDER-001, PKG-BOOT-MATERIALIZE-001, PKG-HO2-SUPERVISOR-001, PKG-LLM-GATEWAY-001, PKG-ANTHROPIC-PROVIDER-001, PKG-HO1-EXECUTOR-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-ADMIN-001

## 6. Test Plan

No new tests written. This handoff verifies existing tests pass after removing the orphan package.

| Verification | Description | Expected |
|------|-------------|----------|
| `test_exactly_five_frameworks` | 5 framework dirs exist (FMWK-004_Attention no longer installed) | PASS |
| `test_fmwk_004_removed` | FMWK-004_Prompt_Governance doesn't exist | PASS (unchanged) |
| Clean-room full suite | All 21-package tests, zero collection errors | All pass, 0 fail |
| Governance gates | All 8 gates | 8/8 PASS |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Current CP_BOOTSTRAP | `_staging/CP_BOOTSTRAP.tar.gz` | Archive to rebuild |
| install.sh | `_staging/install.sh` | Bootstrap installer (stays in archive) |
| resolve_install_order.py | `_staging/resolve_install_order.py` | Auto-discovery (stays in archive) |
| packages.py | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | `pack()` for archive rebuild |
| hashing.py | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | `compute_sha256()` for archive hash |
| Framework wiring test | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/tests/test_framework_wiring.py` | Verify test passes (no modification needed) |
| RESULTS_HANDOFF_27.md | `_staging/handoffs/RESULTS_HANDOFF_27.md` | Previous baseline: 648 tests, 22 packages |

## 8. End-to-End Verification

```bash
# 1. Clean-room install (must pass with zero failures)
TMPDIR=$(mktemp -d)
cd Control_Plane_v2/_staging
tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev

# 2. Run ALL tests — target: zero failures
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -q

# 3. Specifically verify the framework test passes
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 -m pytest "$TMPDIR/HOT/tests/test_framework_wiring.py::TestRemovedFrameworks::test_exactly_five_frameworks" -v

# 4. Run gates (8/8 PASS expected)
PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" \
  python3 "$TMPDIR/HOT/scripts/gate_check.py" --all --enforce --root "$TMPDIR"
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (22→21 packages, exclude PKG-ATTENTION-001) |
| `RESULTS_HANDOFF_28.md` | `_staging/handoffs/` | CREATE |

No source files, test files, or manifests are modified. No writes outside `_staging/`.

## 10. Design Principles

1. **Don't install dead code.** PKG-ATTENTION-001 is not imported by any working component. HO2 has its own attention implementation. Installing unused code creates false framework directories and breaks tests.
2. **Keep but don't install.** The package stays in `_staging/` for future use. Removing from bootstrap is not deleting — it's decluttering the installed system.
3. **Zero pre-existing failures.** The installed system should have zero test failures. Accepting "pre-existing" failures is deferred debt that compounds.
4. **Agents NEVER write outside `_staging/`.** Clean-room verification uses ephemeral temp directories. Persistent installs (CP_2.1) are the user's responsibility.
5. **Housekeeping is not refactoring.** Rebuild one archive, verify in clean room, report. No code changes. No improvements. No scope creep.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HOUSEKEEPING-28** — Remove orphan package from bootstrap, clean-room verification

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/HOUSEKEEPING_HANDOFF_28_system_health.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. No exceptions. NEVER write to CP_2.1, the conflated repo tree, or any location outside `_staging/`. Clean-room verification uses ephemeral temp directories only.
2. No code changes. No source files, test files, or manifests are modified. Only CP_BOOTSTRAP.tar.gz is rebuilt.
3. PKG-ATTENTION-001 stays in `_staging/`. Do NOT delete the package directory. Only exclude it from CP_BOOTSTRAP.
4. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL tests from clean-room install. Zero failures is the target. The pre-existing framework test failure should be GONE.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_28.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section.
8. CP_BOOTSTRAP rebuild: Use `packages.py:pack()` for the archive and `hashing.py:compute_sha256()` for the hash. NEVER use raw hashlib or shell tar.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What package is being removed from CP_BOOTSTRAP and why? What test failure does this fix?
2. Why is PKG-ATTENTION-001 unused? What does HO2 use instead? (Name the file and class.)
3. After rebuilding CP_BOOTSTRAP, how many packages should it contain? List all 21 by ID.
4. How many total members should the CP_BOOTSTRAP archive have? (packages + support files)
5. What happens to PKG-ATTENTION-001 in `_staging/`? Is it deleted?
6. What test specifically validates that FMWK-004 does NOT exist? What exact directory name does it check?
7. What tools do you use to rebuild CP_BOOTSTRAP? (Name the module and function for both archiving and hashing.)
8. Where does clean-room verification happen? Can you write to CP_2.1 or anywhere outside `_staging/`?
9. What is the expected test count direction — UP, DOWN, or SAME compared to H-27's 648? Why?
10. After clean-room verification passes, what does the agent deliver? (Hint: two files in `_staging/`.)

**11. THE ADVERSARIAL SIMULATION (PRE-FLIGHT)**
Before executing the first command, answer these three Bonus "Pressure Tests":
1. **The Failure Mode:** "If this build fails at Gate G3 (Package Integrity), which specific file/hash in my current scope is the most likely culprit?"
2. **The Shortcut Check:** "Is there a Kernel tool (e.g., `hashing.py`) I am tempted to skip in favor of a standard shell command? (If yes, explain why you will NOT do that)."
3. **The Semantic Audit:** "Identify one word in my current plan that is 'ambiguous' according to the Lexicon of Precision and redefine it now."

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers

1. PKG-ATTENTION-001 is removed because it's unused dead code — nothing in the dispatch loop imports from it. HO2 has its own absorbed attention.py. Removing it fixes `test_exactly_five_frameworks` which fails because PKG-ATTENTION-001 installs FMWK-004_Attention as a 6th framework directory (test expects only 5).
2. HO2 uses `HO2/kernel/attention.py` with `AttentionRetriever` class (imported at `ho2_supervisor.py:37`, instantiated at line 111). This is an absorbed/simplified version of the standalone attention concepts, wired directly into the Kitchener dispatch loop.
3. 21 packages: PKG-GENESIS-000, PKG-KERNEL-001, PKG-REG-001, PKG-VOCABULARY-001, PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001, PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001, PKG-VERIFY-001, PKG-WORK-ORDER-001, PKG-BOOT-MATERIALIZE-001, PKG-HO2-SUPERVISOR-001, PKG-LLM-GATEWAY-001, PKG-ANTHROPIC-PROVIDER-001, PKG-HO1-EXECUTOR-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-ADMIN-001.
4. 24 total members: 21 package archives + install.sh + resolve_install_order.py + packages/ directory.
5. PKG-ATTENTION-001 stays in `_staging/`. It is NOT deleted. Only excluded from the bootstrap archive.
6. `test_fmwk_004_removed` (line 79-82 in test_framework_wiring.py) checks for `FMWK-004_Prompt_Governance` — the old dead directory name. `test_exactly_five_frameworks` (line 89-94) globs `FMWK-*/` and expects exactly 5 dirs.
7. `packages.py:pack()` for archiving (deterministic tar.gz). `hashing.py:compute_sha256()` for the SHA256 hash (produces `sha256:<64hex>` format).
8. Clean-room verification happens in an ephemeral temp directory (`mktemp -d`). NEVER write to CP_2.1 or anywhere outside `_staging/`. The temp dir is disposable.
9. DOWN from 648. PKG-ATTENTION-001's tests (installed under HOT/tests/) are no longer present. All remaining tests should pass with 0 failures.
10. Two files in `_staging/`: (a) the rebuilt `CP_BOOTSTRAP.tar.gz` (21 packages) and (b) `handoffs/RESULTS_HANDOFF_28.md` with full clean-room verification, baseline snapshot, and regression results.

### Expected Adversarial Answers

11.1 **Failure Mode**: CP_BOOTSTRAP.tar.gz itself is the only file in scope. If G3 fails, the most likely culprit is a stale or incorrectly-packed CP_BOOTSTRAP archive (e.g., .DS_Store included, wrong member set, or `./` prefix on entries).
11.2 **Shortcut Check**: Yes — tempting to use shell `tar` instead of `packages.py:pack()`. Will NOT do that because shell tar produces non-deterministic metadata (timestamps, uid), producing different hashes each build. `pack()` is deterministic (mtime=0, uid=0, sorted entries, PAX format).
11.3 **Semantic Audit**: "Remove" is ambiguous — could mean delete from disk or exclude from archive. Redefined: "Exclude PKG-ATTENTION-001.tar.gz from the CP_BOOTSTRAP archive membership. The package directory and its archive remain in `_staging/` untouched."
