# Results: HANDOFF-25 — Fix classify structured output + admin tool improvements

## Status: PASS

## Summary
Implemented HANDOFF-25 in `Control_Plane_v2/_staging/` with DTT flow:
1. Added tests first (HO1 + ADMIN), including regression tests for `output_json`, `tools_allowed`, ledger selection, and `list_files`.
2. Implemented the four scoped fixes across HO1 and ADMIN.
3. Fixed one additional scoped issue discovered during E2E: `list_files` failed when `--root` was a symlink path.
4. Updated manifest asset hashes using `hashing.py:compute_sha256()`.
5. Rebuilt package archives and `CP_BOOTSTRAP.tar.gz` using `packages.py:pack()`.
6. Completed clean-room install, reinstall-on-top, full regression, 8/8 gates, and E2E verification.

## Files Modified
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py`
  - SHA256 before: `sha256:116c30318956f206d0262faa0cdc321ba9942a06fb64488c5668bc75ff9793f9`
  - SHA256 after: `sha256:8b89991dbead75755aa3efb6633c75509ea9c192e78b5f95a80166aa16d1bd25`

- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py`
  - SHA256 before: `sha256:6ac22eda4eb26f5819a9653fc87f879261735db9a0d1e089fcd18a577ca3598e`
  - SHA256 after: `sha256:abc804c81939234f06295e0619355d84748fafaf9085db78ef4d8df8334b8f68`

- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/manifest.json`
  - SHA256 after: `sha256:5f1f18a9a3c7f4d36f6616e6af18ab7347d7c8049886bc4a549cc779d7108e91`

- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py`
  - SHA256 before: `sha256:e6d0bf4569e098258f071daa93219bdfbeac263a4d814af5b2dc288744c79269`
  - SHA256 after: `sha256:0871acace58bd3f998205335948e062e337161ac24da10b27165908d57a2f73f`

- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/config/admin_config.json`
  - SHA256 before: `sha256:053eaffa921570acef9f04aebe4955b1ad9664fe3a111f2228d23de483eb4eb7`
  - SHA256 after: `sha256:bb0088f32a01953ad8e918e52111956c8215d6e560bda7dbe683fa5f7fe9ef7f`

- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`
  - SHA256 before: `sha256:7bec5282b55583af3a13f0857532164797599012f589fd9538a219b363432e26`
  - SHA256 after: `sha256:2186f10638b7bd647aace7a3b1eac7c6aa5352edadbb14db0ebf429b664ff12a`

- `Control_Plane_v2/_staging/PKG-ADMIN-001/manifest.json`
  - SHA256 after: `sha256:9943a2687ec168d7e96b5e17561d2c315c6f7a10490096069c5d2f20d3d344e1`

## Archives Built
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001.tar.gz`
  - SHA256: `sha256:b80f123ff93e76b282e07c5e03c830e9e85ad284e4ac07d5f851f758aa1e0fb9`

- `Control_Plane_v2/_staging/PKG-ADMIN-001.tar.gz`
  - SHA256: `sha256:76fc611603e7e59e59f97655ce5dc331945999f487cb77255a3e6bbe5ca00eff`

- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz`
  - SHA256: `sha256:1d1b38bf2b22ae30fb2b34eb2e0993647340674b4696d79f833fa5e4d2f3e892`
  - Bootstrap package count: 21

## Test Results — Modified Package Suites
- Command:
  - `python3 -m pytest -q Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`
- Total: 106
- Passed: 106
- Failed: 0
- Skipped: 0

## Full Regression — ALL STAGED PACKAGES (Installed Clean-Room Root)
- Command:
  - `PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" python3 -m pytest "$IR/HOT/tests/" "$IR/HO1/tests/" "$IR/HO2/tests/" -v`
- Log: `/tmp/h25_cleanroom_final.zc4h9l/pytest_full.txt`
- Total: 533
- Passed: 533
- Failed: 0
- Skipped: 0
- New failures introduced by this agent: NONE

