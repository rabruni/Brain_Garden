# Results: HANDOFF-21 — Tool-Use Wiring Governance

## Status: PASS

## Files Modified

| Package | File | SHA256 Before | SHA256 After |
|---------|------|---------------|--------------|
| PKG-HO2-SUPERVISOR-001 | HO2/kernel/ho2_supervisor.py | sha256:39a45582c03d3a627e816c8c45456d4d6cc01d77bd83f3f157c7c85b7211821f | sha256:f71be94713520c6c85461ed27239baf91b1350a4f63afd6302ade9e0add86eda |
| PKG-HO2-SUPERVISOR-001 | HO2/tests/test_ho2_supervisor.py | sha256:c0b93be82c1a33b0e7c0731a0df5548c645161d0b5b7bd92b2ae2c30116e56aa | sha256:ea820e6fda599e39b9e583675f368eafa99bd799ec95beebb59f253e5cf5c062 |
| PKG-HO1-EXECUTOR-001 | HO1/kernel/ho1_executor.py | sha256:2d34f6b28c28eee51040a33cbea9aea1220ba7c34d955b7fe6cd6d084165cffa | sha256:98620385bed09cc791f827b2fffcf695334ee199e5b3d833a4e55f03c6265eed |
| PKG-HO1-EXECUTOR-001 | HO1/tests/test_ho1_executor.py | sha256:4de30dd41d52b72145d9b555e66c970f4976b45ce680a16a774941af90f49b72 | sha256:ed51021b5d73dcfcfcc96e54f7bca2908855e1289265b60de9508b1f96880d92 |
| PKG-LLM-GATEWAY-001 | HOT/kernel/llm_gateway.py | sha256:3b0e9cf08c80bc3c5275ab11eb49f670f90853386a9b2eb6204c5175b52ed647 | sha256:c0ce1e537e4c26a19c418d1ace82f00c4c80a0e9e97d7e32499705288c3bc53b |
| PKG-LLM-GATEWAY-001 | HOT/tests/test_llm_gateway.py | sha256:f4b6cef27a393a931872528d61f2e48024d2f368b81848a5bf56fe6205a38fe4 | sha256:6dcf28d044bc366c0cf3446238b2b6af5cb930e19184659f6479696c23aed628 |
| PKG-ADMIN-001 | HOT/admin/main.py | sha256:24fbb23d5b08ba2ffa4d8261b7a45375ecb2d29f092567ff5ef56e4093ce33bc | sha256:978c0a5bfbabb31b515c229b8bb6a968e00b2edb942c6289314fe46ee0318f1b |
| PKG-ADMIN-001 | HOT/tests/test_admin.py | sha256:ab5029c20dcd384b0b69fd12a5861e843d9b8da8d20da6c8df8c311af94f64a2 | sha256:37796344780af66d4ef11ede586bd5ed1fa1236c859e464a6d3f6fca90daee58 |

Manifests updated (4):
- PKG-HO2-SUPERVISOR-001/manifest.json
- PKG-HO1-EXECUTOR-001/manifest.json
- PKG-LLM-GATEWAY-001/manifest.json
- PKG-ADMIN-001/manifest.json

## Archives Built

| Archive | SHA256 |
|---------|--------|
| PKG-HO2-SUPERVISOR-001.tar.gz | sha256:0c65f8fa2ddd460b3d17768869d701a03c8af109e2124b06ddffcac2cbd5ee25 |
| PKG-HO1-EXECUTOR-001.tar.gz | sha256:fa7ccd9307da324023ade4c4ca8c58ab8eb9a04aabd6ac221f7a2250046e39d3 |
| PKG-LLM-GATEWAY-001.tar.gz | sha256:8ff9091a1f7bda07e7ed9f932f9d41faad0c598b915d9264a4bf5cc918f90933 |
| PKG-ADMIN-001.tar.gz | sha256:ebed20a89cdca8a39c0a67a4572b88f5403e50707e5d83f4e91cce3465e2566b |
| CP_BOOTSTRAP.tar.gz | sha256:d57d8a60d0717f4ebd7738b20551d0b55769622d949e9c5b82574bbb512ae0cc |

All archives built with `packages.py:pack()` (deterministic, I4-DETERMINISTIC).

## Test Results — Package-Local (4 packages)

