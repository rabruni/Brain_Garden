# Builder Follow-Up #3D: Fix Genesis File Registration + Remove Phantom G0K Gate

## Mission

Fix two foundational issues that create permanent gate failures in every clean-room install:

1. **G0B genesis orphans**: 4 genesis files (genesis_bootstrap.py, bootstrap_sequence.json, seed_registry.json, package_manifest_l0.json) are never registered in file_ownership.csv. The registration code (genesis_bootstrap.py lines 236-248) is dead — it reads from a path that doesn't exist.

2. **Phantom G0K gate**: gate_check.py unconditionally includes G0K (kernel parity) in the `--all` gate sequence, but the module `g0k_gate.py` doesn't exist. This causes a permanent FAIL that normalizes seeing failures in gate output — the opposite of what gates are for.

**Packages modified:** PKG-GENESIS-000 (genesis_bootstrap.py) and PKG-KERNEL-001 (gate_check.py, via PKG-VOCABULARY-001 staged copy).

---

## Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST.
3. **These are Layer 0 packages.** Changes require rebuilding PKG-GENESIS-000.tar.gz, PKG-KERNEL-001.tar.gz (if genesis_bootstrap.py is in it), PKG-VOCABULARY-001.tar.gz (gate_check.py), AND CP_BOOTSTRAP.tar.gz.
4. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .`
5. **End-to-end verification.** After rebuilding, run the full install chain: extract CP_BOOTSTRAP.tar.gz → install Layers 0-2 (8 packages). G0B must show 0 orphans. G0K must NOT appear in output.
6. **No file replacement across packages.** Both fixes are edits to files within their own packages.
7. **Results file.** When finished, write `_staging/RESULTS_FOLLOWUP_3D.md`.

---

## Root Cause Analysis

### Issue 1: Genesis Orphans

**How PKG-GENESIS-000 is installed:**

PKG-GENESIS-000 is extracted by `install.sh` using plain `tar xzf` (step 4). It is NOT installed via `install_package()`. This is by design — genesis_bootstrap.py is INSIDE PKG-GENESIS-000, so you can't use it to install itself.

**What happens next:**

`genesis_bootstrap.py` is called with `--archive PKG-KERNEL-001.tar.gz`. Inside `install_package()`:
1. `extract_archive()` extracts kernel files (line 452)
2. `write_install_receipt()` writes `HOT/installed/PKG-KERNEL-001/receipt.json` (line 462)
3. `write_file_ownership()` creates `file_ownership.csv` with ONLY kernel files (line 474)
4. Lines 236-248 attempt to register genesis files by reading `HOT/installed/PKG-GENESIS-000/manifest.json`

**Why line 237 is dead code:**

```python
genesis_manifest = root / "HOT" / "installed" / "PKG-GENESIS-000" / "manifest.json"
```

This path never exists because:
- PKG-GENESIS-000 was tar-extracted, not installed via `install_package()`
- No receipt directory `HOT/installed/PKG-GENESIS-000/` is ever created
- Even if it were, `write_install_receipt()` writes `receipt.json`, not `manifest.json`

**Result:** The 5 genesis files are on disk but unregistered. G0B sees them as orphans.

### Issue 2: Phantom G0K

**Where G0K lives in gate_check.py:**

- `check_g0k_kernel_parity()` function (lines 742-788): tries `from scripts.g0k_gate import run_g0k_gate`, catches ImportError, returns FAIL
- `GATE_FUNCTIONS` dict (line 907): maps `"G0K"` to the function
- `"all"` gate ordering (line 946): includes G0K as the FIRST gate

**Why it shouldn't be there:**

G0K checks kernel parity across tiers (HOT, HO2, HO1). This is meaningful only when multi-tier deployment exists — which is a future capability. Currently all packages target `plane_id: "hot"`. The gate was speculatively added and always fails.

---

## The Fix

### Fix 1: Genesis File Registration

**Strategy:** After `write_file_ownership()` creates file_ownership.csv with kernel files, read the genesis package's manifest **from the original archive** (not from a non-existent receipt directory), and register all genesis files.

**Why "from the archive":** The genesis archive (`PKG-GENESIS-000.tar.gz`) is sitting right there in the same bootstrap directory. The manifest.json is inside it (even though `extract_archive` skips it during extraction). We can read it from the tar and use it to register genesis files.

**Alternative (simpler):** Since `install.sh` already knows the genesis file list (it just extracted them), we could have `genesis_bootstrap.py` accept a `--genesis-archive` argument pointing to PKG-GENESIS-000.tar.gz. Then it reads the manifest from that archive and registers all 5 genesis files.

**Chosen approach:** Add `--genesis-archive <path>` argument to genesis_bootstrap.py. When provided, the script:
1. Reads manifest.json from the genesis archive
2. After creating file_ownership.csv with kernel files, appends genesis file rows
3. Also writes a receipt for PKG-GENESIS-000 at `HOT/installed/PKG-GENESIS-000/receipt.json`

This is cleaner than hardcoding genesis file paths or relying on filesystem discovery. The manifest is the source of truth.

**Changes to install.sh:** Add `--genesis-archive` to the genesis_bootstrap.py invocation:
```bash
python3 "$ROOT/HOT/scripts/genesis_bootstrap.py" \
    --seed "$ROOT/HOT/config/seed_registry.json" \
    --archive "$BOOTSTRAP_DIR/PKG-KERNEL-001.tar.gz" \
    --genesis-archive "$BOOTSTRAP_DIR/PKG-GENESIS-000.tar.gz"
