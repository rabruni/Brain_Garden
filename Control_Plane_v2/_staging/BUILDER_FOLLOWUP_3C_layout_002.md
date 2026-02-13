# Builder Follow-Up #3C: PKG-LAYOUT-002 — Fix HO3, Materialize Tier Directories

## Mission

Build PKG-LAYOUT-002 to supersede PKG-LAYOUT-001. Three changes: (1) remove the HO3 ghost from layout.json (3 tiers: HOT, HO2, HO1), (2) ship a materializer script that creates the tier directory trees, (3) update tests. After install, `HO2/` and `HO1/` directory trees exist alongside `HOT/`.

**CRITICAL CONSTRAINTS — read before doing anything:**

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as `_staging/PKG-LAYOUT-002/` with manifest.json, SHA256 hashes, proper dependencies.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install Layers 0-2 (8 packages, including PKG-LAYOUT-001) → install PKG-LAYOUT-002. All gates must pass. HO2/ and HO1/ directory trees must exist.
5. **No hardcoding.** The materializer reads layout.json — it does NOT hardcode tier names or directory names.
6. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
7. **Results file.** When finished, write `_staging/RESULTS_FOLLOWUP_3C.md` following the format in `BUILDER_HANDOFF_STANDARD.md`.
8. **This package supersedes PKG-LAYOUT-001.** It ships updated versions of files owned by PKG-LAYOUT-001. The ownership transfer mechanism in package_install.py handles this — declare PKG-LAYOUT-001 as a dependency.

---

## Context

### The HO3 Problem

A prior agent created an incorrect 4-tier model: HOT, HO3, HO2, HO1. HO3 does not exist. The correct model is 3 tiers:

| Tier | Role | Memory | Agent Scope |
|------|------|--------|-------------|
| **HOT** | Executive / kernel | Meta / abstract | Infrastructure, governance |
| **HO2** | Session / admin | Episodic / session | Work order duration, sequences HO1 agents |
| **HO1** | Stateless / fast | Working / none | One agent, one contract, one shot |

PKG-LAYOUT-001 shipped `layout.json` with HO3 in the tiers map, and `test_layout.py` with HO3 assertions. Both must be fixed.

### The Materializer Problem

`layout.json` describes the directory structure each tier should have (via `tier_dirs`), but nothing actually creates those directories. The bootstrap only materializes `HOT/`. After install, `HO2/` and `HO1/` do not exist. Admin-level agents need `HO2/` to operate.

### Ownership Transfer

PKG-LAYOUT-001 (Layer 2) owns two files:
- `HOT/config/layout.json`
- `HOT/tests/test_layout.py`

PKG-LAYOUT-002 (Layer 3) ships updated versions of both files. Because PKG-LAYOUT-002 declares PKG-LAYOUT-001 as a dependency, the ownership validator in package_install.py detects this as a legitimate transfer (not a conflict). It updates file_ownership.csv with the supersession.

### Data Stays Centralized

Per architectural decision: registries and ledger stay centralized in `HOT/`. `HO2/` and `HO1/` get their directory scaffolding but NO registries, NO ledger, NO file_ownership.csv. Those subdirectories are created empty — ready for future use when the first HO2 package is built. The `tier_dirs` config defines what subdirectories each tier gets, but the materializer only creates the directories — it does not populate them with data files.

---

## What to Build

### File 1: Updated `layout.json`

**Path:** `PKG-LAYOUT-002/HOT/config/layout.json`

Changes from the PKG-LAYOUT-001 version:
1. Remove `"HO3": "HO3"` from the `tiers` map
2. Bump `schema_version` to `"1.1"`

Result:
```json
{
  "schema_version": "1.1",
  "tiers": {
    "HOT": "HOT",
    "HO2": "HO2",
    "HO1": "HO1"
  },
  "hot_dirs": { ... unchanged ... },
  "tier_dirs": { ... unchanged ... },
  "registry_files": { ... unchanged ... },
  "ledger_files": { ... unchanged ... }
}
```

All other sections (`hot_dirs`, `tier_dirs`, `registry_files`, `ledger_files`) stay exactly as they are in PKG-LAYOUT-001.

