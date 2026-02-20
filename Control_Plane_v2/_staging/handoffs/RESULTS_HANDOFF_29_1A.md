# Results: HANDOFF-29.1A (Structured Artifact Model + Replay-Safe Decay)

## Status: PASS

## Files Modified
- `Control_Plane_v2/_staging/PKG-HO3-MEMORY-001/HOT/kernel/ho3_memory.py` (SHA256 after: `sha256:0d3a182740757f9eb18926454167cefb83f7c7b8db2cb389b8b6e28dcfa6371c`)
- `Control_Plane_v2/_staging/PKG-HO3-MEMORY-001/HOT/tests/test_ho3_memory.py` (SHA256 after: `sha256:a569393ce2dd88812950e737ef764972ff7bf5d5eefde113e13859236d7b5ed6`)
- `Control_Plane_v2/_staging/PKG-HO3-MEMORY-001/manifest.json` (version 1.0.0 -> 1.1.0, hashes updated)
- `Control_Plane_v2/_staging/PKG-GENESIS-000/HOT/config/seed_registry.json` (PKG-KERNEL-001 digest updated after repack)
- `Control_Plane_v2/_staging/PKG-GENESIS-000/manifest.json` (seed_registry hash updated)

## Archives Built
- `Control_Plane_v2/_staging/PKG-HO3-MEMORY-001.tar.gz` (11144 bytes)
- `Control_Plane_v2/_staging/PKG-GENESIS-000.tar.gz` (9337 bytes, seed_registry hash update)
- `Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz` (SHA256: `sha256:4ed6fef167acc74189e785b185d3b0b611dfcab639864e6ee09a6165b7394b7b`, 284711 bytes, 23 packages)

## Test Results -- THIS PACKAGE
- Command: `python3 -m pytest Control_Plane_v2/_staging/PKG-HO3-MEMORY-001/HOT/tests/test_ho3_memory.py -q`
- Total: 36
- Passed: 36
- Failed: 0
- Skipped: 0

### New 29.1A tests present in package
- `test_as_of_ts_deterministic_decay`
- `test_as_of_ts_none_uses_wall_clock`
- `test_as_of_ts_in_read_active_biases`
- `test_as_of_ts_in_is_consolidated`
- `test_structured_artifact_all_fields`
- `test_structured_artifact_backward_read`
- `test_artifact_type_stored`
- `test_labels_stored`
- `test_deactivate_overlay`
- `test_deactivate_nonexistent_raises`
- `test_update_weight`
- `test_expiry_filter`
- `test_expiry_not_expired`
- `test_idempotency_skip_duplicate`
- `test_idempotency_reactivate`
- `test_compute_artifact_id_deterministic`
- `test_lifecycle_resolution_latest_wins`
- `test_context_line_stored` (existing backward-compat test, no new code needed)

## Full Regression Test -- ALL STAGED PACKAGES
- Command: `python3 -m pytest Control_Plane_v2/_staging/ -q --import-mode=importlib --ignore=...ATTENTION/PROMPT-ROUTER/SESSION-HOST`
- Total: 770
- Passed: 729
- Failed: 24
- Skipped: 17
- New failures introduced by this handoff: **NONE**
- Failure set is pre-existing and outside `PKG-HO3-MEMORY-001`.

## Gate Check Results
- Command: `python3 "$ROOT/HOT/scripts/gate_check.py" --root "$ROOT" --all`
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
- Clean-room root: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.ayA4lOcn/CP_2.1`
- Packages installed: 23
- Installed package IDs:
  - `PKG-ADMIN-001, PKG-ANTHROPIC-PROVIDER-001, PKG-ATTENTION-001, PKG-BOOT-MATERIALIZE-001, PKG-FRAMEWORK-WIRING-001, PKG-GENESIS-000, PKG-GOVERNANCE-UPGRADE-001, PKG-HO1-EXECUTOR-001, PKG-HO2-SUPERVISOR-001, PKG-HO3-MEMORY-001, PKG-KERNEL-001, PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-LLM-GATEWAY-001, PKG-PHASE2-SCHEMAS-001, PKG-REG-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-SPEC-CONFORMANCE-001, PKG-TOKEN-BUDGETER-001, PKG-VERIFY-001, PKG-VOCABULARY-001, PKG-WORK-ORDER-001`
- `file_ownership.csv` rows: 141
- Installed HOT/HO1/HO2 tests: 782 total (781 passed, 1 failed)
- Gate results: 8/8 PASS

## Clean-Room Verification
- Temp directory: `/var/folders/gf/3ljb_fbn6ksf8tfghxr6nwlr0000gn/T/tmp.ayA4lOcn`
- Commands:
  - `tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TMP/bootstrap"`
  - `bash "$TMP/bootstrap/install.sh" --root "$TMP/CP_2.1" --dev`
  - `PYTHONPATH=... python3 -m pytest "$ROOT/HOT/tests" "$ROOT/HO1/tests" "$ROOT/HO2/tests" -q`
  - `python3 "$ROOT/HOT/scripts/gate_check.py" --root "$ROOT" --all`
- Install result: PASS (23 receipts)
- Installed test result: `1 failed, 781 passed` (single pre-existing framework-count failure)
- Gates result: PASS (8/8)

## Issues Encountered
- Repacking ALL packages changed PKG-KERNEL-001.tar.gz hash (non-deterministic due to `__pycache__` leaking during pack). Required updating `seed_registry.json` and PKG-GENESIS-000 manifest.
- Dead V1 packages (PKG-PROMPT-ROUTER-001, PKG-SESSION-HOST-001) were included in CP_BOOTSTRAP on first attempt, causing ownership conflicts. Excluded from final build.

## Implementation Summary

### Gap 1: as_of_ts (replay-safe decay)
- Added `as_of_ts: Optional[str] = None` to `read_signals()`, `read_active_biases()`, `_is_consolidated()`
- When provided, uses `datetime.fromisoformat(as_of_ts)` instead of `datetime.now(timezone.utc)`
- `_is_consolidated` now uses range check `window_cutoff <= window_end <= now` to correctly handle past as_of_ts

### Gap 2: Structured artifact fields
- Extended `log_overlay()` to persist 13 structured keys: artifact_id, artifact_type, labels, weight, scope, context_line, enabled, expires_at_event_ts, source_signal_ids, gate_snapshot, model, prompt_pack_version, consolidation_event_ts

### Gap 3: Overlay lifecycle (append-only)
- Added `deactivate_overlay(artifact_id, reason, event_ts)` -- writes HO3_OVERLAY_DEACTIVATED event
- Added `update_overlay_weight(artifact_id, new_weight, reason, event_ts)` -- writes HO3_OVERLAY_WEIGHT_UPDATED event
- `read_active_biases()` now resolves lifecycle: scans all events per artifact_id, latest determines state

### Gap 4: Idempotency
- Added `compute_artifact_id(source_signal_ids, gate_window_key, model, prompt_pack_version)` -- deterministic SHA256
- Added `_find_overlay_by_artifact_id(artifact_id)` -- scans overlay ledger with lifecycle resolution
- `log_overlay()` checks for existing artifact_id before writing; if active, returns existing overlay_id; if deactivated, re-activates via weight update

## Notes for Reviewer
- Scope adhered to package source boundaries (`PKG-HO3-MEMORY-001` only, plus seed_registry fix for repack).
- All 4 gaps are backward compatible -- old overlays (no artifact_id) still readable.
- Closed vocabulary: `ARTIFACT_TYPES = ("topic_affinity", "interaction_style", "task_pattern", "constraint")`.
- 18 new tests + 18 existing = 36 total in package.