```

### Fix 2: Remove G0K

Remove entirely from gate_check.py:
1. Delete `check_g0k_kernel_parity()` function (lines 742-788)
2. Remove `"G0K": check_g0k_kernel_parity` from GATE_FUNCTIONS (line 907)
3. Remove `"G0K"` from the `"all"` gate ordering (line 946)

When kernel parity is actually needed (first HO2 package), it gets introduced with its own package that ships `g0k_gate.py` AND adds G0K to the gate registry.

---

## Implementation Steps

### Step 1: Edit genesis_bootstrap.py

**File:** `_staging/PKG-GENESIS-000/HOT/scripts/genesis_bootstrap.py`

**1a. Add `--genesis-archive` argument to main()** (after the `--verify-only` argument, around line 539):
```python
parser.add_argument(
    "--genesis-archive",
    help="Path to PKG-GENESIS-000.tar.gz (registers genesis files in file_ownership.csv)"
)
```

**1b. Pass genesis_archive to install_package()** (around line 600):
```python
return install_package(
    archive=archive,
    seed_entry=entry,
    root=root,
    force=args.force,
    verify_only=args.verify_only,
    genesis_archive=Path(args.genesis_archive) if args.genesis_archive else None,
)
```

**1c. Update install_package signature** (line 373):
```python
def install_package(
    archive: Path,
    seed_entry: Dict[str, Any],
    root: Path,
    force: bool = False,
    verify_only: bool = False,
    genesis_archive: Optional[Path] = None,
) -> int:
```

**1d. Replace the dead genesis registration code** (lines 236-248 in `write_file_ownership`):

Remove lines 236-248 entirely. Instead, add genesis registration in `install_package()` after `write_file_ownership()` (after line 480):

```python
# Register genesis files from genesis archive (if provided)
if genesis_archive and genesis_archive.exists():
    print("  Registering genesis files...")
    genesis_file_count = register_genesis_files(genesis_archive, root, ownership_path)
    print(f"  Registered {genesis_file_count} genesis files")

    # Write genesis receipt
    genesis_manifest = load_manifest_from_archive(genesis_archive)
    if genesis_manifest:
        genesis_files_list = [a["path"] for a in genesis_manifest.get("assets", [])]
        genesis_receipt = write_install_receipt(
            pkg_id="PKG-GENESIS-000",
            version=genesis_manifest.get("version", "0.0.0"),
            archive_path=genesis_archive,
            files=genesis_files_list,
            root=root,
            installer="genesis_bootstrap"
        )
        print(f"  Genesis receipt: {genesis_receipt}")
