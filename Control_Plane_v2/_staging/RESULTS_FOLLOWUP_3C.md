# Results: Follow-Up #3C — PKG-LAYOUT-002: Fix HO3, Materialize Tier Directories

## Status: PASS

## Files Created
- `_staging/PKG-LAYOUT-002/manifest.json` (SHA256: c18601cbfbbfc969e8b90800570bb06def9d6bd6474cdecb1f8d561cd31669b5)
- `_staging/PKG-LAYOUT-002/HOT/config/layout.json` (SHA256: 81241eee5713936c6636d93f6dd3a099b7c270a5a03679be8d92f37f00e7fe04)
- `_staging/PKG-LAYOUT-002/HOT/scripts/materialize_layout.py` (SHA256: 4b69e5fd5f506b1e483765aa7b96d7e4411f0609bc25f58b5eef4accde952f7e)
- `_staging/PKG-LAYOUT-002/HOT/tests/test_layout.py` (SHA256: 7a9aedf2b14a379d784c1192cf74736c3fac705f9d751e0e1fb3d2639c726e47)
- `_staging/PKG-LAYOUT-002/HOT/tests/test_materialize_layout.py` (SHA256: da3f01b201483d7dacddd5d410d57b2c1cc29de5e7bfdb3f44efd811e90211c3)

## Files Modified
- None. PKG-LAYOUT-001 and CP_BOOTSTRAP.tar.gz are untouched.

## Archives Built
- `_staging/PKG-LAYOUT-002.tar.gz` (SHA256: 88bd7247c275c830ca05ff8d13341917ea63d8f6a5d684cc8b1b576b791afdd3)

## Test Results
- Total: 43 tests
- Passed: 43
- Failed: 0
- Skipped: 0
- Command: `CONTROL_PLANE_ROOT="$TMPDIR" python3 -m pytest Control_Plane_v2/_staging/PKG-LAYOUT-002/HOT/tests/ -v`

### Test Breakdown
- `test_layout.py`: 31 tests (8 JSON structure + 3 Layout class + 7 HotLayout + 7 TierLayout + 4 convenience + 1 bootstrap fallback + 1 paths bridge)
- `test_materialize_layout.py`: 12 tests (2 root creation + 2 subdir creation + 2 idempotent + 1 config-driven + 1 no data files + 1 error handling + 3 output/exit/env)

Note: The spec says 30 tests in test_layout.py. I have 31 because `test_tier_method_exists` was in the original PKG-LAYOUT-001 tests and the spec's numbered list missed it in the renumbering. Kept it — "all existing tests remain."

## Gate Check Results (Install Pipeline)
- G0B: PASS (pre-install integrity, during package_install.py)
- G0A: PASS (package declaration)
- G1: PASS (chain — 7 chains validated)
- G1-COMPLETE: PASS (framework completeness — 7 frameworks)
- G5: PASS (signature waived in dev mode)

### Post-Install Gate Check (gate_check.py --all)
- G0K: FAIL (pre-existing — g0k_gate.py module not built yet)
- G0B: FAIL (pre-existing — 4 genesis orphan files not registered in file_ownership.csv: genesis_bootstrap.py, bootstrap_sequence.json, seed_registry.json, package_manifest_l0.json)
- G1: PASS (7 chains, 0 warnings)
- G1-COMPLETE: PASS (7 frameworks)
- G2-G6: PASS
- Overall: 7/9 gates pass. Both failures are pre-existing and documented in MEMORY.md.

## Clean-Room Verification
- Packages installed: 9 (8 bootstrap + PKG-LAYOUT-002)
- Install order: PKG-GENESIS-000 → PKG-KERNEL-001 → PKG-VOCABULARY-001 → PKG-REG-001 → PKG-GOVERNANCE-UPGRADE-001 → PKG-FRAMEWORK-WIRING-001 → PKG-SPEC-CONFORMANCE-001 → PKG-LAYOUT-001 → PKG-LAYOUT-002
- All install-time gates pass after each install: YES
- HO3 in layout.json before LAYOUT-002: YES (4 tiers)
- HO3 in layout.json after LAYOUT-002: NO (3 tiers: HOT, HO2, HO1)
- schema_version after LAYOUT-002: "1.1"
- Materializer output: 16 directories created, 13 already existed
- HO2/ subdirectories: 7/7 present, all empty
- HO1/ subdirectories: 7/7 present, all empty

### Ownership Transfer Verified
`file_ownership.csv` shows correct 3-row pattern for each transferred file:
1. Original ownership row (PKG-LAYOUT-001, with hash, no replaced_date)
2. Supersession row (PKG-LAYOUT-001, blank hash, replaced_date set, superseded_by=PKG-LAYOUT-002)
3. New ownership row (PKG-LAYOUT-002, with new hash, no replaced_date)

Files transferred:
- `HOT/config/layout.json`: PKG-LAYOUT-001 → PKG-LAYOUT-002
- `HOT/tests/test_layout.py`: PKG-LAYOUT-001 → PKG-LAYOUT-002

## Issues Encountered
1. **test_layout.py `ModuleNotFoundError`**: When running tests from the staging directory, `sys.path` included `_staging/PKG-LAYOUT-002/HOT/` which has no `kernel/` package. Fixed by adding `CONTROL_PLANE_ROOT`-aware path resolution: when the env var is set, the installed environment's `HOT/` is added to `sys.path` for kernel imports. This is a legitimate fix — the test needs to find kernel modules from the installed environment when run from staging.

2. **HOT tier_dirs + hot_dirs double-counting**: The materializer reports "Tier HOT: 15 dirs (13 exist, 2 created)" because it iterates both `tier_dirs` (7) and `hot_dirs` (8) for the HOT tier. Two HOT-specific `hot_dirs` entries (kernel and frameworks) didn't previously exist as standalone directories. This is correct behavior — the spec says "For HOT specifically: also create the `hot_dirs` directories."

## Notes for Reviewer
1. **Test count is 43, not 42**: The handoff spec numbered 30 tests for test_layout.py but the original PKG-LAYOUT-001 test file had `test_tier_method_exists` which the spec's renumbering missed. I preserved all original tests as instructed ("All existing tests from PKG-LAYOUT-001 remain"). 31 + 12 = 43.

2. **No changes to CP_BOOTSTRAP.tar.gz**: PKG-LAYOUT-001 remains in the bootstrap as-is. PKG-LAYOUT-002 is a standalone Layer 3 archive that supersedes it via ownership transfer.

3. **Materializer is fully config-driven**: Verified via `test_materialize_reads_layout_json` which provides a custom 2-tier layout (HOT + CUSTOM) and confirms the materializer creates CUSTOM/ but NOT HO2/ or HO1/ — proving no hardcoding.

4. **Archive format verified**: `tar tzf` shows `manifest.json` at top level (no `./` prefix), no `__pycache__` directories.
