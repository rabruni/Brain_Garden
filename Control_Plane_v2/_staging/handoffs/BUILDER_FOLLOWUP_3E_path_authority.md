# Builder Follow-Up #3E: Path Authority Consolidation

## 1. Mission

Fix the path authority problem: layout.json declares `HOT/ledger` and `HOT/registries` as canonical paths, but package_install.py writes to `$ROOT/ledger` and `$ROOT/registries` (outside HOT). gate_check.py has dual-path fallback logic trying both locations. ledger_client.py computes its path relative to `__file__`. The result: 4 competing sources of truth for paths, and the ledger ends up in the wrong place.

**Goal:** Make layout.json the single authority. All hardcoded paths must match what layout.json declares. Fix the two critical bugs (package_install.py lines 88-89) and align all ledger/registry path references across PKG-KERNEL-001 and PKG-VOCABULARY-001.

Also fix layout.json itself: it declares HO3 as a tier (HO3 is dead — only HOT, HO2, HO1 exist).

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree.
2. **DTT: Design -> Test -> Then implement.** Write tests FIRST.
3. **Package everything.** Edit existing packages in `_staging/PKG-<NAME>/`, rebuild archives.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> install Layers 0-2 (8 packages). All gates must pass. Ledger must be in `HOT/ledger/`, NOT `$ROOT/ledger/`.
5. **No hardcoding of NEW paths.** Use the pattern: try Layout class, fall back to constant that matches layout.json.
6. **No file replacement.** No new packages that overwrite existing files.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` -- NEVER `tar czf ... -C dir .`
8. **Results file.** When finished, write `_staging/RESULTS_FOLLOWUP_3E.md`.
9. **Full regression test.** Run ALL staged package tests.
10. **Baseline snapshot.** Include package count, file_ownership rows, test count, gate results.
11. **Bootstrap circularity:** Layer 0 code (genesis_bootstrap.py, package_install.py) runs BEFORE layout.json is installed (Layer 2). These files MUST have hardcoded defaults. The defaults must match layout.json. Do NOT add an import dependency on Layout class in Layer 0 code.
12. **Verify ledger location:** After clean-room install, `$ROOT/HOT/ledger/` must exist with ledger files. `$ROOT/ledger/` must NOT exist.

## 3. Architecture / Design

### The Problem

4 sources of truth:

| Source | Location | What it says |
|--------|----------|-------------|
| layout.json | PKG-LAYOUT-001 | `"ledger": "HOT/ledger"`, `"registries": "HOT/registries"` |
| paths.py | PKG-KERNEL-001 | `REGISTRIES_DIR = CONTROL_PLANE / "HOT" / "registries"` (correct via Layout fallback) |
| package_install.py | PKG-KERNEL-001 | `L_PACKAGE_LEDGER = CONTROL_PLANE / "ledger"` (WRONG -- missing HOT/) |
| gate_check.py | PKG-VOCABULARY-001 | Tries `plane_root / 'registries'` first, falls back to `plane_root / 'HOT' / 'registries'` (backwards) |

### The Fix

**Principle:** Hardcoded defaults MUST match layout.json. No "try root, fall back to HOT" -- HOT is correct, use it directly.

**paths.py:** Add `LEDGER_DIR` alongside `REGISTRIES_DIR`, both using Layout class with fallback to `CONTROL_PLANE / "HOT" / <dir>`.

**package_install.py:** Replace inline path construction with paths.py constants.

**gate_check.py:** Remove dual-path fallback. Use `HOT/registries` and `HOT/ledger` directly.

**ledger_client.py:** Fix `DEFAULT_LEDGER_PATH` to use `HOT/ledger` explicitly.

**layout.json:** Remove HO3 from tiers.

### Bootstrap Circularity

genesis_bootstrap.py (Layer 0) hardcodes `"HOT/registries"` on line 215. This is CORRECT -- it matches layout.json. Do NOT change genesis_bootstrap.py.

package_install.py (Layer 0) imports from paths.py which tries Layout class first. During Layer 0-1 install, Layout import fails (layout.json doesn't exist yet), so the fallback fires: `CONTROL_PLANE / "HOT" / "registries"`. This is correct. After Layer 2, Layout class works. Both paths agree with layout.json.

## 4. Implementation Steps

### Step 1: Fix paths.py (PKG-KERNEL-001)

File: `_staging/PKG-KERNEL-001/HOT/kernel/paths.py`

Add `LEDGER_DIR` after `REGISTRIES_DIR` (after line 108):

```python
try:
    from kernel.layout import LAYOUT as _LAYOUT
    REGISTRIES_DIR = _LAYOUT.hot.registries
