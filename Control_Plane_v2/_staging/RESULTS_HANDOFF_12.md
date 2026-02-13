# Results: HANDOFF-12 — PKG-BOOT-MATERIALIZE-001 boot-time materialization + ledger path fix

## Status: PARTIAL

## Files Created
- `Control_Plane_v2/_staging/PKG-BOOT-MATERIALIZE-001/HOT/scripts/boot_materialize.py` (SHA256: `eccf4e2e320854aa4e5dfecb05f953ea37509b74fcf074c511ec2a3370b795c8`)
- `Control_Plane_v2/_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py` (SHA256: `b49f39e2914618e80c5d0da107b5d2a35048aa77da474c57ac1164ab715e763a`)
- `Control_Plane_v2/_staging/PKG-BOOT-MATERIALIZE-001/manifest.json` (SHA256: `127bcb7c2a465a634a85ecadbabf7ce5c709d05712f1003d0771de74a61e1eda`)

## Files Modified
- `Control_Plane_v2/_staging/PKG-KERNEL-001/HOT/kernel/ledger_client.py` (SHA256 before: `eb73a80399ec7043474950ceb21cdf960aa0fdd46bb0c2c498d4dd60ddfcf3d0`, after: `bcbb0056cd8485695a61973fa3f2a0d073c9193afb45151fb1a0c8b63a35c1b1`)
- `Control_Plane_v2/_staging/PKG-KERNEL-001/manifest.json` (SHA256 after: `4566370f4248b47db0f20b7dbc83e2aee341a861dfe97cd330354ee694e78ddf`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py` (SHA256 before: `85df1b27f09991dc076fa536cf4ac12ccf46df2046b9f57b93fdfc86b71e9fc7`, after: `5a33971a3e4e73834e4d4ee86ebb66f2e3d865fd26b4d03d852a7e849c8a4bc4`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/manifest.json` (SHA256 after: `48d53b1fc77a9903c7c47b8082aa6735ce74b8d248eef6bf277b28debf3f85ba`)
- `Control_Plane_v2/_staging/PKG-GENESIS-000/HOT/config/seed_registry.json` (SHA256 before: `87936f889e0d9bf9d713b21839b7712dca9b78a748dc67fe03e223c197980bcf`, after: `7d3dfa148af38056e1b37380e426afd641a8e5948a51ad7e706a8982231a8e8f`)
- `Control_Plane_v2/_staging/PKG-GENESIS-000/manifest.json` (SHA256 after: `8d6a608810c88fade51956df14145e2f40d547ad953bfe1efb5a3d792f2d2e11`)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256 after: `d5d3d81ba42f76bf464239633993dae19ecb5d099062fd605c72f5a922cb5e02`)

