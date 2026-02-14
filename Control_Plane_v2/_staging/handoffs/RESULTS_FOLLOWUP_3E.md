# RESULTS: FOLLOWUP-3E — Path Authority Consolidation

**Status**: PASS 12/12
**Date**: 2026-02-11
**Platform**: Claude (Opus 4.6)

## Summary

Consolidated 4 competing path sources into a single authority (layout.json). Fixed all hardcoded dual-path fallbacks. Removed HO3 ghost tier from layout.json. All ledger writes now go to `HOT/ledger/`, not `root/ledger/`.

## Files Modified

| File | Package | Changes |
|------|---------|---------|
| `HOT/kernel/paths.py` | PKG-KERNEL-001 | Simplified REGISTRIES_DIR/LEDGER_DIR to use CONTROL_PLANE directly (removed fragile LAYOUT dependency for deprecated singletons) |
| `HOT/kernel/layout.py` | PKG-KERNEL-001 | Fixed `_find_cp_root()` to check CONTROL_PLANE_ROOT env var + structural markers (was hardcoding "Control_Plane_v2" directory name) |
| `HOT/kernel/ledger_client.py` | PKG-KERNEL-001 | DEFAULT_LEDGER_PATH now imports LEDGER_DIR from paths.py (was hardcoded relative path) |
| `HOT/kernel/pristine.py` | PKG-KERNEL-001 | Added HOT-prefixed paths to PRISTINE_PATHS, APPEND_ONLY_PATHS, DERIVED_PATHS; fixed audit ledger path (`plane / "HOT" / "ledger"` instead of `plane / "ledger"`) |
| `HOT/scripts/package_install.py` | PKG-KERNEL-001 | Already fixed (LEDGER_DIR import, prior session) |
| `HOT/scripts/gate_check.py` | PKG-VOCABULARY-001 | Removed 5 dual-path fallbacks: load_control_plane_registry, load_file_ownership_registry, check_g1_chain, check_g2_work_order, check_g6_ledger |
| `HOT/config/layout.json` | PKG-LAYOUT-001 | Removed HO3 from tiers (now HOT, HO2, HO1 only) |

## Additional Fixes (discovered during clean-room)

1. **layout.py `_find_cp_root()` broken in clean installs**: Hardcoded "Control_Plane_v2" as directory name. Falls back to `cwd()` when installed elsewhere, corrupting all LAYOUT paths. Fixed with env var check + structural marker detection.

2. **pristine.py path classifications flat-layout only**: `APPEND_ONLY_PATHS = {"ledger"}` didn't match `HOT/ledger/...`. Added HOT-prefixed paths for all three classification sets.

3. **pristine.py audit ledger path**: `_log_event()` wrote audit entries to `plane / "ledger"` (root) instead of `plane / "HOT" / "ledger"`. This created a spurious `root/ledger/` directory during installs.

## Test Results

### test_followup_3e.py — 12/12 PASS

| # | Test | Result |
|---|------|--------|
| 1 | `test_01_paths_ledger_dir_exists` | PASS |
| 2 | `test_02_paths_ledger_dir_in_hot` | PASS |
| 3 | `test_03_paths_registries_dir_in_hot` | PASS |
| 4 | `test_04_package_install_pkg_reg_in_hot` | PASS |
| 5 | `test_05_package_install_ledger_in_hot` | PASS |
| 6 | `test_06_ledger_client_default_path_in_hot` | PASS |
| 7 | `test_07_gate_check_no_root_registries_fallback` | PASS |
| 8 | `test_08_gate_check_no_root_ledger_fallback` | PASS |
| 9 | `test_09_layout_json_no_ho3` | PASS |
| 10 | `test_10_layout_json_tiers_correct` | PASS |
| 11 | `test_11_clean_install_ledger_in_hot` | PASS (runtime: 3 ledger files) |
| 12 | `test_12_clean_install_no_root_ledger` | PASS (runtime: root/ledger/ absent) |

### test_followup_3d.py (regression) — 13/13 PASS

### Clean-Room Verification

- **12 packages installed** across 4 layers (0-3)
- **8/8 gates PASS** (G0B, G1, G1-COMPLETE, G2, G3, G4, G5, G6)
- **HOT/ledger/**: 3 files (governance.jsonl, packages.jsonl, index.jsonl)
- **root/ledger/**: does NOT exist
- **91 ownership rows** in file_ownership.csv
- **12 receipts** in HOT/installed/
- **G0B**: 76 files owned, 0 orphans
- **G1**: 10 chains validated
- **G6**: 3 ledger files, 59 entries

## CP_BOOTSTRAP.tar.gz

- **Size**: 153 KB
- **Members**: 15 (12 packages in packages/ + 3 docs)
- **Layer 0**: PKG-GENESIS-000, PKG-KERNEL-001
- **Layer 1**: PKG-VOCABULARY-001, PKG-REG-001
- **Layer 2**: PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001, PKG-LAYOUT-001
- **Layer 3**: PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001, PKG-PROMPT-ROUTER-001, PKG-LAYOUT-002

## Bugs Fixed (cumulative IDs continuing from MEMORY.md)

27. **layout.py _find_cp_root() hardcodes "Control_Plane_v2"**: Clean installs to arbitrary directories fail because `_find_cp_root()` walks parents looking for a directory named "Control_Plane_v2". Falls back to `cwd()` which is the bootstrap extraction dir, not the install dir. Fixed: check CONTROL_PLANE_ROOT env var first, then structural markers (HOT/kernel/ dir), then legacy name check, then cwd.

28. **pristine.py path classifications missing HOT prefix**: APPEND_ONLY_PATHS had `"ledger"` but rel paths are `"HOT/ledger/..."`. Added `"HOT/ledger"` to APPEND_ONLY_PATHS, `"HOT/kernel"`, `"HOT/scripts"`, etc. to PRISTINE_PATHS, and `"HOT/installed"` to DERIVED_PATHS.

29. **pristine.py audit ledger writes to root/ledger/**: `_log_event()` computed `plane / "ledger" / "governance.jsonl"` when plane was a Path. Fixed to `plane / "HOT" / "ledger" / "governance.jsonl"`.

30. **gate_check.py 5 dual-path fallbacks**: load_control_plane_registry, load_file_ownership_registry used `plane_root / 'registries'` as primary with HOT fallback. check_g1_chain used ternary fallbacks. check_g2_work_order and check_g6_ledger used `plane_root / 'ledger'` without HOT. All fixed to use HOT directly.

31. **layout.json HO3 ghost tier**: Removed from tiers. Correct model: HOT > HO2 > HO1 (3 tiers).