except Exception:
    REGISTRIES_DIR = CONTROL_PLANE / "HOT" / "registries"

try:
    from kernel.layout import LAYOUT as _LAYOUT_L
    LEDGER_DIR = _LAYOUT_L.hot.ledger
except Exception:
    LEDGER_DIR = CONTROL_PLANE / "HOT" / "ledger"
```

### Step 2: Fix package_install.py (PKG-KERNEL-001)

File: `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py`

Line 42 (imports): Add `LEDGER_DIR` to the import:
```python
from kernel.paths import CONTROL_PLANE, REGISTRIES_DIR, LEDGER_DIR
```

Lines 88-89 (constants): Change from:
```python
PKG_REG = CONTROL_PLANE / "registries" / "packages_registry.csv"
L_PACKAGE_LEDGER = CONTROL_PLANE / "ledger" / "packages.jsonl"
```

To:
```python
PKG_REG = REGISTRIES_DIR / "packages_registry.csv"
L_PACKAGE_LEDGER = LEDGER_DIR / "packages.jsonl"
```

### Step 3: Fix ledger_client.py (PKG-KERNEL-001)

File: `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py`

Line 71: Change from:
```python
DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent / "ledger" / "governance.jsonl"
```

To:
```python
try:
    from kernel.paths import LEDGER_DIR as _LDIR
    DEFAULT_LEDGER_PATH = _LDIR / "governance.jsonl"
except Exception:
    DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent / "ledger" / "governance.jsonl"
```

Note: The fallback (`parent.parent / "ledger"`) resolves to `HOT/ledger` because `__file__` is in `HOT/kernel/`. So the fallback was actually correct by accident -- it just wasn't explicit. The new code makes the intent clear.

### Step 4: Fix gate_check.py (PKG-VOCABULARY-001)

File: `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py`

**Lines 95-98** (load_control_plane_registry): Change dual-path to direct:
```python
registry_path = plane_root / 'HOT' / 'registries' / 'control_plane_registry.csv'
```
Remove the fallback to `plane_root / 'registries'`.

**Lines 132-135** (load_file_ownership_registry): Same fix:
```python
registry_path = plane_root / 'HOT' / 'registries' / 'file_ownership.csv'
```
Remove the fallback to `plane_root / 'registries'`.

**Line 544** (check_g2_work_orders): Change:
```python
governance_ledger = plane_root / 'HOT' / 'ledger' / 'governance.jsonl'
```

**Line 775** (check_g6_ledger fallback): Change:
```python
ledger_dir = plane_root / 'HOT' / 'ledger'
```

### Step 5: Fix layout.json (PKG-LAYOUT-001)

File: `_staging/PKG-LAYOUT-001/HOT/config/layout.json`

Remove HO3 from tiers:
```json
"tiers": {
    "HOT": "HOT",
    "HO2": "HO2",
    "HO1": "HO1"
}
```

Also fix this in the identical copy: `_staging/PKG-KERNEL-001/HOT/config/layout.json` (if it exists).

### Step 6: Rebuild archives

1. Recompute SHA256 for all changed files
2. Update manifest.json in PKG-KERNEL-001 and PKG-VOCABULARY-001 and PKG-LAYOUT-001
3. Rebuild PKG-KERNEL-001.tar.gz, PKG-VOCABULARY-001.tar.gz, PKG-LAYOUT-001.tar.gz
4. Rebuild CP_BOOTSTRAP.tar.gz (use Python tarfile, packages/ subdirectory structure)

### Step 7: Clean-room verification

```bash
INSTALL_DIR=$(mktemp -d)
EXTRACT_DIR=$(mktemp -d)
tar xzf _staging/CP_BOOTSTRAP.tar.gz -C "$EXTRACT_DIR"
bash "$EXTRACT_DIR/install.sh" --root "$INSTALL_DIR" --dev

# Verify: ledger is in HOT/ledger, NOT at root
ls "$INSTALL_DIR/HOT/ledger/"           # Should show governance-*.jsonl, packages.jsonl
ls "$INSTALL_DIR/ledger/" 2>/dev/null   # Should NOT exist (or be empty)

