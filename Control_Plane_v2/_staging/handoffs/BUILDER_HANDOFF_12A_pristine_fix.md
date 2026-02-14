# BUILDER HANDOFF 12A — Pristine Bypass Ordering Fix

## 1. Identity

| Field | Value |
|-------|-------|
| Handoff ID | HANDOFF-12A |
| Package(s) | PKG-ADMIN-001 (modify) |
| Title | Fix pristine bypass ordering so boot_materialize runs under dev-mode bypass |
| Layer | 3 |
| Dependencies | HANDOFF-12 (completed) |
| Scope | Single file fix + test + archive rebuild |

## 2. Problem Statement

In `PKG-ADMIN-001/HOT/admin/main.py`, the `run_cli()` function calls `boot_materialize(root)` at line 195, but the dev-mode pristine bypass (`patch("kernel.pristine.assert_append_only")`) doesn't start until line 203. This means boot_materialize runs WITHOUT the pristine bypass, causing a `WriteViolation` crash when it tries to write GENESIS entries to HO2 and HO1 governance ledgers.

The HO2/HO1 ledger files are newly created by boot_materialize — they don't exist in `file_ownership.csv` yet, so pristine.py classifies them as DERIVED and rejects the write.

**Reproduction:**
```bash
# After clean-room install of CP_BOOTSTRAP.tar.gz:
python3 cp_root/HOT/admin/main.py --root cp_root --dev <<< "exit"
# CRASHES with: kernel.pristine.WriteViolation on HO2/ledger/governance.jsonl
```

## 3. Specification

### Fix: Reorder pristine bypass in `run_cli()`

**Current order (WRONG):**
```python
def run_cli(...):
    ...
    from boot_materialize import boot_materialize
    mat_result = boot_materialize(root)          # <- Line 195: NO pristine bypass yet
    ...
    host = build_session_host(...)
    pristine_patch = None
    if dev_mode:
        pristine_patch = patch(...)              # <- Line 203: too late
        pristine_patch.start()
    session_id = host.start_session()
```

**Required order (CORRECT):**
```python
def run_cli(...):
    ...
    from boot_materialize import boot_materialize
    pristine_patch = None
    if dev_mode:
        pristine_patch = patch("kernel.pristine.assert_append_only", return_value=None)
        pristine_patch.start()

    mat_result = boot_materialize(root)          # <- NOW runs under bypass
    if mat_result != 0:
        output_fn(f"WARNING: Boot materialization returned {mat_result} (non-fatal)")

    host = build_session_host(...)
    session_id = host.start_session()
```

The `pristine_patch.stop()` stays in the `finally` block — unchanged.

### Constraints

1. **Only modify `run_cli()` in main.py** — do not change boot_materialize.py, ledger_client.py, or pristine.py.
2. **The `finally` block must still call `pristine_patch.stop()`** — no resource leaks.
3. **Non-dev mode behavior is unchanged** — boot_materialize may fail with WriteViolation in non-dev mode (that's correct — production needs proper file_ownership registration, which is a future task).
4. **Do not add new imports** — `patch` is already imported.

## 4. Files to Modify

| File | Action | What Changes |
|------|--------|-------------|
| `PKG-ADMIN-001/HOT/admin/main.py` | MODIFY | Reorder pristine_patch to start before boot_materialize in run_cli() |

## 5. Test Plan

**3 tests total. Zero API calls, zero ANTHROPIC_API_KEY required.**

### Test 1: `test_boot_materialize_runs_under_pristine_bypass`
- Create a tmp_path plane root with layout.json
- Call `run_cli()` with dev_mode=True, mock input that sends "exit"
- Assert return code 0 (no WriteViolation crash)
- Assert HO2/ledger/governance.jsonl exists

### Test 2: `test_boot_materialize_called_before_session_host`
- Patch both `boot_materialize` and `build_session_host` to track call order
- Call `run_cli()` with dev_mode=True
- Assert boot_materialize was called before build_session_host

### Test 3: `test_pristine_patch_stopped_on_exit`
- Call `run_cli()` with dev_mode=True, input "exit"
- After return, assert that `kernel.pristine.assert_append_only` is no longer patched (original function restored)

## 6. Archive Rebuild

After modifying main.py:
1. Update SHA256 in `PKG-ADMIN-001/manifest.json` for `HOT/admin/main.py`
2. Rebuild `PKG-ADMIN-001.tar.gz`
3. Rebuild `CP_BOOTSTRAP.tar.gz` with updated PKG-ADMIN-001.tar.gz
4. **No cascade needed** — PKG-ADMIN-001 is Layer 3, not referenced by PKG-GENESIS-000's seed_registry

## 7. Verification

1. Run the 3 new tests — all pass
2. Run existing PKG-ADMIN-001 tests (`test_admin.py`) — all still pass
3. Clean-room install of CP_BOOTSTRAP.tar.gz → 17 packages, 8/8 gates PASS
4. Run: `python3 cp_root/HOT/admin/main.py --root cp_root --dev <<< "exit"` → exits cleanly, no WriteViolation
5. Verify HO2 and HO1 directories exist with tier.json and governance.jsonl after ADMIN boot

## 8. Non-Goals

- Do NOT fix production mode (non-dev) WriteViolation — that requires file_ownership.csv registration of HO2/HO1 paths, which is a separate task.
- Do NOT modify boot_materialize.py, pristine.py, or ledger_client.py.
- Do NOT change any other package.

## 9. Results File

Write results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_12A.md` following the BUILDER_HANDOFF_STANDARD.md format.

## 10. Acceptance Criteria

- [ ] `run_cli()` with `--dev` no longer crashes with WriteViolation
- [ ] 3 new tests pass
- [ ] Existing `test_admin.py` tests still pass
- [ ] Clean-room install: 17 packages, 8/8 gates PASS
- [ ] ADMIN dev-mode boot: creates HO2/HO1 dirs + GENESIS chains + exits cleanly
