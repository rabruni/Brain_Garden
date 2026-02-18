# Results: HOUSEKEEPING-28 System Health

## Status: PASS

## Summary
1. Rebuilt `CP_BOOTSTRAP.tar.gz` in `_staging` with the 21-package set, explicitly excluding `PKG-ATTENTION-001.tar.gz`.
2. No code, test, or manifest files were modified.
3. Clean-room install/test/gates all passed.
4. The framework regression (`test_exactly_five_frameworks`) is resolved in clean-room.

## Files Modified
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256: `sha256:05f466e008ded46b9d5f8363231cab358ea801e35a20751a22b48591eaf90a69`)

## Files Created
- `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_28.md`

## Archives Built
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz`
  - SHA256: `sha256:05f466e008ded46b9d5f8363231cab358ea801e35a20751a22b48591eaf90a69`
  - Members: 24 total
  - Packages: 21 total
  - `PKG-ATTENTION-001.tar.gz`: not present

## Test Results — THIS HANDOFF
- No new tests added (housekeeping-only handoff).
- Focus regression check:
  - Command: `python3 -m pytest "$TMPDIR/HOT/tests/test_framework_wiring.py::TestRemovedFrameworks::test_exactly_five_frameworks" -v`
  - Result: **1 passed, 0 failed**

## Full Regression — Clean-Room Installed System (MANDATORY)
- Command:
  - `PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -q`
- Result: **608 passed, 0 failed**
- Direction vs H-27 (648): **DOWN**, expected, because ATTENTION package tests are no longer installed.
- New failures introduced: **NONE**

## Clean-Room Verification
- Clean-room root:
  - `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.pbWj3yNa`
- Install command:
  - `tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"`
  - `bash "$TMPDIR/install.sh" --root "$TMPDIR" --dev`
- Results:
  - Install: **PASS**
  - Full tests: **608 passed, 0 failed**
  - Framework check: **test_exactly_five_frameworks passed**
  - Gates: **8/8 PASS**
- Logs:
  - Install: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.pbWj3yNa/install.log`
  - Pytest all: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.pbWj3yNa/pytest_all.log`
  - Pytest framework: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.pbWj3yNa/pytest_framework.log`
  - Gates: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.pbWj3yNa/gates.log`

## Gate Check Results (Clean-Room)
- G0B: PASS
- G1: PASS
- G1-COMPLETE: PASS
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS
- Overall: **PASS (8/8)**

## Baseline Snapshot (AFTER this handoff)
- Baseline root: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.pbWj3yNa`
- Packages installed: **21**
- Installed package IDs:
  - `PKG-ADMIN-001, PKG-ANTHROPIC-PROVIDER-001, PKG-BOOT-MATERIALIZE-001, PKG-FRAMEWORK-WIRING-001, PKG-GENESIS-000, PKG-GOVERNANCE-UPGRADE-001, PKG-HO1-EXECUTOR-001, PKG-HO2-SUPERVISOR-001, PKG-KERNEL-001, PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-LLM-GATEWAY-001, PKG-PHASE2-SCHEMAS-001, PKG-REG-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-SPEC-CONFORMANCE-001, PKG-TOKEN-BUDGETER-001, PKG-VERIFY-001, PKG-VOCABULARY-001, PKG-WORK-ORDER-001`
- `file_ownership.csv` rows: **126**
- Unique files: **112**
- Supersession rows: **14**
- Total tests (clean-room HOT+HO1+HO2): **608 passed**
- Gate results: **8/8 PASS**

## Issues Encountered
1. None blocking. Clean-room install/test/gates passed on first run after rebuild.
2. `tar` prints `Failed to set default locale` in this environment; does not affect archive validity or install behavior.

## Notes for Reviewer
- Scope stayed narrow as requested: no code/test/manifest edits, no writes outside `_staging` (except ephemeral temp dirs).
- `PKG-ATTENTION-001` remains present in `_staging/` and was only excluded from bootstrap membership.
