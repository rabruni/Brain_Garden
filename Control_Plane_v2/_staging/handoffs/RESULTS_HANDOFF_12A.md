# Results: HANDOFF-12A — Fix pristine bypass ordering so boot_materialize runs under dev-mode bypass

## Status: PASS

## Files Created
- `Control_Plane_v2/_staging/RESULTS_HANDOFF_12A.md` (SHA256: N/A — self-referential document)

## Files Modified
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py` (SHA256 before: `5a33971a3e4e73834e4d4ee86ebb66f2e3d865fd26b4d03d852a7e849c8a4bc4`, after: `5775f595bfd5edd80e820063a1e98c943169037b6a2f67fdf04a31ead27bcecd`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` (SHA256 before: `19e6e27e293d3298ed0d35e02a1522f32fae902b0fcb651320dc236f839bed53`, after: `26c0ac45df81454cc0a637fd8ecc6e11793a82e0b63d47fae36b070505170f0f`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/manifest.json` (SHA256 before: `48d53b1fc77a9903c7c47b8082aa6735ce74b8d248eef6bf277b28debf3f85ba`, after: `c08ee1a4375242cde680bb03f980bed89b27145a6a577abffba53ac93a2a180d`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001.tar.gz` (SHA256 before: `f27db581500e684890314c7ba3da6a24ea285416e834805f78a796efb5f114e3`, after: `6887eefafc1189014fd005e50478091d326ce5c1e58cd97a0bc966c11029c4d0`)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256 before: `d5d3d81ba42f76bf464239633993dae19ecb5d099062fd605c72f5a922cb5e02`, after: `acc7ede98a2fcb878c949ffe3ffc63518c6c2a2f150071e9e4a124a6e6246cd9`)

## Archives Built
- `Control_Plane_v2/_staging/PKG-ADMIN-001.tar.gz` (SHA256: `6887eefafc1189014fd005e50478091d326ce5c1e58cd97a0bc966c11029c4d0`)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256: `acc7ede98a2fcb878c949ffe3ffc63518c6c2a2f150071e9e4a124a6e6246cd9`)

## Test Results — THIS PACKAGE
- Total: 3 tests
- Passed: 3
- Failed: 0
- Skipped: 0
- Command: `python3 -m pytest Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py -k TestBootMaterializeDevBypass -q`

## Additional Touched-Package Tests
- Total: 13 tests
- Passed: 13
- Failed: 0
- Skipped: 0
- Command: `python3 -m pytest Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py -q`

## Full Regression Test — ALL STAGED PACKAGES
- Total: 319 collected before interruption
- Passed: N/A (collection interrupted)
- Failed: 2 collection errors
- Skipped: N/A
- Command: `python3 -m pytest Control_Plane_v2/_staging/ -v --ignore=Control_Plane_v2/_staging/PKG-FLOW-RUNNER-001`
- New failures introduced by this agent: NONE observed in touched package tests.
- Collection blockers are pre-existing:
  - `Control_Plane_v2/_staging/PKG-ATTENTION-001/HOT/tests/test_attention_service.py` (`ModuleNotFoundError: kernel`)
  - `Control_Plane_v2/_staging/PKG-LAYOUT-002/HOT/tests/test_layout.py` (import-file mismatch with `PKG-LAYOUT-001` test basename)

## Gate Check Results
- G0B: PASS (93 files, 0 orphans)
- G1: PASS (15 chains)
- G1-COMPLETE: PASS (15 frameworks)
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS (3 ledger files, 82 entries)
- Overall: PASS (8/8)
- Command: `python3 /tmp/h12a_verify.vFi9Ht/cp_root/HOT/scripts/gate_check.py --root /tmp/h12a_verify.vFi9Ht/cp_root --all`

## Baseline Snapshot (AFTER this agent's work)
- Packages installed: 17
- Installed package IDs:
  - `PKG-ADMIN-001`, `PKG-ANTHROPIC-PROVIDER-001`, `PKG-ATTENTION-001`, `PKG-BOOT-MATERIALIZE-001`, `PKG-FRAMEWORK-WIRING-001`, `PKG-GENESIS-000`, `PKG-GOVERNANCE-UPGRADE-001`, `PKG-KERNEL-001`, `PKG-LAYOUT-001`, `PKG-LAYOUT-002`, `PKG-PHASE2-SCHEMAS-001`, `PKG-PROMPT-ROUTER-001`, `PKG-REG-001`, `PKG-SESSION-HOST-001`, `PKG-SPEC-CONFORMANCE-001`, `PKG-TOKEN-BUDGETER-001`, `PKG-VOCABULARY-001`
- `file_ownership.csv`: 107 data rows (93 unique files, 7 supersession rows)
- Total tests (all staged command): 319 collected before 2 collection errors
- Gate results: G0B PASS, G1 PASS, G1-COMPLETE PASS, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS

## Clean-Room Verification
- Bootstrap archive package count: 17 (`tar tzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz | grep '^packages/PKG-.*\\.tar\\.gz$' | wc -l`)
- Install command: `bash /tmp/h12a_verify.vFi9Ht/install.sh --root /tmp/h12a_verify.vFi9Ht/cp_root --dev`
- Install result: 17 total packages, 17 receipts in `/tmp/h12a_verify.vFi9Ht/cp_root/HOT/installed`
- Gate result after install: 8/8 PASS
- Smoke proof command: `python3 /tmp/h12a_verify.vFi9Ht/cp_root/HOT/admin/main.py --root /tmp/h12a_verify.vFi9Ht/cp_root --dev <<< "exit"`
- Smoke output: session starts and exits cleanly (no `WriteViolation`), and boot materialization creates HO2/HO1 directories and governance ledgers.
- Verified files after smoke:
  - `/tmp/h12a_verify.vFi9Ht/cp_root/HO2/tier.json`
  - `/tmp/h12a_verify.vFi9Ht/cp_root/HO2/ledger/governance.jsonl`
  - `/tmp/h12a_verify.vFi9Ht/cp_root/HO1/tier.json`
  - `/tmp/h12a_verify.vFi9Ht/cp_root/HO1/ledger/governance.jsonl`
- Logs:
  - `/tmp/h12a_verify.vFi9Ht/install_stdout.txt`
  - `/tmp/h12a_verify.vFi9Ht/install_stderr.txt`
  - `/tmp/h12a_verify.vFi9Ht/gates_all.txt`
  - `/tmp/h12a_verify.vFi9Ht/admin_smoke_stdout.txt`
  - `/tmp/h12a_verify.vFi9Ht/admin_smoke_stderr.txt`

## Issues Encountered
- Initial reorder placed pristine patching before `_ensure_import_paths()`, which caused `ModuleNotFoundError: kernel` in isolated test execution. Final fix keeps `_ensure_import_paths()` first, then starts dev bypass before `boot_materialize()`.
- Full staged regression remains blocked by pre-existing collection issues outside HANDOFF-12A scope.

## Notes for Reviewer
- `run_cli()` now executes in dev mode order: `_ensure_import_paths()` → start pristine bypass → `boot_materialize(root)` → `build_session_host()` → session loop.
- `pristine_patch.stop()` remains in `finally` with `if pristine_patch is not None` guard.
- No changes made to `boot_materialize.py`, `ledger_client.py`, or `pristine.py`.
