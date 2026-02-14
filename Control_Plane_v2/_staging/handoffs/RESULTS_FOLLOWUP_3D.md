# Results: Follow-Up #3D — Fix Genesis File Registration + Remove Phantom G0K Gate

## Status: PASS

## Files Modified
- `_staging/PKG-GENESIS-000/HOT/scripts/genesis_bootstrap.py` (SHA256: 2215c7edc75794f670575edf840afbd6389b83bbf86869d0a62c564eeee7777a)
- `_staging/PKG-GENESIS-000/HOT/config/seed_registry.json` (SHA256: df4cd82fca6e30a8e821a89e01f9352fb866290dbe9bfbe07aaea46abc90951b)
- `_staging/PKG-GENESIS-000/manifest.json` (SHA256: 3864f8f9d3f452a53c3fcac5aa5ef6e4e48a139946def0779c3245501a18a337)
- `_staging/PKG-VOCABULARY-001/HOT/scripts/gate_check.py` (SHA256: 1fbbc10991fc3b44666593da32150bb74cb6331758d813df893b432b93f4b9b5)
- `_staging/PKG-VOCABULARY-001/manifest.json` (SHA256: 4cd4e7fb2ffb50d1c6dd62753cec2728fe8b979a064ca18f63fec39f12cb733c)
- `_staging/install.sh` (SHA256: c621aeb8fc2b1d906e0efaeaf479eac0668da0b0d3e777752b8e6e94e684735b)

## Files Created
- `_staging/test_followup_3d.py` (SHA256: 4fefb64d396c6a61078574548f9f4ca630d748b6e61f08644e656919ad895656)

## Archives Rebuilt
- `_staging/PKG-GENESIS-000.tar.gz` (SHA256: 87f1c95bc02f4189c486b7860d3b77cf3234c45ac7214ca92a9ac534a64ee71f)
- `_staging/PKG-VOCABULARY-001.tar.gz` (SHA256: fbd5c3bc7d33a9c9eed4ece616bc5ea71c5df6ff54032097672056aadc3f671a)
- `_staging/CP_BOOTSTRAP.tar.gz` (SHA256: 2626216a1dcfcd0d7d62ee62c529992e4126a355e7acde41b743a3113e6d51ba)

## Test Results
- Total: 13 tests (FOLLOWUP-3D specific)
- Passed: 13
- Failed: 0
- Skipped: 0
- Command: `python3 -m pytest Control_Plane_v2/_staging/test_followup_3d.py -v`

### Test Breakdown
- `TestRegisterGenesisFiles`: 4 tests (from_archive, missing_archive, correct_hashes, correct_classification)
- `TestLoadManifestFromArchive`: 2 tests (success, missing manifest)
- `TestGenesisReceipt`: 3 tests (created, contents, backward_compat)
- `TestG0BPrecondition`: 1 test (all genesis files owned)
- `TestG0KRemoval`: 3 tests (not_in_gate_functions, not_in_all_ordering, gate_list_correct)

### Existing Tests
- 27 existing PKG-GENESIS-000 tests: all pass
- 167 other staging tests: all pass (17 pre-existing failures from doubled `_staging/_staging/` path in test_bootstrap_sequence.py and test_spec_conformance.py — not regressions)

## Gate Check Results (Clean-Room Install)

### After Layer 0-2 Bootstrap (8 packages)
- G0B: PASS (64 files owned, 0 orphans)
- G1: PASS (6 chains validated)
- G1-COMPLETE: PASS (6 frameworks checked)
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS (fallback — 2 ledger files, 13 entries)
- **Overall: 8/8 gates PASS**

### After Layer 3 (4 additional packages)
- G0B: PASS (76 files owned, 0 orphans)
- G1: PASS (10 chains validated)
- G1-COMPLETE: PASS (10 frameworks checked)
- G2-G6: PASS
- **Overall: 8/8 gates PASS**