### File 2: `materialize_layout.py`

**Path:** `PKG-LAYOUT-002/HOT/scripts/materialize_layout.py`

A script that reads layout.json and creates the tier directory trees.

**Behavior:**
1. Load layout.json from `HOT/config/layout.json` (resolved via `CONTROL_PLANE_ROOT` or `paths.py`)
2. For each tier in `tiers` (HOT, HO2, HO1):
   a. Create the tier root directory (e.g., `$ROOT/HO2/`)
   b. For each entry in `tier_dirs`, create the subdirectory (e.g., `$ROOT/HO2/registries/`, `$ROOT/HO2/installed/`, etc.)
3. For HOT specifically: also create the `hot_dirs` directories (kernel, config, registries, schemas, scripts, installed, ledger). These should already exist after bootstrap — skip if they exist.
4. Log what was created vs. what already existed
5. Idempotent: running twice is safe (mkdir -p equivalent)

**NOT done by the materializer:**
- Does NOT create file_ownership.csv in tier registries
- Does NOT create ledger .jsonl files in tier ledgers
- Does NOT copy files between tiers
- Does NOT modify any existing files

**CLI interface:**
```
python3 materialize_layout.py --root <plane_root>
```

If `--root` is omitted, use `CONTROL_PLANE_ROOT` env var (via `paths.py`).

**Output (stdout):**
```
[materialize] Reading layout from HOT/config/layout.json
[materialize] Tier HOT: 7 dirs (7 exist, 0 created)
[materialize] Tier HO2: 7 dirs (0 exist, 7 created)
[materialize] Tier HO1: 7 dirs (0 exist, 7 created)
[materialize] Done: 14 directories created, 7 already existed
```

**Exit codes:**
- 0: success (including "nothing to do")
- 1: layout.json not found or invalid
- 2: permission error creating directories

### File 3: Updated `test_layout.py`

**Path:** `PKG-LAYOUT-002/HOT/tests/test_layout.py`

Changes from the PKG-LAYOUT-001 version:

1. **`test_has_tiers`**: Change from `["HOT", "HO3", "HO2", "HO1"]` to `["HOT", "HO2", "HO1"]`
2. **`TestTierLayout`**: Change all `HO3` references to `HO2`:
   - `test_tier_ho3_returns_tier_layout` → `test_tier_ho2_returns_tier_layout` (use `"HO2"`)
   - `test_tier_ho3_installed_is_path` → `test_tier_ho2_installed_is_path` (assert ends with `"HO2/installed"`)
   - `test_tier_ho3_ledger_is_path` → `test_tier_ho2_ledger_is_path` (assert ends with `"HO2/ledger"`)
   - `test_tier_ho3_tests_is_path` → `test_tier_ho2_tests_is_path`
3. **`test_tier_invalid_raises`**: Keep as-is (tests "INVALID" tier — still valid)
4. **`TestLayoutConvenience`**:
   - `test_ledger_file_resolves`: Change `"HO3"` to `"HO2"`
   - `test_ledger_file_invalid_key_raises`: Change `"HO3"` to `"HO2"`
5. **Add `test_ho3_is_invalid_tier`**: Explicitly test that `LAYOUT.tier("HO3")` raises an error. This is a regression guard — if HO3 ever creeps back, this catches it.
6. **Add `TestMaterializeLayout`**: New test class for the materializer (see Test Plan below)

### File 4: `test_materialize_layout.py`

**Path:** `PKG-LAYOUT-002/HOT/tests/test_materialize_layout.py`

Dedicated test file for the materializer. Separate from test_layout.py to keep concerns clean.

---

## Package Plan

### PKG-LAYOUT-002 (Layer 3)

