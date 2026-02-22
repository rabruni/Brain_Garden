# Results: HANDOFF-26A Pristine Memory + Budget Modes

## Status: PASS (with pre-existing staged-suite failures outside handoff scope)

## Summary
1. Implemented all HANDOFF-26A runtime/config changes across the 4 scoped packages.
2. Added tests first (DTT), then implemented code, then re-ran tests.
3. Rebuilt 4 package archives and `CP_BOOTSTRAP.tar.gz` using `packages.py:pack()`.
4. Clean-room install and 8/8 governance gates passed.

## Files Modified
- `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` (SHA256: `sha256:f714038b22933935eedbe7ec25296524f8de592437c4d5ee32de3802701426a8`)
- `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` (SHA256: `sha256:d2269e171c3a8a556555687cc242762e446a72df03d12c3c7c3c7642107bb53c`)
- `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/manifest.json` (SHA256: `sha256:243af8634fa3d54aa54422976ad221d84519625d5af48ad97f3a2ebe98da768f`)
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` (SHA256: `sha256:9b8051d71ca43b92f98c317ed23d9f9e38fbacc9b45b63369ae95b03d7204ce7`)
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` (SHA256: `sha256:e456274d7e116e23be7f216a527c63c84a43bb0c9a78fe8a067e881d9e65c46a`)
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/manifest.json` (SHA256: `sha256:93946ce15bdbd46fc686d1871ddc89265a7be1bb2ba8a4478580af64bf23ce3c`)
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` (SHA256: `sha256:8dfd88f6d48c2729d552872275f4e151495bd9ef410ad23646481f4198104256`)
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` (SHA256: `sha256:d5a49fc84510279e239cd4f7589c216b8e177566760d2b04d196a781cf19bff1`)
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/manifest.json` (SHA256: `sha256:2620904dc921c07972fd080580cc95ef856cdd038c2aadc32090312592907a74`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/admin/main.py` (SHA256: `sha256:eb5aab03a95065ec92326c7124131adbf73ba36824346063d94af766c9be83a2`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/config/admin_config.json` (SHA256: `sha256:aac396bec16ecbb4836cafd56c7ba7ab8ad52cc49ad9bdf612fcedb0e03a161a`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py` (SHA256: `sha256:129e3374eed6d9a1e6b280a1d010f4138491f0bf337904006e21f57b5f36f22f`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001/manifest.json` (SHA256: `sha256:813675ff3d3d6a42f66b412e2de8d7cd73ca85b275b0cb5f038db3d288a32280`)

## Archives Built
- `Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001.tar.gz` (SHA256: `sha256:79e4cbe7ecbd7c3f7754abb3bd3c88fe741cc6dbb3d66500a37a0aafb37f0597`)
- `Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001.tar.gz` (SHA256: `sha256:129cbf3b32702738ca28c12cbdcc05fdca7425670eee2e61b1a1d719d856e417`)
- `Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001.tar.gz` (SHA256: `sha256:abfad4008a16e0473ecfe8c109dde2c58e71f857adc7e99ae163233202e4eb7b`)
- `Control_Plane_v2/_staging/PKG-ADMIN-001.tar.gz` (SHA256: `sha256:2c3bd3b57ef10468b79a0fad6514afa54cf6aaa0f7a37e4d12afe1cfee84334d`)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256: `sha256:6c05e9c149371c244f1076f4c4a4fd6abd2f1193697fd4fbaf184a1804d040eb`)

## Test Results — THIS HANDOFF (Scoped Packages)
- Targeted handoff test run:
  - Command: `python3 -m pytest Control_Plane_v2/_staging/PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py Control_Plane_v2/_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py Control_Plane_v2/_staging/PKG-ADMIN-001/HOT/tests/test_admin.py -q`
  - Result: **213 passed, 0 failed**

- Package-local runs:
  - `PKG-HO2-SUPERVISOR-001`: 68 passed
  - `PKG-HO1-EXECUTOR-001`: 82 passed
  - `PKG-LLM-GATEWAY-001`: 28 passed
  - `PKG-ADMIN-001`: 35 passed

## Full Regression — ALL STAGED PACKAGES
- Command 1 (strict all staged):
  - `python3 -m pytest Control_Plane_v2/_staging -q`
  - Result: **2 collection errors** (pre-existing):
    - `PKG-ATTENTION-001` import path issue (`kernel.attention_stages`)
    - `PKG-LAYOUT-002` import-file mismatch with `PKG-LAYOUT-001`

- Command 2 (excluding those known collection blockers):
  - `python3 -m pytest Control_Plane_v2/_staging -q --ignore=Control_Plane_v2/_staging/PKG-ATTENTION-001 --ignore=Control_Plane_v2/_staging/PKG-LAYOUT-002`
  - Result: **553 passed, 26 failed, 17 skipped**
  - Failures are outside HANDOFF-26A package scope (framework/layout/spec/vocabulary/bootstrap baseline issues).

- New failures introduced by this handoff: **NONE observed in scoped packages**.

## Clean-Room Verification
- Extract/bootstrap/install command sequence:
  1. `TMPDIR=$(mktemp -d)`
  2. `tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"`
  3. `cd "$TMPDIR" && bash install.sh --root "$TMPDIR" --dev`
- Install result: `INSTALL_RC=0`
- Clean-room test command:
  - `PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" python3 -m pytest "$TMPDIR/HOT/tests" "$TMPDIR/HO1/tests" "$TMPDIR/HO2/tests" -q`
  - Result: **553 passed, 0 failed**
- Gates command:
  - `PYTHONPATH="$TMPDIR/HOT/kernel:$TMPDIR/HOT:$TMPDIR/HOT/scripts:$TMPDIR/HOT/admin:$TMPDIR/HO1/kernel:$TMPDIR/HO2/kernel" python3 "$TMPDIR/HOT/scripts/gate_check.py" --all --enforce --root "$TMPDIR"`
  - Result: **PASS (8/8 gates)**
- Verified clean-room root:
  - `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.CvbxShwK`

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

## Baseline Snapshot (AFTER this agent's work)
- Baseline root: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.CvbxShwK`
- Packages installed: **21**
- Installed package IDs:
  - `PKG-ADMIN-001, PKG-ANTHROPIC-PROVIDER-001, PKG-BOOT-MATERIALIZE-001, PKG-FRAMEWORK-WIRING-001, PKG-GENESIS-000, PKG-GOVERNANCE-UPGRADE-001, PKG-HO1-EXECUTOR-001, PKG-HO2-SUPERVISOR-001, PKG-KERNEL-001, PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-LLM-GATEWAY-001, PKG-PHASE2-SCHEMAS-001, PKG-REG-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-SPEC-CONFORMANCE-001, PKG-TOKEN-BUDGETER-001, PKG-VERIFY-001, PKG-VOCABULARY-001, PKG-WORK-ORDER-001`
- `file_ownership.csv` rows: **126**
- Unique files: **112**
- Supersession rows: **14**
- Total tests (clean-room HOT+HO1+HO2): **553 passed**
- Gate results: **8/8 PASS**

## Issues Encountered
1. `.DS_Store` files in package roots caused G0A failure during clean-room install.
   - Resolution: rebuilt the 4 package archives from sanitized temporary copies (excluding `.DS_Store` and `__pycache__`) using `packages.py:pack()`.
2. Full staged suite contains pre-existing non-handoff failures and collection blockers.
   - Resolution: reported strict run output and a second run excluding known blockers to provide complete regression visibility.

## Notes for Reviewer
- DTT order was followed: tests added first, then implementation.
- Budget mode is now consistently wired via `admin_config.json` through HO2, HO1, and Gateway.
- TURN_RECORDED now persists on degradation exception path.
- Tool-call logging in HO1 now includes full arguments/results + byte sizes + tool error metadata for both tool-loop and `tool_call` WO paths.
- `query_ledger` now returns full reason and metadata values (not just metadata keys).