## Clean-Room Verification
- Packages installed: 8 bootstrap + 4 Layer 3 = 12 total
- Install order: PKG-GENESIS-000 (tar extract) → PKG-KERNEL-001 (genesis bootstrap) → PKG-VOCABULARY-001 → PKG-REG-001 → PKG-GOVERNANCE-UPGRADE-001 → PKG-FRAMEWORK-WIRING-001 → PKG-SPEC-CONFORMANCE-001 → PKG-LAYOUT-001 → PKG-PHASE2-SCHEMAS-001 → PKG-TOKEN-BUDGETER-001 → PKG-PROMPT-ROUTER-001 → PKG-LAYOUT-002
- Genesis files registered: 5 (genesis_bootstrap.py, bootstrap_sequence.json, seed_registry.json, package_manifest_l0.json, test_genesis_bootstrap.py)
- Genesis receipt exists: YES (`HOT/installed/PKG-GENESIS-000/receipt.json`)
- G0K in gate output: NO
- file_ownership.csv rows: 75 (after Layer 0-2)
- All install-time gates pass after each install: YES

## Changes Made

### 1. genesis_bootstrap.py
- **Added `--genesis-archive` CLI argument**: Optional path to PKG-GENESIS-000.tar.gz
- **Added `load_manifest_from_archive()`**: Reads manifest.json from inside a tar.gz archive. Extracted from duplicate inline code at old lines 437-448.
- **Added `register_genesis_files()`**: Reads genesis manifest from archive, appends 5 ownership rows to file_ownership.csv with correct hashes and classifications.
- **Updated `install_package()` signature**: New optional `genesis_archive` parameter. When provided, registers genesis files and writes genesis receipt after kernel file ownership.
- **Removed dead code** (old lines 236-248): The genesis registration code in `write_file_ownership()` that read from `HOT/installed/PKG-GENESIS-000/manifest.json` — a path that never existed without the install.sh hack.
- **Replaced inline manifest reading** (old lines 435-448): Now calls `load_manifest_from_archive(archive)`.

### 2. gate_check.py
- **Removed `check_g0k_kernel_parity()` function** (old lines 742-788)
- **Removed `"G0K"` from `GATE_FUNCTIONS` dict** (old line 907)
- **Removed `"G0K"` from `--all` gate ordering** (old line 946)
- **New `--all` ordering**: `["G0B", "G1", "G1-COMPLETE", "G2", "G3", "G4", "G5", "G6"]` (8 gates)

### 3. install.sh
- **Removed manifest copy hack** (old lines 143-150): No longer copies manifest.json to `HOT/installed/PKG-GENESIS-000/`. Replaced with `rm -f "$ROOT/manifest.json"` to clean up the extracted manifest.
- **Added `--genesis-archive`**: Genesis bootstrap invocation now includes `--genesis-archive "$BOOTSTRAP_DIR/PKG-GENESIS-000.tar.gz"`
- **Removed G0K workaround** (old lines 264-274): No longer filters out "known G0K failures". Any gate failure is now a real failure (`exit 3`).

### 4. seed_registry.json
- **Updated PKG-KERNEL-001 digest**: Fixed stale hash from `c39baed6c...` to `21d482d5b...` to match the actual PKG-KERNEL-001.tar.gz archive.

## G6 Investigation (Step 2d)
`g6_gate.py` does NOT exist (confirmed). However, `check_g6_ledger()` in gate_check.py has a graceful fallback (lines 821-836): it catches ImportError, counts ledger files, and returns PASS. This is fundamentally different from G0K which returned FAIL on ImportError. **Recommendation: keep G6 in the gate list** — it degrades gracefully and will activate when g6_gate.py ships.

## Notes for Reviewer
1. **Seed registry hash fix**: The seed_registry.json had a stale digest for PKG-KERNEL-001.tar.gz. This was a pre-existing issue — PKG-KERNEL-001.tar.gz was rebuilt in earlier sessions (package_install.py bug fixes) but the seed_registry wasn't updated. Fixed as part of this follow-up.
2. **Layer 3 macOS path quirk**: Layer 3 installs in tmpdir require `CONTROL_PLANE_ROOT` with resolved `/private/var/...` path on macOS. The `/var` → `/private/var` symlink causes path comparison failures in package_install.py's write-outside-CONTROL_PLANE check. Not a regression — pre-existing macOS behavior.
3. **Backward compatibility**: `--genesis-archive` is optional. Without it, genesis_bootstrap.py works exactly as before (genesis files unregistered, no genesis receipt). This preserves backward compatibility for any existing callers.
4. **Gate count**: install.sh summary reports "7 passed" (counts only `G??:` pattern lines in gate output), while gate_check.py reports "8/8 gates passed" (includes G1-COMPLETE which has a hyphen). This display discrepancy is cosmetic and pre-existing.