## Gate Check Results
- Command:
  - `PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" python3 "$IR/HOT/scripts/gate_check.py" --root "$IR" --all --enforce`
- Log: `/tmp/h25_cleanroom_final.zc4h9l/gates_all.txt`

Results:
- G0B: PASS
- G1: PASS
- G1-COMPLETE: PASS
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS
- Overall: PASS (8/8)

## Baseline Snapshot (AFTER this agent's work)
- Packages installed: 21
- `file_ownership.csv` rows: 142
- `file_ownership.csv` unique files: 112
- `file_ownership.csv` supersession rows: 0
- Total tests (all staged installed suites): 533
- Gate results: 8/8 PASS

## Clean-Room Verification
- Clean root: `/tmp/h25_cleanroom_final.zc4h9l`
- Install root: `/tmp/h25_cleanroom_final.zc4h9l/installed`
- Bootstrap extraction: PASS
- `install.sh --root <install-root> --dev`: PASS
- Reinstall-on-top (modified packages): PASS (`--force`)
  - `PKG-HO1-EXECUTOR-001`
  - `PKG-ADMIN-001`
- Full regression in clean-room: PASS
- Gate check in clean-room: PASS (8/8)
- Logs:
  - Extract stdout: `/tmp/h25_cleanroom_final.zc4h9l/extract_stdout.txt`
  - Extract stderr: `/tmp/h25_cleanroom_final.zc4h9l/extract_stderr.txt`
  - Install stdout: `/tmp/h25_cleanroom_final.zc4h9l/install_stdout.txt`
  - Install stderr: `/tmp/h25_cleanroom_final.zc4h9l/install_stderr.txt`
  - Reinstall HO1: `/tmp/h25_cleanroom_final.zc4h9l/install_pkg_ho1.txt`
  - Reinstall ADMIN: `/tmp/h25_cleanroom_final.zc4h9l/install_pkg_admin.txt`
  - Full pytest: `/tmp/h25_cleanroom_final.zc4h9l/pytest_full.txt`
  - Gates: `/tmp/h25_cleanroom_final.zc4h9l/gates_all.txt`

## E2E Verification (Admin Shell)
- Main sequence log: `/tmp/h25_cleanroom_final.zc4h9l/e2e_admin_h25.txt`
- Query-ledger ho2m log: `/tmp/h25_cleanroom_final.zc4h9l/e2e_query_ledger_ho2m.txt`

Verified outcomes:
- `admin> hello`
  - Natural-language reply (no JSON wrapping).
- `admin> what frameworks are installed?`
  - Tool call observed: `list_packages({})`
- `admin> show me turn events from the session ledger`
  - In explicit verification run, tool call observed:
    - `query_ledger({"ledger": "ho2m", "event_type": "TURN_RECORDED", "max_entries": 5})`
- `admin> what files are in the HOT/kernel directory?`
  - Tool call observed: `list_files({"path": "HOT/kernel"})`
  - Natural-language response returned with kernel file listing.

## Additional Issue Found (Within Scope) and Fixed
- File: `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py` (`_list_files`)
- Problem: when `--root` is a symlink/non-resolved path, `entry.relative_to(root)` raised `ValueError`, causing tool status `error` in real admin sessions.
- Fix: use `resolved_root = root.resolve()` consistently for traversal checks and relative path computation.
- Added test: `TestListFilesTool.test_list_files_handles_symlink_root` in `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py`.

## Issues Encountered
1. Hidden `.DS_Store` artifacts caused G0A undeclared-file failures for rebuilt archives.
2. Resolved by building package archives from sanitized temporary copies (excluding `.DS_Store` and `__pycache__`) while still using `packages.py:pack()`.

## Notes for Reviewer
- Scope remained within HANDOFF-25 file list plus required manifest/archive/result updates.
- `admin_config.schema.json` was intentionally unchanged per handoff clarification.
- Primary classify fix (`tools_allowed` filter restoration) and defense-in-depth (`output_json` interception) are both covered by HO1 tests and clean-room regression.