```json
{
  "package_id": "PKG-LAYOUT-002",
  "version": "1.1.0",
  "schema_version": "1.2",
  "title": "Tier Layout Materializer",
  "description": "Fix HO3 ghost, materialize HO2/HO1 directory trees from layout.json",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot",
  "layer": 3,
  "dependencies": [
    "PKG-KERNEL-001",
    "PKG-LAYOUT-001"
  ],
  "assets": [
    {
      "path": "HOT/config/layout.json",
      "sha256": "<computed>",
      "classification": "config"
    },
    {
      "path": "HOT/scripts/materialize_layout.py",
      "sha256": "<computed>",
      "classification": "script"
    },
    {
      "path": "HOT/tests/test_layout.py",
      "sha256": "<computed>",
      "classification": "test"
    },
    {
      "path": "HOT/tests/test_materialize_layout.py",
      "sha256": "<computed>",
      "classification": "test"
    }
  ]
}
```

**Key points:**
- Depends on `PKG-LAYOUT-001` — enables ownership transfer for `layout.json` and `test_layout.py`
- Depends on `PKG-KERNEL-001` — for paths.py, layout.py
- Ships 2 updated files (transfer) + 2 new files
- Layer 3 — installs after the full bootstrap

---

## Test Plan

### test_layout.py updates (existing tests, fixed)

All existing tests from PKG-LAYOUT-001 remain, with HO3 → HO2 substitution:

1. `test_layout_json_exists` — layout.json in HOT/config/ (unchanged)
2. `test_layout_json_is_valid_json` — parseable JSON (unchanged)
3. `test_has_schema_version` — update to check for "1.1"
4. `test_has_tiers` — **FIX**: assert HOT, HO2, HO1 (3 tiers, not 4)
5. `test_has_hot_dirs` — unchanged
6. `test_has_tier_dirs` — unchanged
7. `test_has_registry_files` — unchanged
8. `test_has_ledger_files` — unchanged
9. `test_layout_module_importable` — unchanged
10. `test_load_layout_returns_layout` — unchanged
11. `test_layout_singleton_exists` — unchanged
12. `test_hot_registries_is_path` — unchanged
13. `test_hot_registries_points_to_hot_registries` — unchanged
14. `test_hot_kernel_is_path` — unchanged
15. `test_hot_config_is_path` — unchanged
16. `test_hot_schemas_is_path` — unchanged
17. `test_hot_installed_is_path` — unchanged
18. `test_hot_ledger_is_path` — unchanged
19. `test_tier_ho2_returns_tier_layout` — **FIX**: was HO3
20. `test_tier_ho2_installed_is_path` — **FIX**: was HO3, assert "HO2/installed"
21. `test_tier_ho2_ledger_is_path` — **FIX**: was HO3, assert "HO2/ledger"
22. `test_tier_ho2_tests_is_path` — **FIX**: was HO3
23. `test_tier_invalid_raises` — unchanged (tests "INVALID")
24. `test_ho3_is_invalid_tier` — **NEW**: assert LAYOUT.tier("HO3") raises
25. `test_registry_file_resolves` — unchanged
26. `test_registry_file_in_hot_registries` — unchanged
27. `test_ledger_file_resolves` — **FIX**: was HO3, use HO2
28. `test_ledger_file_invalid_key_raises` — **FIX**: was HO3, use HO2
29. `test_load_layout_with_missing_file` — unchanged
30. `test_registries_dir_matches_layout` — unchanged

### test_materialize_layout.py (new tests)

1. `test_materialize_creates_ho2_root` — HO2/ directory created
2. `test_materialize_creates_ho1_root` — HO1/ directory created
3. `test_materialize_creates_ho2_subdirs` — HO2/registries/, HO2/installed/, HO2/ledger/, HO2/packages_store/, HO2/scripts/, HO2/tests/, HO2/spec_packs/ all created
4. `test_materialize_creates_ho1_subdirs` — same 7 subdirs under HO1/
5. `test_materialize_hot_already_exists` — HOT/ dirs already present, materializer reports "already existed" and does not error
6. `test_materialize_idempotent` — run twice, no errors, same result
7. `test_materialize_reads_layout_json` — materializer uses tier names from layout.json (not hardcoded). Verify by providing a custom layout.json with only 2 tiers.
8. `test_materialize_no_data_files_created` — after materialize, HO2/registries/ is empty (no CSV files), HO2/ledger/ is empty (no JSONL files)
9. `test_materialize_missing_layout_json` — exit code 1 with clear error
10. `test_materialize_exit_code_zero` — successful run returns 0
11. `test_materialize_output_reports_counts` — stdout contains created/existed counts
12. `test_materialize_respects_control_plane_root` — uses --root arg or CONTROL_PLANE_ROOT env var