# All gates pass
python3 "$INSTALL_DIR/HOT/scripts/gate_check.py" --root "$INSTALL_DIR" --all
# Expected: 8/8 PASS
```

## 5. Package Plan

No new packages. Edits to 3 existing packages:

| Package | Files Changed | Archive to Rebuild |
|---------|--------------|-------------------|
| PKG-KERNEL-001 | paths.py, package_install.py, ledger_client.py | PKG-KERNEL-001.tar.gz |
| PKG-VOCABULARY-001 | gate_check.py | PKG-VOCABULARY-001.tar.gz |
| PKG-LAYOUT-001 | layout.json | PKG-LAYOUT-001.tar.gz |

Plus CP_BOOTSTRAP.tar.gz (contains all three).

## 6. Test Plan

Write: `_staging/test_followup_3e.py`

| Test | Description | Expected |
|------|-------------|----------|
| test_paths_ledger_dir_exists | LEDGER_DIR exported from paths.py | LEDGER_DIR is a Path |
| test_paths_ledger_dir_in_hot | LEDGER_DIR path contains "HOT/ledger" | True |
| test_paths_registries_dir_in_hot | REGISTRIES_DIR path contains "HOT/registries" | True |
| test_package_install_pkg_reg_in_hot | PKG_REG path contains "HOT/registries" | True |
| test_package_install_ledger_in_hot | L_PACKAGE_LEDGER path contains "HOT/ledger" | True |
| test_ledger_client_default_path_in_hot | DEFAULT_LEDGER_PATH contains "HOT/ledger" | True |
| test_gate_check_no_root_registries_fallback | gate_check.py does not try plane_root/'registries' first | grep check |
| test_gate_check_no_root_ledger_fallback | gate_check.py does not try plane_root/'ledger' without HOT | grep check |
| test_layout_json_no_ho3 | layout.json tiers does not include HO3 | True |
| test_layout_json_tiers_correct | layout.json tiers are exactly HOT, HO2, HO1 | True |
| test_clean_install_ledger_in_hot | After clean-room install, HOT/ledger/ exists with files | True |
| test_clean_install_no_root_ledger | After clean-room install, $ROOT/ledger/ does not exist | True |

Minimum 12 tests.

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| paths.py (current) | `_staging/PKG-KERNEL-001/HOT/kernel/paths.py` | Add LEDGER_DIR next to REGISTRIES_DIR |
| package_install.py | `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py` | Fix lines 88-89 |
| ledger_client.py | `_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` | Fix line 71 |
| gate_check.py | `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py` | Fix lines 95-98, 132-135, 544, 775 |
| layout.json | `_staging/PKG-LAYOUT-001/HOT/config/layout.json` | Remove HO3 |
| FOLLOWUP-3D results | `_staging/RESULTS_FOLLOWUP_3D.md` | Baseline to diff against |

## 8. End-to-End Verification

```bash
# 1. Validate JSON
python3 -c "import json; json.load(open('Control_Plane_v2/_staging/PKG-LAYOUT-001/HOT/config/layout.json')); print('layout.json OK')"

# 2. Run 3E tests
python3 -m pytest Control_Plane_v2/_staging/test_followup_3e.py -v

# 3. Clean-room install
INSTALL_DIR=$(mktemp -d)
EXTRACT_DIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$INSTALL_DIR"
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$EXTRACT_DIR"
bash "$EXTRACT_DIR/install.sh" --root "$INSTALL_DIR" --dev

# 4. Verify ledger location
test -d "$INSTALL_DIR/HOT/ledger" && echo "PASS: HOT/ledger exists"
test ! -d "$INSTALL_DIR/ledger" && echo "PASS: root/ledger does not exist"

# 5. All gates pass
python3 "$INSTALL_DIR/HOT/scripts/gate_check.py" --root "$INSTALL_DIR" --all