| Package | Total | Passed | Failed | Skipped |
|---------|-------|--------|--------|---------|
| PKG-HO2-SUPERVISOR-001 | 54 | 54 | 0 | 0 |
| PKG-HO1-EXECUTOR-001 | 59 | 59 | 0 | 0 |
| PKG-LLM-GATEWAY-001 | 20 | 20 | 0 | 0 |
| PKG-ADMIN-001 | 14 | 14 | 0 | 0 |
| **Total** | **147** | **147** | **0** | **0** |

New tool-use test classes:
- `TestToolUseWiring` (HO2): 7 tests
- `TestToolUseWiring` (HO1): 9 tests
- `TestToolUseObservability` (Gateway): 2 tests
- `TestToolUseWiring` (Admin): 1 test
- **Total new tests: 19**

## Full Regression Test — ALL PACKAGES (from installed root)

- Total: 487 tests
- Passed: 487
- Failed: 0
- Skipped: 0
- Command: `PYTHONPATH="$IR/HOT/kernel:$IR/HOT:$IR/HOT/scripts:$IR/HOT/admin:$IR/HO1/kernel:$IR/HO2/kernel" python3 -m pytest "$IR/HOT/tests/" "$IR/HO1/tests/" "$IR/HO2/tests/" -v`
- New failures introduced: **NONE**
- Delta from baseline: +19 tests (468 → 487)

## Gate Check Results

Run with `--all --enforce` from installed root:

- G0B: PASS (112 files owned, 0 orphans)
- G1: PASS (19 chains validated, 0 warnings)
- G1-COMPLETE: PASS (19 frameworks checked)
- G2: PASS (WO system: 0 approved, 0 completed)
- G3: PASS (Constraints check passed)
- G4: PASS (Acceptance infrastructure check passed)
- G5: PASS (No packages store found)
- G6: PASS (3 ledger files, 94 entries)

Overall: **PASS (8/8 gates passed)**

## Clean-Room Verification

- Bootstrap extracted to temp dir
- `install.sh --root "$TMPDIR/INSTALL_ROOT" --dev`
- Packages installed: 21 (2 bootstrap + 19 dependency-ordered)
- Install order: PKG-GENESIS-000 → PKG-KERNEL-001 → PKG-REG-001 → PKG-VOCABULARY-001 → PKG-GOVERNANCE-UPGRADE-001 → PKG-FRAMEWORK-WIRING-001 → PKG-SPEC-CONFORMANCE-001 → PKG-LAYOUT-001 → PKG-LAYOUT-002 → PKG-PHASE2-SCHEMAS-001 → PKG-TOKEN-BUDGETER-001 → PKG-VERIFY-001 → PKG-WORK-ORDER-001 → PKG-BOOT-MATERIALIZE-001 → PKG-HO2-SUPERVISOR-001 → PKG-LLM-GATEWAY-001 → PKG-ANTHROPIC-PROVIDER-001 → PKG-HO1-EXECUTOR-001 → PKG-SESSION-HOST-V2-001 → PKG-SHELL-001 → PKG-ADMIN-001
- All gates pass after install: **YES** (8/8)

## Baseline Snapshot (AFTER this handoff)

- Packages installed: 21
- file_ownership.csv rows: 127 (including header)
- Total tests (from installed root): 487
- Gate results: G0B PASS, G1 PASS, G1-COMPLETE PASS, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS (8/8)
- CP_BOOTSTRAP.tar.gz packages: 21

## Issues Encountered

1. **macOS .DS_Store recreation**: After cleaning .DS_Store files from package directories, macOS Finder recreated them before `pack()` ran. Required a second delete-then-immediately-pack cycle to produce clean archives. First install attempt failed G0A (`UNDECLARED: '.DS_Store'`).

2. **No code changes required**: All tool-use wiring code was verified correct against Section 3 design by the previous agent. This handoff was purely governance (hash update → archive rebuild → clean-room verify).

## Notes for Reviewer

- **Scope**: This handoff performed NO code changes. All 8 files were modified by a previous agent who bypassed governance. This handoff brings them back into compliance (manifest hashes, archives, clean-room verification).
- **Delta**: 468 → 487 tests (+19). All 19 are tool-use wiring tests spread across 4 packages.
- **All hashes computed with `hashing.py:compute_sha256()`**, all archives built with `packages.py:pack()`.
- **Previous manifest hashes** (before column) are the old values that no longer matched the modified files. New hashes (after column) match the actual file contents.
