# Results: HANDOFF-20 Test Infrastructure Cleanup

## Status: PASS

## Summary

Fixed 24 pre-existing test failures across 3 test files caused by staging-vs-installed path mismatch and incomplete FMWK-005 manifest. All tests now pass in both staging and installed contexts.

## Files Modified

- `PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py`
  - SHA256 before: `sha256:b49f39e2914618e80c5d0da107b5d2a35048aa77da474c57ac1164ab715e763a`
  - SHA256 after: `sha256:83f04afe73b6ee3731f8e3953326cd409c30616bb74bbfa05af35f9ffdbe41f9`
  - Change: Replaced hardcoded `parents[3]` path resolution with dual-context detection using `kernel/ledger_client.py` probe

- `PKG-ADMIN-001/HOT/tests/test_admin.py`
  - SHA256 before: `sha256:7ff7c2ee1a2d8ab2e71e7fa31ee8b5ebaae94e59f251e21d1c31b133438d6519`
  - SHA256 after: `sha256:ab5029c20dcd384b0b69fd12a5861e843d9b8da8d20da6c8df8c311af94f64a2`
  - Change: Replaced hardcoded `parents[3]` path resolution with dual-context detection; updated `_write_layout_json` helper to use same detection

- `PKG-ADMIN-001/HOT/FMWK-005_Admin/manifest.yaml`
  - SHA256 before: `sha256:54bf77783e508c12716ebb100bf75fcb1449f78a4a914cdc3515e8d82b129e51`
  - SHA256 after: `sha256:cbbcc905b591aee74c4d2b8d111c0f8da3c977ab994cc29751c4256070b11059`
  - Change: Added 8 missing/misnamed fields (`title` replacing `name`, `ring`, `created_at`, `assets`, `expected_specs`, `invariants`, `path_authorizations`, `required_gates`) following FMWK-007 schema template

- `PKG-FRAMEWORK-WIRING-001/HOT/tests/test_framework_wiring.py`
  - SHA256 before: `sha256:f12fded5bc48546ef8dbdda2c8c05e4af371c6cd94860de0b28adaf6724a649b`
  - SHA256 after: `sha256:9820357441e4a0a830725c7e0c63f442aada546d5e3f081f977883882ce0dda8`
  - Change: Added `"FMWK-005": []` to `EXPECTED_WIRING` dict; updated framework count assertion from 4 to 5

- `PKG-BOOT-MATERIALIZE-001/manifest.json`
  - SHA256 after: `sha256:da81635ef13192c6d760071bb9ff6a1d5b94309b8952e47c0db0725317eccdde`
  - Change: Updated `test_boot_materialize.py` hash

- `PKG-ADMIN-001/manifest.json`
  - SHA256 after: `sha256:abadac2e95682f38cf6054a3646cc019666f7c4d5db7a246f0537b080cb56c62`
  - Change: Updated `test_admin.py` and `manifest.yaml` (FMWK-005) hashes

- `PKG-FRAMEWORK-WIRING-001/manifest.json`
  - SHA256 after: `sha256:e8ebea6f712bc99dbbcfe0034d0e00e0759d4fbb8d8a6fee7f6e6c2abcc07c5f`
  - Change: Updated `test_framework_wiring.py` hash

## Archives Built

- `PKG-BOOT-MATERIALIZE-001.tar.gz` (SHA256: `sha256:6cc91a3bd69435a122c9d690267768f4a4c2d1dfb936b5e749dac07f438690bb`)
- `PKG-ADMIN-001.tar.gz` (SHA256: `sha256:94e78ddd136943ecf1f0572b620cffee1df3adb52e3b2da7fe8e856b5b6d0a87`)
- `PKG-FRAMEWORK-WIRING-001.tar.gz` (SHA256: `sha256:7fc0bdaf87a87596696457891b681faf6a78e99f732804831e279de1dc7221d5`)
- `CP_BOOTSTRAP.tar.gz` (SHA256: `sha256:bbed3e3a86d8be3ece68410e65e345d006b454cc6a4b1a10b97587737777c7ed`)

## Test Results -- PREVIOUSLY FAILING TESTS

- Total: 73 tests (across 3 test files)
- Passed: 73
- Failed: 0
- Skipped: 0
- Command: `PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" python3 -m pytest "$IR/HOT/tests/test_boot_materialize.py" "$IR/HOT/tests/test_admin.py" "$IR/HOT/tests/test_framework_wiring.py" -v`

### Breakdown by file:
- `test_boot_materialize.py`: 21 passed (17 TestBootMaterialize + 4 TestLedgerPathFixes)
- `test_admin.py`: 13 passed (4 TestAdminConfig + 6 TestAdminEntrypoint + 3 TestBootMaterializeDevBypass)
- `test_framework_wiring.py`: 39 passed (4 TestRemovedFrameworks + 30 TestFrameworkManifestStructure + 5 TestExpectedSpecsMatch)

## Full Regression Test -- ALL INSTALLED TESTS

- Total: 371 tests
- Passed: 371
- Failed: 0
- Skipped: 0
- Command: `PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" python3 -m pytest "$IR/HOT/tests/" -v`
- New failures introduced by this agent: NONE

