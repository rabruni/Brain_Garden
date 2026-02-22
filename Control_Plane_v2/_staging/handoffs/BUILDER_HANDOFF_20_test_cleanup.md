# BUILDER_HANDOFF_20: Test Infrastructure Cleanup

## 1. Mission

Fix 24 pre-existing test failures across 3 test files in the installed system. The tests were written for staging layout (`_staging/PKG-*/HOT/tests/`) and break when run from the installed root where package contents are merged into a flat tier structure. Additionally, FMWK-005 (added by Gemini) is missing required manifest fields, causing framework wiring tests to fail.

**Affected packages:** PKG-BOOT-MATERIALIZE-001, PKG-ADMIN-001, PKG-FRAMEWORK-WIRING-001.

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`.** Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** The deliverable IS test fixes — verify by running the modified tests against a clean-room install.
3. **Package everything.** After modifying files, update manifest.json SHA256 hashes using `compute_sha256()`, repack affected packages using `packages.py:pack()`, rebuild CP_BOOTSTRAP.tar.gz.
4. **End-to-end verification.** Extract CP_BOOTSTRAP.tar.gz → install to temp dir → run ALL tests. All 24 previously-failing tests must pass. Zero new failures introduced.
5. **No hardcoding.** Path detection must work in BOTH contexts (staging and installed) using filesystem probing, not hardcoded parent counts.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`.
8. **Results file.** Write `_staging/handoffs/RESULTS_HANDOFF_20.md` when finished.
9. **Full regression test.** Run ALL staged package tests and report results.
10. **Baseline snapshot.** Include package count, file_ownership rows, total tests, all gate results.

**Task-specific constraints:**
11. **Dual-context path detection.** All path resolution MUST work from both `_staging/PKG-*/HOT/tests/` (staging) AND `{INSTALL_ROOT}/HOT/tests/` (installed). Use filesystem existence checks (e.g., `(_HOT / "kernel" / "ledger_client.py").exists()`) to detect context — NEVER count parent levels.
12. **FMWK-005 manifest must match schema.** Use FMWK-007 as the reference template. FMWK-005 is missing 8 fields/misnamed: `title` (has `name`), `ring`, `created_at`, `assets`, `expected_specs`, `invariants`, `path_authorizations`, `required_gates`. Tests enforce 4 of these (`ring`, `expected_specs`, `invariants`, `required_gates`); fix all 8 for schema compliance.

## 3. Architecture / Design

### Problem

Three test files fail because they assume the staging directory layout:

```
STAGING:                                    INSTALLED:
_staging/                                   CP_2.1/
  PKG-KERNEL-001/HOT/kernel/ledger_client.py    HOT/kernel/ledger_client.py
  PKG-LAYOUT-002/HOT/config/layout.json         HOT/config/layout.json
  PKG-BOOT-MATERIALIZE-001/HOT/scripts/         HOT/scripts/
  PKG-ADMIN-001/HOT/admin/main.py               HOT/admin/main.py
  PKG-*/HOT/tests/test_*.py                     HOT/tests/test_*.py
```

In staging, `Path(__file__).resolve().parents[3]` reaches `_staging/` and sibling packages are accessible. In installed root, `parents[3]` reaches `playground/` where no `PKG-*` directories exist.

### Solution: Dual-Context Detection

Each test file detects its context by probing the filesystem:

```python
_HERE = Path(__file__).resolve().parent   # .../HOT/tests/
_HOT = _HERE.parent                        # .../HOT/

if (_HOT / "kernel" / "ledger_client.py").exists():
    # INSTALLED: everything merged under HOT/
    # → resolve imports and data from _HOT subdirectories
else:
    # STAGING: reach sibling packages via _HERE.parents[2]
    # → resolve imports and data from PKG-*/HOT/ directories
```