## Archives Built
- `Control_Plane_v2/_staging/PKG-BOOT-MATERIALIZE-001.tar.gz` (SHA256: `658c1d3629fa6d68e2c3495d6d991e1b8c0a0bd65182ae19326de68d1fc87296`)
- `Control_Plane_v2/_staging/PKG-KERNEL-001.tar.gz` (SHA256: `e3373b6e24ff7c6ea7da9c66c98328b0685fe0053bef5ce48ecfac0fa5e9bcb2`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001.tar.gz` (SHA256: `f27db581500e684890314c7ba3da6a24ea285416e834805f78a796efb5f114e3`)
- `Control_Plane_v2/_staging/PKG-GENESIS-000.tar.gz` (SHA256: `46615079665f5eb7b3d2df2f61525293c9fcfbc223ca89a763beed43480d7959`)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256: `d5d3d81ba42f76bf464239633993dae19ecb5d099062fd605c72f5a922cb5e02`)

## Test Results — THIS PACKAGE
- Total: 21 tests
- Passed: 21
- Failed: 0
- Skipped: 0
- Command: `python3 -m pytest Control_Plane_v2/_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py -q`

## Additional Touched-Package Tests
- Total: 31 tests
- Passed: 31
- Failed: 0
- Skipped: 0
- Command: `python3 -m pytest Control_Plane_v2/_staging/PKG-BOOT-MATERIALIZE-001/HOT/tests/test_boot_materialize.py Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py -q`

## Full Regression Test — ALL STAGED PACKAGES
- Total: 316 collected before interruption
- Passed: N/A (collection interrupted)
- Failed: 2 collection errors
- Skipped: N/A
- Command: `python3 -m pytest Control_Plane_v2/_staging/. -v --ignore=PKG-FLOW-RUNNER-001`
- New failures introduced by this agent: NONE observed in touched package suites (`PKG-BOOT-MATERIALIZE-001`, `PKG-ADMIN-001`).
- Collection blockers are pre-existing:
  - `PKG-ATTENTION-001/HOT/tests/test_attention_service.py` (`ModuleNotFoundError: kernel`)
  - `PKG-LAYOUT-002/HOT/tests/test_layout.py` import-file mismatch with `PKG-LAYOUT-001` test basename

## Gate Check Results
- G0B: PASS (93 files, 0 orphans)
- G1: PASS (15 chains)
- G1-COMPLETE: PASS (15 frameworks)
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS (3 ledger files, 84 entries)
- Overall: PASS (8/8)
- Command: `python3 <install_root>/HOT/scripts/gate_check.py --root <install_root> --all`

## Baseline Snapshot (AFTER this agent's work)
- Packages installed: 17
- Installed package IDs:
  - `PKG-ADMIN-001`, `PKG-ANTHROPIC-PROVIDER-001`, `PKG-ATTENTION-001`, `PKG-BOOT-MATERIALIZE-001`, `PKG-FRAMEWORK-WIRING-001`, `PKG-GENESIS-000`, `PKG-GOVERNANCE-UPGRADE-001`, `PKG-KERNEL-001`, `PKG-LAYOUT-001`, `PKG-LAYOUT-002`, `PKG-PHASE2-SCHEMAS-001`, `PKG-PROMPT-ROUTER-001`, `PKG-REG-001`, `PKG-SESSION-HOST-001`, `PKG-SPEC-CONFORMANCE-001`, `PKG-TOKEN-BUDGETER-001`, `PKG-VOCABULARY-001`
- `file_ownership.csv`: 107 data rows (93 unique files, 7 supersession rows)
- Total tests (all staged command): 316 collected before 2 collection errors
- Gate results: G0B PASS, G1 PASS, G1-COMPLETE PASS, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS

## Clean-Room Verification
- `CP_BOOTSTRAP.tar.gz` package count: 17 (`tar tzf ... | grep '.tar.gz' | wc -l`)
- Install command: `bash install.sh --root <install_root> --dev`
- Install result: 17 total packages (2 Layer-0 + 15 resolver-installed), 17 receipts
- Gate result after install: 8/8 PASS
- Boot materialization verification:
  - `boot_materialize(root)` returns `0`
  - `HO2/` and `HO1/` directories + `tier.json` + `ledger/governance.jsonl` created
  - Chain link checks immediately after materialization: `HO2->HOT=True`, `HO1->HO2=True`
- ADMIN smoke:
  - Command: `python3 <install_root>/HOT/admin/main.py --root <install_root> --dev <<< "exit"`
  - Result: session starts and exits cleanly
- Path fix verification:
  - `get_session_ledger_path("ho2", "SES-001", root=Path("/cp"))` -> `/cp/HO2/sessions/SES-001/ledger/exec.jsonl`
  - `planes/` not present
- Logs:
  - `/tmp/h12_install3_stdout.txt`
  - `/tmp/h12_install3_stderr.txt`
  - `/tmp/h12_boot3_verify.txt`
  - `/tmp/h12_admin3_stdout.txt`
  - `/tmp/h12_admin3_stderr.txt`
  - `/tmp/h12_gate3.txt`
  - `/tmp/h12_path3.txt`

## Issues Encountered
- Updating `PKG-KERNEL-001.tar.gz` changed Layer-0 digest; `PKG-GENESIS-000/HOT/config/seed_registry.json` had to be updated and `PKG-GENESIS-000.tar.gz` rebuilt to keep cold-boot verification valid.
- Full staged regression command is blocked by pre-existing collection errors unrelated to this handoff.
- `HO2->HOT` chain verification can fail after additional HOT writes (for example after ADMIN session activity); validation is correct immediately after materialization before parent ledger advances.

## Notes for Reviewer
- `boot_materialize.py` derives tier roots and ledger subpaths from `HOT/config/layout.json` (`tiers`, `tier_dirs`, `ledger_files`) and does not hardcode HO2/HO1 directory names.
- `main.py` now calls `boot_materialize()` before `build_session_host()` and continues on non-zero result with a warning.
- `ledger_client.py` helper paths now consistently use `<root>/<TIER>/...` (uppercase normalization, no `planes/` prefix).
