# Results: HANDOFF-29P Admin Reliability Patch

## Status: PASS (with external-provider limitation in live E2E)

## Summary
1. Implemented bounded gateway retry/backoff for retryable provider failures and wired timeout/retry from ADMIN config into `RouterConfig`.
2. Added grounded-response guardrails in synthesize prompt + quality gate rejection for ungrounded source-visibility claims.
3. Added two admin tools (`show_runtime_config`, `list_tuning_files`) and exposed them in `admin_config.json` so they are in `tools_allowed`.
4. Updated manifests (sha256 format), rebuilt changed package archives with `packages.py:pack()`, and rebuilt `CP_BOOTSTRAP.tar.gz` with `pack()`.
5. Clean-room install, clean-room full regression (HOT/HO1/HO2), and gate checks all passed.

## Files Created
- `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_quality_gate.py` (SHA256: `sha256:f38c17469c3dadc60eaf6a7e43ead1685d444869065175da0f2da19b33cade50`)
- `Control_Plane_v2/_staging/handoffs/RESULTS_HANDOFF_29P.md`

## Files Modified
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` (SHA256: `sha256:e01105c163d8c5556bcee31e24977fe1f2fa44d8892b29103ae9cf2834eb6c33`)
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` (SHA256: `sha256:75f8ccda460eb22ceecf42d9f3dccc5f3d0a71b783abd99d2f9ab5eda7803e5b`)
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-SYNTHESIZE-001.txt` (SHA256: `sha256:55d519affd2988fcb3353f0989d95b56aba13c0baaae6f0ac1c547e0ef51363b`)
- `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/quality_gate.py` (SHA256: `sha256:81da27fb9da4d6d386bd7fb0be5ee200c92a232ee99a0d7f3ea22faa97533195`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py` (SHA256: `sha256:90b9408c8dc89f90a0c8717e65a8bebbac0ed51ada801a4744a98954fd665f14`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/config/admin_config.json` (SHA256: `sha256:9502ad29168052d3f28f94009ecdda7a296c08c40ee969ef1a1527132079277a`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` (SHA256: `sha256:a07384219c882d8643291c1798fd192e9f5775bc3bd46f558aa9b16f51f5d946`)
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/manifest.json` (SHA256: `sha256:cb9c56496f47f2499e8d0473c732f7f1ff04d064ba08b6b9e4cd91abf9f7cf47`)
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/manifest.json` (SHA256: `sha256:aacc1fa701068051f192aac067220dfe23828d34d6135c714f3f1ee2f507f006`)
- `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/manifest.json` (SHA256: `sha256:3d4ac4eb1e0e88b76d8762594a9b28af50696135b0e035200e44c94a6b3f404e`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/manifest.json` (SHA256: `sha256:c719a46db5ced0618025d6376ec73b9a1a712a7cfab8e79e3768b66adab2a792`)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256: `sha256:4040c2bb1e52ba933cce4b556bf8ec327857a1445e8e1ca9bffb003770b78528`)

## Archives Built
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001.tar.gz` (SHA256: `sha256:39a66cb7d9683113e38d41c4ca1a54ea7d16ce423238dae447b8b3c345e64b31`)
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001.tar.gz` (SHA256: `sha256:7129e9f5b5f16b159d64f8a1423600c708df73ebe44a088e864093b75738c372`)
- `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001.tar.gz` (SHA256: `sha256:f164ee4d5d2fbff46cc7ae8bff9e4552c64756648479e15cdc41b91f755789f8`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001.tar.gz` (SHA256: `sha256:e8f0650c15d33dad6a0a92aa1868b86f297ad913f012387dd15854b832d382c1`)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256: `sha256:4040c2bb1e52ba933cce4b556bf8ec327857a1445e8e1ca9bffb003770b78528`)

## Test Results — THIS HANDOFF
- DTT red-state checks (new tests before implementation):
  - Gateway retry tests failed as expected pre-implementation.
  - Quality-gate grounding test failed as expected pre-implementation.
  - Admin runtime/tuning tool tests failed as expected pre-implementation.
- Post-implementation package-local regression:
  - Command:
    - `pytest -q Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_quality_gate.py Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py`
  - Result: **301 passed, 0 failed**

## Full Regression — ALL STAGED PACKAGES
- Broad `_staging` run (supplemental):
  - Command:
    - `python3 -m pytest Control_Plane_v2/_staging -q --ignore=Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz --ignore=Control_Plane_v2/_staging/PKG-ATTENTION-001/HOT/tests/test_attention_service.py --import-mode=importlib`
  - Result: **703 passed, 26 failed, 17 skipped**
  - Failures are pre-existing in unrelated packages/paths (`PKG-LAYOUT-001`, `PKG-FRAMEWORK-WIRING-001`, `PKG-SPEC-CONFORMANCE-001`, `PKG-VOCABULARY-001`, `tests/test_bootstrap_sequence.py`, and one import-mode-specific backward-compat assertion). None were introduced in modified 29P package-local tests.

## Clean-Room Verification
- Clean-room root:
  - `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.QS1qEt9R`
- Install command:
  - `LC_ALL=C tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$BOOT"`
  - `bash install.sh --root "$ROOT" --dev`
- Installed system full regression command:
  - `PYTHONPATH="$ROOT/HOT/kernel:$ROOT/HOT:$ROOT/HOT/scripts:$ROOT/HOT/admin:$ROOT/HO1/kernel:$ROOT/HO2/kernel" python3 -m pytest "$ROOT/HOT/tests" "$ROOT/HO1/tests" "$ROOT/HO2/tests" -q`
- Gate command:
  - `python3 "$ROOT/HOT/scripts/gate_check.py" --root "$ROOT" --all`
- Results:
  - Install: **PASS (rc=0)**
  - Full tests (installed HOT+HO1+HO2): **660 passed, 0 failed**
  - Gates: **Overall PASS (8/8)**

## Gate Check Results (Clean-Room)
- G0B: PASS
- G1: PASS
- G1-COMPLETE: PASS
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS
- Overall: **PASS (8/8 gates passed)**

## Baseline Snapshot (AFTER this handoff)
- Baseline root: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.QS1qEt9R/CP_2.1`
- Packages installed: **22**
- Installed package IDs:
  - `PKG-ADMIN-001, PKG-ANTHROPIC-PROVIDER-001, PKG-BOOT-MATERIALIZE-001, PKG-FRAMEWORK-WIRING-001, PKG-GENESIS-000, PKG-GOVERNANCE-UPGRADE-001, PKG-HO1-EXECUTOR-001, PKG-HO2-SUPERVISOR-001, PKG-HO3-MEMORY-001, PKG-KERNEL-001, PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-LLM-GATEWAY-001, PKG-PHASE2-SCHEMAS-001, PKG-REG-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-SPEC-CONFORMANCE-001, PKG-TOKEN-BUDGETER-001, PKG-VERIFY-001, PKG-VOCABULARY-001, PKG-WORK-ORDER-001`
- `file_ownership.csv` rows: **131**
- Unique files: **117**
- Supersession rows: **14**
- Total tests (clean-room HOT+HO1+HO2): **660 passed**
- Gate results: **8/8 PASS**

## E2E Admin-Shell Verification (Real Provider)
- Command sequence executed in clean-room ADMIN shell:
  1. `show runtime config`
  2. `list tuning files`
  3. `can you prove this from ledger/code right now?`
  4. `/exit`
- Result:
  - Session started and processed turns, but provider calls hit repeated `TIMEOUT: Connection error` during classify, then circuit opened.
  - Shell responses became `[Error: CIRCUIT_OPEN: Circuit breaker is open]`.
- What this validated:
  - New retry trail is present in governance ledger (`retry_attempt`, `retryable`, `will_retry`, `max_retries`) across timeout attempts.
  - Circuit-breaker behavior remained bounded/fail-closed.
- What could not be fully validated live due external connectivity:
  - Final natural-language grounded response path and successful tool-mediated runtime/tuning responses in shell loop.
  - Covered by package tests + clean-room regression.

## Issues Encountered
1. `install.sh` in bootstrap extracts non-executable due deterministic pack mode normalization; running via `bash install.sh` is required in clean-room.
2. Repacked archives initially included `__pycache__` after test runs; removed `__pycache__`/`.DS_Store`, then rebuilt archives and bootstrap.
3. Live provider connectivity during E2E produced repeated timeout + open circuit; this is environmental, not a regression in 29P code paths.

## Notes for Reviewer
- Scope was kept to the 29P files list plus required manifest/archive/result updates.
- `query_ledger` was left intact; additive tools (`show_runtime_config`, `list_tuning_files`) are now registered and configured.
- Gateway retry policy is bounded and explicit for retryable classes only, with per-attempt ledger metadata.
