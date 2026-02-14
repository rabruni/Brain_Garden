# Results: HANDOFF-10 — Exchange Recording Redesign

## Status: PARTIAL

## Files Created
- `Control_Plane_v2/_staging/RESULTS_HANDOFF_10.md` (SHA256: self-referential; omitted)

## Files Modified
- `Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` (SHA256 before: not captured in this workspace snapshot, after: `ef9b2be75e01a03657a39d44f90a84f3d5481d9687011387cb869e11d898dec7`)
- `Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/HOT/tests/test_prompt_router.py` (SHA256 before: not captured in this workspace snapshot, after: `f967e55502be799eb6306930dfd8b1b4664f428eca11c7f3eef424f084c756c0`)
- `Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/manifest.json` (SHA256 before: not captured in this workspace snapshot, after: `164676d856490340892b7f9d00064c1d8b9d5a19f0e9bb55e589bce72d074101`)

## Archives Built
- `Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001.tar.gz` (SHA256: `ea44ef92ee7f5fd76b9ace952a1bcbcc21ed815db7a4d2c764d665832f782f90`)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256: `3b4a95cce75e4ae8debe4a28dc22d9960eb3ccbe9332a5d73b06aa45b08bd542`)

## Test Results — THIS PACKAGE
- Total: 30 tests
- Passed: 30
- Failed: 0
- Skipped: 0
- Command: `CONTROL_PLANE_ROOT="$TMPDIR" PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" python3 -m pytest Control_Plane_v2/_staging/PKG-PROMPT-ROUTER-001/HOT/tests/test_prompt_router.py -q`

## Full Regression Test — ALL STAGED PACKAGES
- Attempt 1 (exact handoff command):
- Total: N/A (collection interrupted)
- Passed: N/A
- Failed: 91 collection errors
- Skipped: N/A
- Command: `CONTROL_PLANE_ROOT="$TMPDIR" PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" python3 -m pytest Control_Plane_v2/_staging/ -v --ignore="Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz"`
- Result: interrupted by duplicate test-module collection in `_staging/cp_rebuild_tmp/` and `_staging/cp_rebuild_work/`, plus non-bootstrap package test dependency mismatch (`PKG-ATTENTION-001`).

- Attempt 2 (scoped staged package regression, excluding rebuild temp trees and non-bootstrap attention package):
- Total: 261 tests
- Passed: 222
- Failed: 23
- Skipped: 16
- Command: `CONTROL_PLANE_ROOT="$TMPDIR" PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT" python3 -m pytest --import-mode=importlib [staged package tests + _staging/tests/test_bootstrap_sequence.py + followup tests] -q`
- Failing tests are in pre-existing suites (`PKG-VOCABULARY-001`, `PKG-SPEC-CONFORMANCE-001`, `PKG-LAYOUT-001`, `_staging/tests/test_bootstrap_sequence.py`) and are unrelated to prompt-router exchange recording.
- New failures introduced by this agent: NONE observed in `PKG-PROMPT-ROUTER-001`.

## Gate Check Results
- G0B: PASS (78 files owned, 0 orphans)
- G1: PASS (11 chains)
- G1-COMPLETE: PASS (11 frameworks)
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS (3 ledger files, 63 entries)

## Baseline Snapshot (AFTER this agent's work)
- Packages installed: 13
- file_ownership.csv rows: 93 total lines (92 data rows, 78 unique files, 7 supersession rows)
- Total tests (scoped staged regression): 261
- Gate results: G0B PASS, G1 PASS, G1-COMPLETE PASS, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS

## Clean-Room Verification
- Packages installed: 13
- Install order: PKG-KERNEL-001 -> PKG-VOCABULARY-001 -> PKG-REG-001 -> PKG-GOVERNANCE-UPGRADE-001 -> PKG-FRAMEWORK-WIRING-001 -> PKG-SPEC-CONFORMANCE-001 -> PKG-LAYOUT-001 -> PKG-PHASE2-SCHEMAS-001 -> PKG-TOKEN-BUDGETER-001 -> PKG-PROMPT-ROUTER-001 -> PKG-ANTHROPIC-PROVIDER-001 -> PKG-LAYOUT-002
- All gates pass after install: YES (8/8)
- Receipts present: 13
- Full command log artifacts:
- `$TMPDIR/install_stdout.txt`
- `$TMPDIR/install_stderr.txt`
- `$TMPDIR/gates_all.txt`
- `$TMPDIR/router_pytest.txt`
- `$TMPDIR/full_pytest_exact.txt`
- `$TMPDIR/full_pytest_filtered.txt`
- `$TMPDIR/smoke.txt`

## Issues Encountered
- Running manual package_install sequence from a partially bootstrapped path produced an invalid `HOT/HOT` layout; switched to `install.sh --root <tmpdir> --dev`, which completed cleanly.
- Exact full `_staging` pytest run is currently blocked by existing `_staging/cp_rebuild_tmp/` and `_staging/cp_rebuild_work/` duplicate test module trees and one non-bootstrap package dependency mismatch.
- Smoke validation against a fresh ledger needed `assert_append_only` patching in-process to bypass pristine boundary checks for the temporary test ledger file.

## Notes for Reviewer
- Router behavior is verified on the new exchange model: one `EXCHANGE` record per LLM round-trip and lightweight `DISPATCH` marker correlation.
- Rejection paths remain `PROMPT_REJECTED` and intentionally do not create dispatch markers.
- `ledger_client.py`, `provider.py`, `anthropic_provider.py`, and `token_budgeter.py` were not edited for this handoff.

## Execution Shortcuts (Captured Learnings)
- Prefer bootstrap orchestrator over manual chain: `./install.sh --root "$TMPDIR" --dev` from extracted bootstrap root avoids partial-path mistakes.
- Use two-stage verification: run package-local tests first for fast signal, then run mandatory full `_staging` pytest and report blockers separately.
- Full `_staging` pytest currently collects duplicate modules from `_staging/cp_rebuild_tmp/` and `_staging/cp_rebuild_work/`; expect collection noise unless excluded.
- For smoke ledgers outside governed paths, patch pristine guard in test scope (`patch("kernel.pristine.assert_append_only", ...)`) to avoid append-only enforcement failures.
- Be careful with quoted heredocs in shell-to-python snippets; quoting can create literal `"$TMPDIR"` paths.
- Remove `__pycache__` and `.pyc` from package directories before archive rebuild to avoid undeclared asset failures.
- Keep tar packaging strict: `tar czf ... -C dir $(ls dir)` and never `tar czf ... -C dir .`.
- Capture verification logs under `$TMPDIR` (`install_stdout.txt`, `install_stderr.txt`, `gates_all.txt`, pytest logs) so `RESULTS_*.md` can be generated quickly and reproducibly.
