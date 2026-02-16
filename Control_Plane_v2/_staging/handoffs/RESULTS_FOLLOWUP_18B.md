# Results: FOLLOWUP-18B — Budget Reconciliation Fix

## Status: PASS

## Files Modified

| File | SHA256 Before | SHA256 After |
|------|---------------|--------------|
| `PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` | `sha256:8fbfdc7323b5ccc0e563ef887eb157240b80407bc7ec5be45bdbc118ba6f4ef2` | `sha256:e44282b784faa34092e8cb49092f0e47d98e8d35abc8f76a98442133b43a7eea` |
| `PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` | `sha256:7970410faf26335e014e4e1a4d95a753988b552fc4023cd2bfbcd1b3845206fe` | `sha256:89a944c0274c8fc42ffb31af8d898f07958caf9ad7a7ab6be3a196a4f766b277` |
| `PKG-HO1-EXECUTOR-001/manifest.json` | (hashes updated for both assets above) | (updated) |

## Changes Summary

### Change 1 — Cap max_tokens (root cause fix)
In `_build_prompt_request()`, both the PromptRequest path and SimpleNamespace fallback path now use:
```python
max_tokens=min(boundary.get("max_tokens", 4096), token_budget)
```
where `token_budget = wo.get("constraints", {}).get("token_budget", 100000)`.

This ensures the Gateway never sees a `max_tokens` value exceeding the allocated budget.

### Change 2 — Check response.outcome (defense-in-depth)
After `gateway.route(request)` returns, the executor now checks `response.outcome`. If outcome is not `SUCCESS` or `RouteOutcome.SUCCESS`, the WO is explicitly failed with the error code and message from the response. This prevents silently wrapping empty content as "completed".

## Archives Built
- `PKG-HO1-EXECUTOR-001.tar.gz` (SHA256: `sha256:333a7cc100ac2c672ddb749b3a65dbe3d21006120b9d9fbce5dd3d67ae6833d6`)
- `CP_BOOTSTRAP.tar.gz` (SHA256: `sha256:0ba5d5000ef6e3614640475cb409cb4b2eb09c7677f4e79a8306b4b039f97437`)

## Test Results — THIS PACKAGE
- Total: 40 tests
- Passed: 40
- Failed: 0
- Skipped: 0
- Command: `python3 -m pytest Control_Plane_v2/_staging/PKG-HO1-EXECUTOR-001/ -v`

### New Tests (5)
| Test | Validates |
|------|-----------|
| `test_max_tokens_capped_to_budget` | max_tokens = min(boundary, budget) when budget < boundary |
| `test_max_tokens_uses_contract_when_budget_larger` | max_tokens = contract value when budget > boundary |
| `test_gateway_rejection_fails_wo` | outcome=REJECTED triggers _fail_wo with error code |
| `test_gateway_error_fails_wo` | outcome=ERROR triggers _fail_wo with error code |
| `test_gateway_success_completes_wo` | outcome=SUCCESS proceeds normally to completion |

## Full Regression Test — ALL STAGED PACKAGES
- Total: 222 tests
- Passed: 222
- Failed: 0
- Skipped: 0
- Command: `python3 -m pytest PKG-WORK-ORDER-001 PKG-HO1-EXECUTOR-001 PKG-HO2-SUPERVISOR-001 PKG-LLM-GATEWAY-001 PKG-SESSION-HOST-V2-001 PKG-SHELL-001 PKG-ADMIN-001 PKG-ANTHROPIC-PROVIDER-001 PKG-TOKEN-BUDGETER-001 -v`
- New failures introduced by this agent: NONE

## Gate Check Results
- G0B: PASS (107 files, 0 orphans)
- G1: PASS (18 chains validated, 0 warnings)
- G1-COMPLETE: PASS (18 frameworks checked)
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS (3 ledger files, 90 entries)

## Clean-Room Verification
- Packages installed: 20 (20 receipts)
- Install order: auto-resolved via `resolve_install_order.py`
- All gates pass: YES (8/8 PASS)
- Bootstrap extracted to temp dir, `install.sh --root --dev` executed cleanly

## Baseline Snapshot (AFTER this agent's work)
- Packages installed: 20
- Total tests (all staged): 222
- Gate results: G0B PASS, G1 PASS, G1-COMPLETE PASS, G2 PASS, G3 PASS, G4 PASS, G5 PASS, G6 PASS (8/8)

## Issues Encountered
- None. Both changes were surgical and all existing tests continued to pass.

## Notes for Reviewer
- The spec mentioned 21 packages; the actual count is 20 after CLEANUP-2 removed 4 V1 packages (from 24 → 20).
- E2E smoke test requires ANTHROPIC_API_KEY which is not available in this environment. The fix is verified via unit tests that confirm: (a) max_tokens is capped to min(boundary, budget), and (b) gateway rejections fail the WO with proper error codes.
- The `str(outcome)` comparison handles both string and enum values safely without importing Gateway internals.