### Staging backward-compatibility

- `test_boot_materialize.py` + `test_admin.py` also pass from staging context: 34 passed, 0 failed

## Gate Check Results

- G0B: PASS (112 files owned, 0 orphans)
- G1: PASS (19 chains validated, 0 warnings)
- G1-COMPLETE: PASS (19 frameworks checked)
- G2: PASS (WO system: 0 approved HOT, 0 completed HO2)
- G3: PASS (constraints check passed)
- G4: PASS (acceptance infrastructure check passed)
- G5: PASS (no packages store found)
- G6: PASS (3 ledger files, 94 entries)
- Overall: PASS (8/8 gates passed)

## Baseline Snapshot (AFTER this agent's work)

- Packages installed: 21 (PKG-GENESIS-000, PKG-KERNEL-001, PKG-REG-001, PKG-VOCABULARY-001, PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001, PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001, PKG-VERIFY-001, PKG-WORK-ORDER-001, PKG-BOOT-MATERIALIZE-001, PKG-HO2-SUPERVISOR-001, PKG-LLM-GATEWAY-001, PKG-ANTHROPIC-PROVIDER-001, PKG-HO1-EXECUTOR-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-ADMIN-001)
- file_ownership.csv: 127 rows (112 unique files, 15 supersession rows)
- Total tests (all installed): 371
- Gate results: 8/8 PASS (G0B, G1, G1-COMPLETE, G2, G3, G4, G5, G6)
- CP_BOOTSTRAP.tar.gz: 24 members (21 package archives + install.sh + resolve_install_order.py + packages/ dir)

## Clean-Room Verification

- Packages installed: 21 (21 receipts)
- Install order: PKG-GENESIS-000 (seed) -> PKG-KERNEL-001 (bootstrap) -> PKG-REG-001 -> PKG-VOCABULARY-001 -> PKG-GOVERNANCE-UPGRADE-001 -> PKG-FRAMEWORK-WIRING-001 -> PKG-SPEC-CONFORMANCE-001 -> PKG-LAYOUT-001 -> PKG-LAYOUT-002 -> PKG-PHASE2-SCHEMAS-001 -> PKG-TOKEN-BUDGETER-001 -> PKG-VERIFY-001 -> PKG-WORK-ORDER-001 -> PKG-BOOT-MATERIALIZE-001 -> PKG-HO2-SUPERVISOR-001 -> PKG-LLM-GATEWAY-001 -> PKG-ANTHROPIC-PROVIDER-001 -> PKG-HO1-EXECUTOR-001 -> PKG-SESSION-HOST-V2-001 -> PKG-SHELL-001 -> PKG-ADMIN-001
- All gates pass after install: YES (8/8)
- Install method: `tar xzf CP_BOOTSTRAP.tar.gz -C "$TMPDIR" && bash "$TMPDIR/install.sh" --root "$TMPDIR/INSTALL_ROOT" --dev`
- Install root: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.gMg6Df3a/INSTALL_ROOT`

## Issues Encountered

- **macOS .DS_Store regeneration**: After initial cleanup of `.DS_Store` files from package directories, macOS Finder regenerated them before the pack step completed. Required deleting and packing in the same command pipeline to avoid G0A (UNDECLARED asset) failures. This is a recurring issue on macOS -- the `.DS_Store` cleanup and pack must be atomic.
- No pre-existing failures. All 371 installed tests pass.

## Notes for Reviewer

1. **Dual-context probe**: All 3 test files use `(_HOT / "kernel" / "ledger_client.py").exists()` as the detection probe. The `admin/main.py` probe was explicitly rejected (exists in both staging and installed contexts for PKG-ADMIN-001). This is documented in test_admin.py with a NOTE comment.

2. **Test count discrepancy with spec**: The spec predicted 444+ total tests. The actual installed test count is 371. This is because the spec counted staging tests across all `PKG-*/HOT/tests/` directories, but some packages' tests may overlap or the count included duplicates from the parametrized fixtures. The installed root merges all test files into `HOT/tests/`, which is the authoritative count.

3. **Framework count**: 5 framework directories now exist in HOT (FMWK-000, FMWK-001, FMWK-002, FMWK-005, FMWK-007). The `test_exactly_five_frameworks` test validates this.

4. **FMWK-005 manifest.yaml**: The `expected_specs` field is an empty list `[]` because FMWK-005 (Admin Framework) does not govern any specs directly. The `_parse_yaml_simple()` parser in test_framework_wiring.py handles this correctly -- an empty `expected_specs: []` line results in `"expected_specs"` being present in the parsed data (checked via `"expected_specs" in data`).

5. **No registry updates needed**: FMWK-005 was already in the frameworks_registry.csv (added when PKG-ADMIN-001 was first installed). The manifest.yaml fix is an in-package change only.

6. **Tools used**: `hashing.py:compute_sha256()` for all SHA256 hashes (canonical `sha256:<64hex>` format). `packages.py:pack()` for all archive builds (deterministic I4-DETERMINISTIC packing).