---

## Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Current layout.json | `_staging/PKG-LAYOUT-001/HOT/config/layout.json` | Base to modify (remove HO3) |
| Current test_layout.py | `_staging/PKG-LAYOUT-001/HOT/tests/test_layout.py` | Base to modify (HO3→HO2) |
| layout.py (Layout class) | `_staging/PKG-KERNEL-001/HOT/kernel/layout.py` | Understand how Layout reads layout.json |
| paths.py | `_staging/PKG-KERNEL-001/HOT/kernel/paths.py` | get_control_plane_root() for --root fallback |
| package_install.py | `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py` | Ownership transfer mechanism |
| Package manifest pattern | `_staging/PKG-PHASE2-SCHEMAS-001/manifest.json` | Layer 3 manifest example |

---

## End-to-End Verification

```bash
TMPDIR=$(mktemp -d)
STAGING="Control_Plane_v2/_staging"
export CONTROL_PLANE_ROOT="$TMPDIR"

# 1. Extract and install bootstrap (Layers 0-2, including PKG-LAYOUT-001)
tar xzf "$STAGING/CP_BOOTSTRAP.tar.gz" -C "$TMPDIR"

# Layer 0
tar xzf "$TMPDIR/PKG-GENESIS-000.tar.gz" -C "$TMPDIR"
python3 "$TMPDIR/HOT/scripts/genesis_bootstrap.py" \
    --seed "$TMPDIR/HOT/config/seed_registry.json" \
    --archive "$TMPDIR/PKG-KERNEL-001.tar.gz"

# Layer 1
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-VOCABULARY-001.tar.gz" \
    --id PKG-VOCABULARY-001 --root "$TMPDIR" --dev
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$TMPDIR/PKG-REG-001.tar.gz" \
    --id PKG-REG-001 --root "$TMPDIR" --dev

# Layer 2
for pkg in PKG-GOVERNANCE-UPGRADE-001 PKG-FRAMEWORK-WIRING-001 \
           PKG-SPEC-CONFORMANCE-001 PKG-LAYOUT-001; do
    python3 "$TMPDIR/HOT/scripts/package_install.py" \
        --archive "$TMPDIR/$pkg.tar.gz" \
        --id "$pkg" --root "$TMPDIR" --dev
done

# 2. Verify PKG-LAYOUT-001 installed (HO3 still in layout.json)
python3 -c "import json; d=json.load(open('$TMPDIR/HOT/config/layout.json')); assert 'HO3' in d['tiers']"
echo "PKG-LAYOUT-001 installed with HO3 (expected)"

# 3. Install PKG-LAYOUT-002 (Layer 3, supersedes LAYOUT-001)
python3 "$TMPDIR/HOT/scripts/package_install.py" \
    --archive "$STAGING/PKG-LAYOUT-002.tar.gz" \
    --id PKG-LAYOUT-002 --root "$TMPDIR" --dev

# 4. Verify HO3 removed from layout.json
python3 -c "import json; d=json.load(open('$TMPDIR/HOT/config/layout.json')); assert 'HO3' not in d['tiers']; assert set(d['tiers']) == {'HOT', 'HO2', 'HO1'}"
echo "HO3 removed, 3 tiers correct"

# 5. Run materializer
python3 "$TMPDIR/HOT/scripts/materialize_layout.py" --root "$TMPDIR"

# 6. Verify tier directories exist
for tier in HO2 HO1; do
    for subdir in registries installed ledger packages_store scripts tests spec_packs; do
        test -d "$TMPDIR/$tier/$subdir" || echo "MISSING: $tier/$subdir"
    done
done
echo "Tier directories verified"

# 7. Verify tier directories are EMPTY (no data files)
test -z "$(ls -A "$TMPDIR/HO2/registries/")" && echo "HO2/registries/ empty (correct)"
test -z "$(ls -A "$TMPDIR/HO1/ledger/")" && echo "HO1/ledger/ empty (correct)"

# 8. Verify ownership transfer in file_ownership.csv
grep "layout.json" "$TMPDIR/HOT/registries/file_ownership.csv"
# Should show: PKG-LAYOUT-001 with replaced_date set, PKG-LAYOUT-002 as current owner

# 9. Run gate checks
python3 "$TMPDIR/HOT/scripts/gate_check.py" --root "$TMPDIR" --all

# 10. Run tests
CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest \
    "$STAGING/PKG-LAYOUT-002/HOT/tests/" -v
```