# 6. Full regression tests
CONTROL_PLANE_ROOT="$INSTALL_DIR" python3 -m pytest "$INSTALL_DIR/HOT/tests/" -v
```

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| paths.py | `_staging/PKG-KERNEL-001/HOT/kernel/` | EDIT: add LEDGER_DIR |
| package_install.py | `_staging/PKG-KERNEL-001/HOT/scripts/` | EDIT: fix lines 88-89 |
| ledger_client.py | `_staging/PKG-KERNEL-001/HOT/kernel/` | EDIT: fix line 71 |
| gate_check.py | `_staging/PKG-VOCABULARY-001/HOT/scripts/` | EDIT: fix 4 path references |
| layout.json | `_staging/PKG-LAYOUT-001/HOT/config/` | EDIT: remove HO3 |
| layout.json | `_staging/PKG-KERNEL-001/HOT/config/` | EDIT: remove HO3 (if exists) |
| test_followup_3e.py | `_staging/` | CREATE |
| PKG-KERNEL-001.tar.gz | `_staging/` | REBUILD |
| PKG-VOCABULARY-001.tar.gz | `_staging/` | REBUILD |
| PKG-LAYOUT-001.tar.gz | `_staging/` | REBUILD |
| CP_BOOTSTRAP.tar.gz | `_staging/` | REBUILD |
| RESULTS_FOLLOWUP_3E.md | `_staging/` | CREATE |

## 10. Design Principles

- **layout.json is the single source of truth for paths.** All code must agree with it.
- **Hardcoded defaults match layout.json.** No "try wrong path, fall back to right path."
- **Layer 0 uses hardcoded defaults.** Cannot import Layout class (circular dependency). Defaults must match layout.json.
- **No dual-path fallback logic.** `HOT/registries` is correct. Don't also try `registries/`.
- **HO3 is dead.** Only 3 tiers: HOT, HO2, HO1. Remove all HO3 references.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY -- print this FIRST before doing anything else:**
> **Agent: FOLLOWUP-3E** -- Path authority consolidation: fix ledger/registry paths to match layout.json

**Read this file FIRST -- it is your complete specification:**
`Control_Plane_v2/_staging/BUILDER_FOLLOWUP_3E_path_authority.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design -> Test -> Then implement. Write tests FIRST.
3. Tar archive format: NEVER use `tar czf ... -C dir .` -- use Python tarfile module with explicit arcname.
4. CP_BOOTSTRAP.tar.gz must have packages/ subdirectory structure (3 docs at top, 8 archives in packages/).
5. End-to-end: clean-room install must show ledger at HOT/ledger/ (not root/ledger/).
6. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_FOLLOWUP_3E.md`.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What TWO lines in package_install.py are wrong, and what should they be?
2. What constant are you adding to paths.py, and what is its fallback value?
3. Why can't package_install.py import the Layout class directly?
4. In gate_check.py, what is the dual-path fallback pattern you're removing?
5. What is the correct ledger path according to layout.json?
6. What tier is being removed from layout.json, and why?
7. How many packages are you editing (not creating)?
8. After clean-room install, what directory must NOT exist at $ROOT?
9. How many tests are you writing, and what do the last two verify?
10. What archive structure does CP_BOOTSTRAP.tar.gz use (top-level files vs packages)?

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and says go.
```

### Expected Answers

1. Line 88: `PKG_REG = CONTROL_PLANE / "registries" / ...` -> `REGISTRIES_DIR / ...`; Line 89: `L_PACKAGE_LEDGER = CONTROL_PLANE / "ledger" / ...` -> `LEDGER_DIR / ...`
2. LEDGER_DIR, fallback: `CONTROL_PLANE / "HOT" / "ledger"`
3. Bootstrap circularity: package_install.py runs during Layer 0-1, Layout class needs layout.json which ships in Layer 2
4. Tries `plane_root / 'registries'` first, then falls back to `plane_root / 'HOT' / 'registries'` -- removes the first try, uses HOT/ directly
5. `HOT/ledger` (from hot_dirs.ledger in layout.json)
6. HO3 -- it was a prior agent mistake, only 3 tiers exist: HOT, HO2, HO1
7. 3 packages: PKG-KERNEL-001, PKG-VOCABULARY-001, PKG-LAYOUT-001
8. `$ROOT/ledger/` -- ledger must be at `$ROOT/HOT/ledger/` only
9. 12 tests; last two: test_clean_install_ledger_in_hot (HOT/ledger exists with files) and test_clean_install_no_root_ledger ($ROOT/ledger does not exist)
10. Top level: README.md, INSTALL.md, install.sh; packages/ subdirectory: 8 .tar.gz archives