```

**1e. Add `register_genesis_files()` function** (new helper, place after `write_file_ownership`):

```python
def register_genesis_files(
    genesis_archive: Path,
    root: Path,
    ownership_csv: Path,
) -> int:
    """Register genesis package files in file_ownership.csv.

    Reads manifest.json from the genesis archive and appends
    ownership rows for each genesis file.

    Args:
        genesis_archive: Path to PKG-GENESIS-000.tar.gz
        root: Control Plane root
        ownership_csv: Path to file_ownership.csv

    Returns:
        Number of genesis files registered
    """
    manifest = load_manifest_from_archive(genesis_archive)
    if not manifest:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    count = 0

    with open(ownership_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for asset in manifest.get("assets", []):
            g_path = asset.get("path", "")
            g_full = root / g_path
            if g_full.exists() and g_full.is_file():
                g_digest = sha256_file(g_full)
                g_class = asset.get("classification", "genesis")
                writer.writerow([g_path, "PKG-GENESIS-000", g_digest, g_class, now, "", ""])
                count += 1

    return count


def load_manifest_from_archive(archive: Path) -> Optional[Dict[str, Any]]:
    """Read manifest.json from inside a tar.gz archive.

    Args:
        archive: Path to tar.gz archive

    Returns:
        Parsed manifest dict, or None if not found
    """
    try:
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf.getmembers():
                if member.name == "manifest.json" or (
                    member.name.endswith("/manifest.json") and member.name.count("/") <= 1
                ):
                    mf = tf.extractfile(member)
                    if mf:
                        return json.load(mf)
    except (tarfile.TarError, json.JSONDecodeError):
        pass
    return None
```

**Note:** `load_manifest_from_archive` is extracted from the existing inline code at lines 437-448. This is a refactor of duplicate logic, not new functionality.

**1f. Remove the dead code at lines 236-248** in `write_file_ownership()`. Delete:
```python
    # Register genesis package files (from installed manifest if available)
    genesis_manifest = root / "HOT" / "installed" / "PKG-GENESIS-000" / "manifest.json"
    if genesis_manifest.exists():
        gm = json.loads(genesis_manifest.read_text(encoding="utf-8"))
        for asset in gm.get("assets", []):
            g_path = asset.get("path", "")
            g_full = root / g_path
            if g_full.exists() and g_full.is_file():
                g_digest = sha256_file(g_full)
                g_class = asset.get("classification", "genesis")
                with open(ownership_csv, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([g_path, "PKG-GENESIS-000", g_digest, g_class, now, "", ""])
```

**1g. Replace the inline manifest-reading code** at lines 435-448 in `install_package()` with a call to `load_manifest_from_archive()`:
```python
    # Load manifest from archive for classification data
    manifest = load_manifest_from_archive(archive)
```

### Step 2: Edit gate_check.py

**File:** `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py`

**2a. Delete the `check_g0k_kernel_parity()` function** (lines 742-788)

**2b. Remove G0K from GATE_FUNCTIONS** (line 907):
```python
# Before:
"G0K": check_g0k_kernel_parity,        # Kernel parity (Phase 4)

# After: (line deleted)
```

**2c. Remove G0K from the `"all"` gate ordering** (line 946):
```python
# Before:
gates = ["G0K", "G0B", "G1", "G1-COMPLETE", "G2", "G3", "G4", "G5", "G6"]

# After:
gates = ["G0B", "G1", "G1-COMPLETE", "G2", "G3", "G4", "G5", "G6"]
```

**2d. Also check if G6 has the same phantom pattern.** Looking at the code (lines 791+), G6 does `from scripts.g6_gate import run_g6_gate` with the same ImportError catch. **If g6_gate.py also doesn't exist, remove G6 the same way.** Check: does `_staging/PKG-VOCABULARY-001/HOT/scripts/g6_gate.py` exist?

### Step 3: Edit install.sh

**File:** `_staging/install.sh`

Add `--genesis-archive` to the genesis_bootstrap.py invocation:

```bash
# Before:
python3 "$ROOT/HOT/scripts/genesis_bootstrap.py" \
    --seed "$ROOT/HOT/config/seed_registry.json" \
    --archive "$BOOTSTRAP_DIR/PKG-KERNEL-001.tar.gz"

# After:
python3 "$ROOT/HOT/scripts/genesis_bootstrap.py" \
    --seed "$ROOT/HOT/config/seed_registry.json" \
    --archive "$BOOTSTRAP_DIR/PKG-KERNEL-001.tar.gz" \
    --genesis-archive "$BOOTSTRAP_DIR/PKG-GENESIS-000.tar.gz"
```

### Step 4: Rebuild archives

1. Recompute SHA256 for modified `genesis_bootstrap.py`
2. Update `_staging/PKG-GENESIS-000/manifest.json` with new hash
3. Rebuild `_staging/PKG-GENESIS-000.tar.gz`
4. Recompute SHA256 for modified `gate_check.py`
5. Update `_staging/PKG-VOCABULARY-001/manifest.json` with new hash
6. Rebuild `_staging/PKG-VOCABULARY-001.tar.gz`
7. Update `_staging/install.sh` (no hash needed — not in a package manifest)
8. Rebuild `_staging/CP_BOOTSTRAP.tar.gz` with all updated archives + updated install.sh

### Step 5: End-to-end verification

```bash
TESTDIR=$(mktemp -d)

# Extract bootstrap
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TESTDIR"

# Run installer
chmod +x "$TESTDIR/install.sh"
"$TESTDIR/install.sh" --root "$TESTDIR/cp" --dev

# Verify G0B: 0 orphans
python3 "$TESTDIR/cp/HOT/scripts/gate_check.py" --root "$TESTDIR/cp" --gate G0B
# Expected: G0B PASS, 0 orphans

# Verify G0K is gone
python3 "$TESTDIR/cp/HOT/scripts/gate_check.py" --root "$TESTDIR/cp" --all 2>&1 | grep -i g0k
# Expected: no output (G0K not in gate list)

# Verify all gates pass
python3 "$TESTDIR/cp/HOT/scripts/gate_check.py" --root "$TESTDIR/cp" --all
# Expected: ALL gates PASS

# Verify genesis receipt exists
ls "$TESTDIR/cp/HOT/installed/PKG-GENESIS-000/"
# Expected: receipt.json

# Verify genesis files in file_ownership.csv
grep "PKG-GENESIS-000" "$TESTDIR/cp/HOT/registries/file_ownership.csv"
# Expected: 5 rows (genesis_bootstrap.py, bootstrap_sequence.json,
#           seed_registry.json, package_manifest_l0.json, test_genesis_bootstrap.py)

# Verify total file_ownership.csv row count
wc -l "$TESTDIR/cp/HOT/registries/file_ownership.csv"
# Expected: ~79 (74 kernel+package rows + 5 genesis rows + 1 header = 80)

# Full gate check
python3 "$TESTDIR/cp/HOT/scripts/gate_check.py" --root "$TESTDIR/cp" --all
# Expected: ALL PASS, no G0K, no orphans

# Run existing tests
CONTROL_PLANE_ROOT="$TESTDIR/cp" python3 -m pytest Control_Plane_v2/_staging/ -v --ignore=Control_Plane_v2/_staging/PKG-ATTENTION-001 --ignore=Control_Plane_v2/_staging/PKG-FLOW-RUNNER-001
# Expected: all pass

# Also verify Layer 3 still works on top
for pkg in PKG-PHASE2-SCHEMAS-001 PKG-TOKEN-BUDGETER-001 PKG-PROMPT-ROUTER-001 PKG-LAYOUT-002; do
    python3 "$TESTDIR/cp/HOT/scripts/package_install.py" \
        --archive "Control_Plane_v2/_staging/$pkg.tar.gz" \
        --id "$pkg" --root "$TESTDIR/cp" --dev
done

python3 "$TESTDIR/cp/HOT/scripts/gate_check.py" --root "$TESTDIR/cp" --all
# Expected: ALL PASS
```

---

## Test Plan

### Tests for genesis file registration (add to existing test_genesis_bootstrap.py or new test file)

| # | Test | Validates | Expected |
|---|------|-----------|----------|
| 1 | `test_register_genesis_files_from_archive` | `register_genesis_files()` reads manifest from tar and appends to CSV | 5 rows appended with PKG-GENESIS-000 |
| 2 | `test_register_genesis_files_missing_archive` | Handles missing archive gracefully | Returns 0, no crash |
| 3 | `test_register_genesis_files_correct_hashes` | SHA256 in CSV matches actual files on disk | All 5 hashes match |
| 4 | `test_register_genesis_files_correct_classification` | Classification from manifest is used | "genesis" for genesis files |
| 5 | `test_load_manifest_from_archive` | Extracts manifest.json from tar | Returns parsed dict |
| 6 | `test_load_manifest_from_archive_missing` | Handles archive without manifest | Returns None |
| 7 | `test_genesis_receipt_created` | After install with --genesis-archive, receipt exists | HOT/installed/PKG-GENESIS-000/receipt.json exists |
| 8 | `test_genesis_receipt_contents` | Receipt has correct fields | id, version, files, installed_at |
| 9 | `test_genesis_archive_arg_optional` | Without --genesis-archive, install still works | PKG-KERNEL-001 installs, genesis files not registered (backward compatible) |
| 10 | `test_g0b_passes_after_genesis_registration` | After full install with genesis registration, G0B finds 0 orphans | G0B PASS |

### Tests for G0K removal

| # | Test | Validates | Expected |
|---|------|-----------|----------|
| 11 | `test_g0k_not_in_gate_functions` | G0K removed from GATE_FUNCTIONS dict | "G0K" not in GATE_FUNCTIONS |
| 12 | `test_all_gates_no_g0k` | `--all` gate ordering doesn't include G0K | "G0K" not in expanded gate list |
| 13 | `test_all_gates_pass_clean_install` | After clean install, `--all` returns all PASS | all_passed == True |

**Total: 13 tests minimum**

---

## Package Plan

No NEW packages. Two existing packages are modified:

### PKG-GENESIS-000 (Layer 0)
- **Modified:** `HOT/scripts/genesis_bootstrap.py` — add `--genesis-archive`, `register_genesis_files()`, `load_manifest_from_archive()`, remove dead code
- **Hash update:** manifest.json for genesis_bootstrap.py
- **Archive rebuild:** PKG-GENESIS-000.tar.gz

### PKG-VOCABULARY-001 (Layer 1) — ships gate_check.py
- **Modified:** `HOT/scripts/gate_check.py` — remove G0K function, GATE_FUNCTIONS entry, and `"all"` ordering
- **Hash update:** manifest.json for gate_check.py
- **Archive rebuild:** PKG-VOCABULARY-001.tar.gz

### install.sh (not a package — top-level bootstrap file)
- **Modified:** Add `--genesis-archive` argument to genesis_bootstrap.py invocation

### CP_BOOTSTRAP.tar.gz
- **Rebuild** with updated PKG-GENESIS-000.tar.gz, PKG-VOCABULARY-001.tar.gz, and install.sh

---

## Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| genesis_bootstrap.py | `_staging/PKG-GENESIS-000/HOT/scripts/genesis_bootstrap.py` | THE file being modified |
| gate_check.py | `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py` | THE other file being modified |
| install.sh | `_staging/install.sh` | Add --genesis-archive argument |
| PKG-GENESIS-000 manifest | `_staging/PKG-GENESIS-000/manifest.json` | Hash update needed |
| PKG-VOCABULARY-001 manifest | `_staging/PKG-VOCABULARY-001/manifest.json` | Hash update needed |
| BUILDER_HANDOFF_STANDARD.md | `_staging/BUILDER_HANDOFF_STANDARD.md` | Results file format |

---

## Files Modified

| File | Location | Action |
|------|----------|--------|
| `genesis_bootstrap.py` | `_staging/PKG-GENESIS-000/HOT/scripts/` | EDIT: add --genesis-archive, register_genesis_files(), load_manifest_from_archive(), remove dead code |
| `manifest.json` | `_staging/PKG-GENESIS-000/` | EDIT: update SHA256 hash |
| `PKG-GENESIS-000.tar.gz` | `_staging/` | REBUILD |
| `gate_check.py` | `_staging/PKG-VOCABULARY-001/HOT/scripts/` | EDIT: remove G0K function + references |
| `manifest.json` | `_staging/PKG-VOCABULARY-001/` | EDIT: update SHA256 hash |
| `PKG-VOCABULARY-001.tar.gz` | `_staging/` | REBUILD |
| `install.sh` | `_staging/` | EDIT: add --genesis-archive argument |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD |

---

## Design Principles

1. **No orphans, no phantom gates.** Every file on disk must be registered. Every gate in the sequence must be real. Zero normalized failures.
2. **Manifest is truth.** Genesis file registration reads from the manifest inside the archive — same source of truth the rest of the system uses.
3. **Backward compatible.** `--genesis-archive` is optional. Without it, genesis_bootstrap.py works exactly as before (genesis files unregistered). With it, full registration.
4. **Introduce at time of need.** G0K gets built when multi-tier deployment exists, not before. Same principle applies to G6 if it has the same phantom pattern.
5. **Clean gate output.** After this fix, `gate_check.py --all` on a clean install should show ALL PASS. That's the baseline we build on.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: FOLLOWUP-3D** — Fix genesis file registration in file_ownership.csv + remove phantom G0K gate

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/BUILDER_FOLLOWUP_3D_genesis_g0k_fix.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: `tar czf ... -C dir $(ls dir)` — NEVER `tar czf ... -C dir .`
4. End-to-end verification: After rebuilding, G0B must show 0 orphans, G0K must not appear, all gates must PASS.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_FOLLOWUP_3D.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What are the two issues this follow-up fixes?
2. Why are genesis files currently unregistered in file_ownership.csv? (Trace the exact code path — which line, which condition fails, why)
3. What new CLI argument does genesis_bootstrap.py get, and what does it do?
4. How does `register_genesis_files()` get the list of genesis files to register? (Not hardcoded — what does it read?)
5. Why is G0K being removed? What principle does its current presence violate?
6. After removing G0K, what is the `--all` gate ordering?
7. Which files need hash updates in their manifests, and which archives need rebuilding?
8. Does install.sh change? If so, how?
9. How many tests does the test plan specify? What is the key verification test?
10. After a clean install with this fix, what should `gate_check.py --all` output? (Specifically: how many gates, how many PASS, how many FAIL)

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead. The 10-question verification is a gate, not a formality. Wait for approval.
```

### Expected Answers (for reviewer)

1. (a) G0B genesis orphans: 4-5 genesis files never registered in file_ownership.csv. (b) Phantom G0K gate: always fails because g0k_gate.py doesn't exist.
2. Lines 236-248 in `write_file_ownership()` try to read `HOT/installed/PKG-GENESIS-000/manifest.json`. This path never exists because: PKG-GENESIS-000 is tar-extracted (not installed via `install_package()`), so no receipt directory is created. Even if it were, `write_install_receipt()` writes `receipt.json`, not `manifest.json`.
3. `--genesis-archive <path>` — points to PKG-GENESIS-000.tar.gz. When provided, genesis_bootstrap.py reads the manifest from that archive and registers all genesis files in file_ownership.csv + writes a receipt.
4. It reads `manifest.json` from inside the genesis tar.gz archive using `load_manifest_from_archive()`. The manifest's `assets` array lists all genesis files.
5. G0K checks kernel parity across tiers. Multi-tier deployment doesn't exist yet. Having it unconditionally FAIL normalizes failures in gate output. Violates "introduce at time of need."
6. `["G0B", "G1", "G1-COMPLETE", "G2", "G3", "G4", "G5", "G6"]` (8 gates, G0K removed)
7. **Manifests:** PKG-GENESIS-000/manifest.json (genesis_bootstrap.py hash) and PKG-VOCABULARY-001/manifest.json (gate_check.py hash). **Archives:** PKG-GENESIS-000.tar.gz, PKG-VOCABULARY-001.tar.gz, CP_BOOTSTRAP.tar.gz.
8. Yes — add `--genesis-archive "$BOOTSTRAP_DIR/PKG-GENESIS-000.tar.gz"` to the genesis_bootstrap.py invocation.
9. 13 tests minimum. Key test: `test_g0b_passes_after_genesis_registration` — proves G0B shows 0 orphans after a full install.
10. 8 gates (G0B, G1, G1-COMPLETE, G2, G3, G4, G5, G6), ALL PASS, 0 FAIL. No G0K in output.

---

## Note on G6

Step 2d asks the agent to check if G6 has the same phantom pattern (imports `g6_gate.py` which doesn't exist). If so, remove G6 the same way. The agent should report what they find in their results file.