**Expected results:**
- 9 packages installed (8 bootstrap + PKG-LAYOUT-002)
- Ownership transfer: layout.json and test_layout.py transferred from PKG-LAYOUT-001 to PKG-LAYOUT-002
- HO2/ and HO1/ each have 7 subdirectories, all empty
- No HO3 references anywhere
- All gates pass
- All tests pass

---

## Files Summary

| File | Location | Action |
|------|----------|--------|
| `layout.json` | `_staging/PKG-LAYOUT-002/HOT/config/` | CREATE (updated, removes HO3) |
| `materialize_layout.py` | `_staging/PKG-LAYOUT-002/HOT/scripts/` | CREATE (new) |
| `test_layout.py` | `_staging/PKG-LAYOUT-002/HOT/tests/` | CREATE (updated, HO3→HO2 + new HO3-invalid test) |
| `test_materialize_layout.py` | `_staging/PKG-LAYOUT-002/HOT/tests/` | CREATE (new) |
| `manifest.json` | `_staging/PKG-LAYOUT-002/` | CREATE |
| `PKG-LAYOUT-002.tar.gz` | `_staging/` | CREATE |
| `RESULTS_FOLLOWUP_3C.md` | `_staging/` | CREATE (results file) |

**Not modified:** PKG-LAYOUT-001 (stays in CP_BOOTSTRAP as-is), CP_BOOTSTRAP.tar.gz, any other package.

---

## Design Principles

1. **Config-driven, not hardcoded.** The materializer reads tier names and subdirectory names from layout.json. If layout.json adds a new tier tomorrow, the materializer handles it without code changes.
2. **Directories are scaffolding, not data.** The materializer creates empty directories. No CSV files, no JSONL files, no data. Data stays centralized in HOT/ until the first HO2 package is built.
3. **Idempotent.** Run the materializer 10 times — same result. No errors, no duplicates.
4. **Ownership transfer, not file replacement.** PKG-LAYOUT-002 takes legitimate ownership of layout.json and test_layout.py from PKG-LAYOUT-001 via the dependency-based transfer mechanism. file_ownership.csv records the supersession.
5. **HO3 is dead, permanently.** The test `test_ho3_is_invalid_tier` is a regression guard. If HO3 ever appears again, it fails.

---

## Cross-Cutting Concerns (Tracked, Not Implemented)

These concerns are noted here for future reference. They are NOT part of this handoff.

| Concern | Decision | When to Revisit |
|---------|----------|-----------------|
| Cross-tier reads (HOT reading HO2 data) | Data stays centralized in HOT/. `scope.tier` in ledger_entry_metadata.schema.json enables filtered queries. No physical split. | When ledger_query_service (handoff #6) needs cross-tier aggregation. Currently a filtered query on one ledger — no special handling needed. |
| Tier privilege model (who writes where) | Conceptual only. Not enforced in code. | When first HO2 agent is built. Enforcement goes in authz.py at the API boundary, not filesystem permissions. |
| Per-tier registries/ledger | Deferred. All data in HOT/registries/ and HOT/ledger/. | When first package targets `plane_id: "ho2"`. Will require package_install.py upgrade. |
| Dynamic tier provisioning | Not built. Only base 3 tiers (HOT, HO2, HO1) are materialized. | When a framework requests a non-base tier. Flow runner would handle creation. |
| Cross-tier agent class | Not a new role type. KERNEL agents already have full read access. Cross-tier queries are a privilege of the KERNEL.semantic class, not a separate role. | When learning loops (handoff #8) need to read HO2 operational data from HOT governance scope. |