This is robust because `ledger_client.py` only exists under the HOT of an installed root (never inside PKG-BOOT-MATERIALIZE-001's own HOT).

### FMWK-005 Manifest Fix

FMWK-005 was added by Gemini with only basic fields. The test framework_wiring.py validates that every framework manifest has `expected_specs`, `ring`, `invariants`, `required_gates`. Fix: add the missing fields following the exact schema used by FMWK-007.

### Adversarial Analysis: Dual-Context vs. Separate Test Files

**Hurdles**: Dual-context detection adds a branch to module-level code. If the detection logic is wrong, tests silently import from the wrong location. Mitigation: the probe file (`ledger_client.py`) is unambiguous — it's a kernel module that never ships inside non-kernel packages.

**Not Enough**: Without dual-context, we'd need separate copies of tests for staging vs. installed. That means tests diverge over time and the installed tests become second-class citizens (exactly how we got here).

**Too Much**: We could build a conftest.py with centralized path setup. But that's a new file that every package would need to ship, and it couples test infrastructure across packages.

**Synthesis**: Dual-context detection in each test file. Self-contained, no new files, works in both contexts. The detection probe (`ledger_client.py` existence) is definitive.

## 4. Implementation Steps

### Step 1: Fix test_boot_materialize.py

**File:** `_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py`

Replace lines 14-25 (path setup block) with:

```python
# Dual-context path detection: installed root vs staging packages
_HERE = Path(__file__).resolve().parent
_HOT = _HERE.parent

if (_HOT / "kernel" / "ledger_client.py").exists():
    # Installed layout — all packages merged under HOT/
    LAYOUT_SOURCE = _HOT / "config" / "layout.json"
    _paths = [_HOT / "scripts", _HOT, _HOT / "kernel"]
else:
    # Staging layout — sibling packages under _staging/
    _STAGING_ROOT = _HERE.parents[2]
    LAYOUT_SOURCE = _STAGING_ROOT / "PKG-LAYOUT-002" / "HOT" / "config" / "layout.json"
    _paths = [
        _STAGING_ROOT / "PKG-BOOT-MATERIALIZE-001" / "HOT" / "scripts",
        _STAGING_ROOT / "PKG-LAYOUT-002" / "HOT" / "scripts",
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT",
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT" / "kernel",
    ]

for p in _paths:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
```

### Step 2: Fix test_admin.py

**File:** `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`

**2a.** Replace lines 14-15 (path setup) with:

```python
# Dual-context path detection: installed root vs staging packages
# Probe: kernel/ledger_client.py exists ONLY in installed root (merged from PKG-KERNEL-001).
# It does NOT exist in PKG-ADMIN-001's own HOT, so this probe is unambiguous.
# NOTE: Do NOT use admin/main.py as probe — it exists in BOTH contexts (ambiguous).
_HERE = Path(__file__).resolve().parent
_HOT = _HERE.parent

if (_HOT / "kernel" / "ledger_client.py").exists():
    # Installed layout — all packages merged under HOT/
    sys.path.insert(0, str(_HOT / "admin"))
    for p in [_HOT / "kernel", _HOT / "scripts", _HOT]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
else:
    # Staging layout — admin code in sibling package
    _STAGING_ROOT = _HERE.parents[2]
    sys.path.insert(0, str(_STAGING_ROOT / "PKG-ADMIN-001" / "HOT" / "admin"))
    for p in [
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT" / "kernel",
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT",
        _STAGING_ROOT / "PKG-BOOT-MATERIALIZE-001" / "HOT" / "scripts",
    ]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
```

**2b.** Replace `_write_layout_json` function (lines 69-75) with:

```python
def _write_layout_json(tmp_path: Path) -> Path:
    # Reuse the same dual-context detection as the module-level path setup.
    # _HOT is already resolved at module level via kernel/ledger_client.py probe.
    if (_HOT / "config" / "layout.json").exists():
        layout_src = _HOT / "config" / "layout.json"
    else:
        layout_src = _HERE.parents[2] / "PKG-LAYOUT-002" / "HOT" / "config" / "layout.json"
    cfg_dir = tmp_path / "HOT" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    dst = cfg_dir / "layout.json"
    dst.write_text(layout_src.read_text())
    return dst
```

### Step 3: Fix test_framework_wiring.py

**File:** `_staging/PKG-FRAMEWORK-WIRING-001/HOT/tests/test_framework_wiring.py`

**3a.** Add FMWK-005 to `EXPECTED_WIRING` dict (after line 33):

```python
"FMWK-005": [],
```

**3b.** Update `test_exactly_four_frameworks` (line 92) — change expected list:

```python
assert fmwk_ids == ["FMWK-000", "FMWK-001", "FMWK-002", "FMWK-005", "FMWK-007"], \
    f"Expected exactly 5 frameworks, got: {fmwk_ids}"
```

### Step 4: Fix FMWK-005 manifest

**File:** `_staging/PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml`

Replace entire file with complete manifest (use FMWK-007 as template):

```yaml
framework_id: FMWK-005
title: Admin Framework
version: 1.0.0
status: active
ring: admin
plane_id: hot
created_at: "2026-02-15T00:00:00Z"
assets:
  - admin_config.json
expected_specs: []
invariants:
  - level: MUST
    statement: ADMIN config MUST be validated before session start
  - level: MUST
    statement: ADMIN operations MUST be audited in governance ledger
  - level: MUST NOT
    statement: ADMIN MUST NOT interact with RESIDENT namespaces
path_authorizations:
  - "HOT/admin/*.py"
  - "HOT/config/admin_config.json"
required_gates:
  - G0
  - G1
  - G5
```

### Step 5: Update manifest.json SHA256 hashes

For each modified package, recompute SHA256 for changed files using `compute_sha256()` and update `manifest.json`.

Affected manifests:
- `_staging/PKG-BOOT-MATERIALIZE-001/manifest.json` (test_boot_materialize.py hash)
- `_staging/PKG-ADMIN-001/manifest.json` (test_admin.py hash + manifest.yaml hash)
- `_staging/PKG-FRAMEWORK-WIRING-001/manifest.json` (test_framework_wiring.py hash)

### Step 6: Repack affected packages

Using `packages.py:pack()`, rebuild:
- `_staging/PKG-BOOT-MATERIALIZE-001.tar.gz`
- `_staging/PKG-ADMIN-001.tar.gz`
- `_staging/PKG-FRAMEWORK-WIRING-001.tar.gz`

Clean `__pycache__` and `.DS_Store` before packing.

### Step 7: Rebuild CP_BOOTSTRAP.tar.gz

Rebuild `_staging/CP_BOOTSTRAP.tar.gz` with updated package archives. Expected: 20 packages + install.sh + resolve_install_order.py.

### Step 8: Clean-room install and verify

```bash
TMPDIR=$(mktemp -d)
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
```

Expected: 20 packages installed, 8/8 gates PASS.

### Step 9: Run all tests from installed root

```bash
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 -m pytest "$IR/HOT/tests/" -v
```

Expected: 444+ tests pass, 0 failures.

### Step 10: Write results file

Write `_staging/handoffs/RESULTS_HANDOFF_20.md` with full template.

## 5. Package Plan

No new packages. Three existing packages modified:

### PKG-BOOT-MATERIALIZE-001 (Layer 2)
- **Spec:** SPEC-GENESIS-001, **Framework:** FMWK-000, **Plane:** hot
- **Modified asset:** `HOT/tests/test_boot_materialize.py` (path detection fix)
- **Dependencies:** PKG-KERNEL-001, PKG-LAYOUT-002

### PKG-ADMIN-001 (Layer 2)
- **Spec:** SPEC-GATE-001, **Framework:** FMWK-005, **Plane:** hot
- **Modified assets:** `HOT/tests/test_admin.py` (path detection fix), `HOT/FMWK-005_Admin/manifest.yaml` (add required fields)
- **Dependencies:** PKG-KERNEL-001, PKG-LAYOUT-002, PKG-BOOT-MATERIALIZE-001

### PKG-FRAMEWORK-WIRING-001 (Layer 2)
- **Spec:** SPEC-CORE-001, **Framework:** FMWK-000, **Plane:** hot
- **Modified asset:** `HOT/tests/test_framework_wiring.py` (expect 5 frameworks)
- **Dependencies:** PKG-KERNEL-001

## 6. Test Plan

No new test files. The 24 previously-failing tests become the verification:

### test_boot_materialize.py (15 tests — all should now PASS)

| Test | Validates |
|------|-----------|
| `test_fresh_boot_creates_ho2_directories` | HO2 dirs created from layout.json |
| `test_fresh_boot_creates_ho1_directories` | HO1 dirs created from layout.json |
| `test_fresh_boot_creates_ho2_tier_json` | HO2 tier.json written |
| `test_fresh_boot_creates_ho1_tier_json` | HO1 tier.json written |
| `test_ho2_tier_json_parent_is_hot` | HO2 parent ledger → HOT |
| `test_ho1_tier_json_parent_is_ho2` | HO1 parent ledger → HO2 |
| `test_hot_genesis_created_if_empty` | HOT genesis event written |
| `test_ho2_genesis_created` | HO2 genesis event written |
| `test_ho1_genesis_created` | HO1 genesis event written |
| `test_genesis_chain_ho2_to_hot` | HO2 genesis hash chains to HOT |
| `test_genesis_chain_ho1_to_ho2` | HO1 genesis hash chains to HO2 |
| `test_chain_verification_passes` | Cross-tier chain verification |
| `test_idempotent_second_boot` | Double boot doesn't duplicate genesis |
| `test_partial_recovery_missing_ho1_only` | Recovery when HO1 deleted |
| `test_paths_derived_from_layout_json` | Custom tier names work |

(2 additional tests — `test_returns_zero_on_success` and `test_returns_one_on_missing_layout_json` — were also affected by collection error.)

### test_admin.py (3 tests in affected classes — all should now PASS)

| Test | Validates |
|------|-----------|
| `test_boot_materialize_runs_under_pristine_bypass` | Boot materialize runs during CLI startup |
| `test_boot_materialize_called_before_session_host_v2` | Boot → build → run ordering |
| `test_pristine_patch_stopped_on_exit` | Pristine guard restored after boot |

(4 additional TestAdminConfig + 4 TestAdminEntrypoint tests were also affected by collection error.)

### test_framework_wiring.py (6 tests — all should now PASS)

| Test | Validates |
|------|-----------|
| `test_exactly_four_frameworks` → `test_exactly_five_frameworks` | 5 FMWK dirs exist |
| `test_has_expected_specs` (FMWK-005) | manifest has expected_specs |
| `test_has_ring` (FMWK-005) | manifest has ring field |
| `test_has_invariants` (FMWK-005) | manifest has invariants |
| `test_has_required_gates` (FMWK-005) | manifest has required_gates |
| `test_expected_specs_declared` (FMWK-005) | declared specs match wiring |

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| FMWK-007 manifest (template) | `_staging/PKG-KERNEL-001/HOT/FMWK-007_Package_Management/manifest.yaml` | Schema reference for FMWK-005 fix |
| Current test_boot_materialize.py | `_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py` | Lines 14-25 to replace |
| Current test_admin.py | `_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` | Lines 14-15 and 69-75 to replace |
| Current test_framework_wiring.py | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/tests/test_framework_wiring.py` | Lines 26-33 and 88-93 to update |
| Current FMWK-005 manifest | `_staging/PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml` | Current state (9 lines, missing fields) |
| hashing.py | `_staging/PKG-KERNEL-001/HOT/kernel/hashing.py` | `compute_sha256()` for manifest hash updates |
| packages.py | `_staging/PKG-KERNEL-001/HOT/kernel/packages.py` | `pack()` for archive rebuilds |
| Installed CP_2.1 layout | `/Users/raymondbruni/Brain_Garden/playground/CP_2.1/HOT/` | Reference for what the installed tree looks like |

## 8. End-to-End Verification

```bash
# Step 1: Clean-room install
TMPDIR=$(mktemp -d)
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
mkdir -p "$TMPDIR/INSTALL_ROOT"
bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev
# Expected: 20 packages installed, 8/8 gates PASS

# Step 2: Run previously-failing tests
IR="$TMPDIR/INSTALL_ROOT"
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 -m pytest "$IR/HOT/tests/test_boot_materialize.py" \
                    "$IR/HOT/tests/test_admin.py" \
                    "$IR/HOT/tests/test_framework_wiring.py" -v
# Expected: 24+ tests, ALL PASS

# Step 3: Full test suite
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 -m pytest "$IR/HOT/tests/" -v
# Expected: 444+ tests, 0 failures

# Step 4: Gate check
PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts" \
  python3 "$IR/HOT/scripts/gate_check.py" --root "$IR" --all --enforce
# Expected: 8/8 gates PASS

# Step 5: E2E smoke (optional but recommended)
echo "hello" | PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" \
  python3 "$IR/HOT/admin/main.py" --root "$IR" --dev
# Expected: Kitchener loop produces a response
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `test_boot_materialize.py` | `_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/` | MODIFY (path detection) |
| `test_admin.py` | `_staging/PKG-ADMIN-001/HOT/tests/` | MODIFY (path detection + layout helper) |
| `test_framework_wiring.py` | `_staging/PKG-FRAMEWORK-WIRING-001/HOT/tests/` | MODIFY (expect 5 FMWKs) |
| `manifest.yaml` | `_staging/PKG-ADMIN-001/HOT/FMWK-005_Admin/` | MODIFY (add required fields) |
| `manifest.json` | `_staging/PKG-BOOT-MATERIALIZE-001/` | MODIFY (update SHA256) |
| `manifest.json` | `_staging/PKG-ADMIN-001/` | MODIFY (update SHA256) |
| `manifest.json` | `_staging/PKG-FRAMEWORK-WIRING-001/` | MODIFY (update SHA256) |
| `PKG-BOOT-MATERIALIZE-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-ADMIN-001.tar.gz` | `_staging/` | REBUILD |
| `PKG-FRAMEWORK-WIRING-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |
| `RESULTS_HANDOFF_20.md` | `_staging/handoffs/` | CREATE |

## 10. Design Principles

- **Dual-context detection over parent-counting.** Filesystem probing (`file.exists()`) is robust across layouts. Parent-level counting is fragile and broke when the directory structure changed.
- **Self-contained tests.** Each test file resolves its own imports. No shared conftest.py coupling across packages.
- **Schema compliance.** Every framework manifest must have ALL required fields. Incomplete manifests cause cascading test failures in framework wiring tests.
- **Backward-compatible.** Changes must not break staging tests. The dual-context branch preserves the existing staging path logic.
- **Minimal diff.** Only change the path resolution blocks. Do not refactor test logic, rename tests, or add new tests. The goal is to fix what's broken, not improve what works.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**Agent: HANDOFF-20** — Fix 24 pre-existing test failures caused by staging-vs-installed path mismatch and incomplete FMWK-005 manifest.

Read your specification, answer the 10 questions below, then STOP and WAIT for approval.

**Specification:**
`Control_Plane_v2/_staging/handoffs/BUILDER_HANDOFF_20_test_cleanup.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars total). Bare hex will fail G0A.
5. Clean-room verification: Extract CP_BOOTSTRAP.tar.gz to temp dir → run install.sh → install to temp root → ALL gates must pass. This is NOT optional.
6. Full regression: Run ALL installed tests (not just the 3 you modified). Report total count, pass/fail, and whether you introduced new failures.
7. Results file: Write `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_20.md` following the FULL template in BUILDER_HANDOFF_STANDARD.md. MUST include: Clean-Room Verification section, Baseline Snapshot section, Full Regression section. Missing sections = incomplete handoff.
8. Registry updates: If your changes affect framework registries, update frameworks_registry.csv.
9. CP_BOOTSTRAP rebuild: Rebuild CP_BOOTSTRAP.tar.gz with updated package archives and report member count and SHA256.
10. Built-in tools: Use `hashing.py:compute_sha256()` for all SHA256 hashes and `packages.py:pack()` for all archives. NEVER use raw hashlib or shell tar. See "Required Kernel Tools" in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. Which 3 test files are you modifying, and which staging package directory does each live in?
2. What is the root cause of the 15 test_boot_materialize.py failures? Specifically, what does `Path(__file__).resolve().parents[3]` resolve to from the installed root vs. staging?
3. How does your dual-context detection work? What file existence do you check, and why is that probe unambiguous?
4. For test_admin.py, which additional sys.path entries are needed in the installed context beyond `HOT/admin/`? Why?
5. What 6 fields is FMWK-005's manifest.yaml missing, and what file do you use as the schema template?
6. In test_framework_wiring.py, what TWO changes are needed — one to the wiring dict and one to the assertion?
7. After modifying the 4 source files, what are the 3 manifest.json files you must update with new SHA256 hashes? What tool do you use?
8. How many .tar.gz archives do you rebuild (list them), and what tool do you use for packing?
9. How many total tests do you expect to pass after your changes? How many were passing before?
10. What PYTHONPATH do you need to set when running tests from the installed root, and why is it necessary?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

### Expected Answers

1. `test_boot_materialize.py` in `PKG-BOOT-MATERIALIZE-001/HOT/tests/`, `test_admin.py` in `PKG-ADMIN-001/HOT/tests/`, `test_framework_wiring.py` in `PKG-FRAMEWORK-WIRING-001/HOT/tests/`.
2. From installed root (`CP_2.1/HOT/tests/`), `parents[3]` = `playground/`. From staging (`_staging/PKG-*/HOT/tests/`), `parents[3]` = `_staging/`. `playground/` has no `PKG-*` directories, so `LAYOUT_SOURCE` and all sys.path entries point to nonexistent paths.
3. Check `(_HOT / "kernel" / "ledger_client.py").exists()` where `_HOT = Path(__file__).resolve().parent.parent`. In installed root, `HOT/kernel/ledger_client.py` exists (all kernel modules merged). In staging, the PKG-specific HOT directory has no kernel subdirectory. Unambiguous because kernel modules only exist in PKG-KERNEL-001, never in PKG-BOOT-MATERIALIZE-001 or PKG-ADMIN-001. IMPORTANT: Use this same probe for ALL 3 test files — do NOT use `admin/main.py` for test_admin.py because it exists in both contexts (ambiguous).
4. `HOT/kernel` (for `ledger_client`, `hashing`, etc.), `HOT/scripts` (for `boot_materialize`), `HOT` (for `kernel` as a package). admin/main.py imports from these transitively.
5. 8 fields missing or misnamed: `title` (has `name` instead), `ring`, `created_at`, `assets`, `expected_specs`, `invariants`, `path_authorizations`, `required_gates`. Tests enforce 4 of these (`ring`, `expected_specs`, `invariants`, `required_gates`); fix all 8 for full schema compliance. Template: `FMWK-007_Package_Management/manifest.yaml` in PKG-FRAMEWORK-WIRING-001.
6. (a) Add `"FMWK-005": []` to `EXPECTED_WIRING` dict. (b) Change assertion from `["FMWK-000", "FMWK-001", "FMWK-002", "FMWK-007"]` to `["FMWK-000", "FMWK-001", "FMWK-002", "FMWK-005", "FMWK-007"]`.
7. `PKG-BOOT-MATERIALIZE-001/manifest.json`, `PKG-ADMIN-001/manifest.json`, `PKG-FRAMEWORK-WIRING-001/manifest.json`. Use `hashing.py:compute_sha256()`.
8. 4 archives: `PKG-BOOT-MATERIALIZE-001.tar.gz`, `PKG-ADMIN-001.tar.gz`, `PKG-FRAMEWORK-WIRING-001.tar.gz`, `CP_BOOTSTRAP.tar.gz`. Use `packages.py:pack()` for the first 3, then assemble CP_BOOTSTRAP.
9. 444+ total (420 previously passing + 24 fixed). Before: 420 pass, 24 fail.
10. `$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel`. Necessary because the installed root has no conftest.py or setup.py — Python doesn't know where to find modules without explicit paths.
