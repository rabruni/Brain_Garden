# Results: HANDOFF-29C — Consolidation Dispatch + Domain-Tag Provider Routing

## Status: PASS

## Summary

Wave 3 (29C) of HANDOFF-29 implements:
1. **Consolidation WO dispatch** from HO2 after gate-crossing signals (out-of-band, after user response)
2. **Domain-tag-based provider routing** in the LLM Gateway (3-step precedence)
3. **tool_ids_used tracking** in HO1 cost dict for HO2 signal extraction
4. **domain_tags passthrough** from HO1 WO constraints to Gateway PromptRequest

All changes are backward-compatible. Empty domain_tag_routes = zero behavioral change. No consolidation runs unless ho3_enabled=True AND gate crosses threshold.

## Files Created

- `PKG-HO1-EXECUTOR-001/HO1/contracts/consolidate.json` (SHA256: sha256:e37f3e081cae95d13ef15f81d5e55754d01f6bcb9ac4ec4276eb9bf77583d990)
- `PKG-HO1-EXECUTOR-001/HO1/prompt_packs/PRM-CONSOLIDATE-001.txt` (SHA256: sha256:31f423a939fec5c9e8a679317558a961c13826772a0d6471081f6f44264bbd19)

## Files Modified

- `PKG-HO1-EXECUTOR-001/HO1/kernel/ho1_executor.py` (SHA256: sha256:24d68de2d4237b5591453a1baad745439c02a699d24471284dadb3e932b6d631)
  - Added `cost.setdefault("tool_ids_used", []).append(tu["tool_id"])` in tool loop
  - Added `domain_tags` passthrough in `_build_prompt_request()` (both PromptRequest and SimpleNamespace paths)
- `PKG-HO1-EXECUTOR-001/HO1/tests/test_ho1_executor.py` (SHA256: sha256:537ec55e7a9e05e924a36ac14f6e46928c5fd4e3d74becfaa9a0271317de8240)
  - Added TestDomainTagsPassthrough class (5 new tests)
- `PKG-HO1-EXECUTOR-001/manifest.json` — version bumped to 1.2.0, added consolidate.json + PRM-CONSOLIDATE-001.txt assets
- `PKG-HO2-SUPERVISOR-001/HO2/kernel/ho2_supervisor.py` (SHA256: sha256:1e133421fc18932508d2b0cab09489fb034c1418f3983caf1c84c62745f02a36)
  - Added consolidation_budget + consolidation_contract_id to HO2Config
  - Added tool signal extraction from wo_chain cost.tool_ids_used
  - Added `run_consolidation()` method with idempotent gate re-check + overlay write
- `PKG-HO2-SUPERVISOR-001/HO2/tests/test_ho2_supervisor.py` (SHA256: sha256:34186c603ba76e67cbd0e562ebb0687a50a621723a22bd681d68ac515ce3c6fc)
  - Added TestConsolidationDispatch class (4 new tests)
- `PKG-HO2-SUPERVISOR-001/manifest.json` — version bumped to 1.1.0, updated hashes
- `PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py` (SHA256: sha256:dd5fcdf3082958614971fb27239d6e6ac463c89351bc73d7333511bdc6126c2d)
  - Added `domain_tag_routes: dict` to RouterConfig
  - Changed provider resolution to 3-step precedence: explicit > domain_tag > default
  - Added `_resolve_domain_tags()` method
  - Updated `from_config_file()` to parse domain_tag_routes
- `PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` (SHA256: sha256:c6917ec8daa7a0d2fefe803b2b6dbb562f9d3259469e81cc7d47ca004d998dbc)
  - Added TestDomainTagRouting class (3 new tests)
- `PKG-LLM-GATEWAY-001/manifest.json` — version bumped to 1.1.0, updated hashes

## Archives Built

- `PKG-HO1-EXECUTOR-001.tar.gz` (SHA256: ac1ef7f6d90cc210dd9a6a25d59f0a70d5069f4e9af85a0b3d7e31d5a4448a9e)
- `PKG-HO2-SUPERVISOR-001.tar.gz` (SHA256: 214ab5236d2f951f462eedcfd6f7d630414b18e96aed81bc8851beb1d8bed56a)
- `PKG-LLM-GATEWAY-001.tar.gz` (SHA256: 9264383fb096e16d262fe6fb20677bf886a4812d89c380ac6ac8121840455873)
- `CP_BOOTSTRAP.tar.gz` (SHA256: sha256:11e900d6dd8dcaccb4a6019a65b121d19a234479e6883ec85b5c7af5be54051c)

## Test Results — Modified Packages

### PKG-HO1-EXECUTOR-001
- Total: 87 tests (82 existing + 5 new)
- Passed: 87
- Failed: 0
- Skipped: 0
- New tests: test_ho1_passes_domain_tags, test_ho1_passes_empty_domain_tags, test_ho1_exposes_tool_ids_used, test_consolidation_prompt_pack_loads, test_consolidation_contract_loads

### PKG-HO2-SUPERVISOR-001
- Total: 82 tests (78 existing + 4 new)
- Passed: 82
- Failed: 0
- Skipped: 0
- New tests: test_consolidation_dispatches_wo, test_consolidation_idempotent, test_consolidation_overlay_has_source_ids, test_tool_signal_from_wo_chain

### PKG-LLM-GATEWAY-001
- Total: 31 tests (28 existing + 3 new)
- Passed: 31
- Failed: 0
- Skipped: 0
- New tests: test_domain_tag_routes_local, test_no_tag_routes_default, test_explicit_provider_overrides_tags

## Full Regression Test — ALL PACKAGES (Clean-Room)
- Total: 649 tests
- Passed: 649
- Failed: 0
- Skipped: 0
- Baseline was: 637 tests (22 packages)
- Delta: +12 new tests
- Command: `PYTHONPATH="$ROOT/HOT/kernel:$ROOT/HOT:$ROOT/HOT/scripts:$ROOT/HOT/admin:$ROOT/HO1/kernel:$ROOT/HO2/kernel" python3 -m pytest $ROOT/HOT/tests/ $ROOT/HO1/tests/ $ROOT/HO2/tests/ --tb=short`
- New failures introduced by this agent: NONE

## Gate Check Results
- G0B: PASS (116 files owned, 0 orphans)
- G1: PASS (20 chains validated, 0 warnings)
- G1-COMPLETE: PASS (20 frameworks checked)
- G2: PASS
- G3: PASS
- G4: PASS
- G5: PASS
- G6: PASS (3 ledger files, 98 entries)
- Overall: PASS (8/8 gates passed)

## Baseline Snapshot (AFTER this agent's work)
- Packages installed: 22 (22 receipts)
- file_ownership.csv rows: 131 (including header)
- Total tests (all packages, clean-room): 649
- Gate results: 8/8 PASS
- CP_BOOTSTRAP.tar.gz SHA256: sha256:11e900d6dd8dcaccb4a6019a65b121d19a234479e6883ec85b5c7af5be54051c

## Clean-Room Verification
- Packages installed: 22
- Install order: PKG-GENESIS-000 + PKG-KERNEL-001 (Layer 0), then 20 auto-discovered: PKG-REG-001, PKG-VOCABULARY-001, PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001, PKG-LAYOUT-001, PKG-LAYOUT-002, PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001, PKG-VERIFY-001, PKG-WORK-ORDER-001, PKG-BOOT-MATERIALIZE-001, PKG-HO2-SUPERVISOR-001, PKG-HO3-MEMORY-001, PKG-LLM-GATEWAY-001, PKG-ANTHROPIC-PROVIDER-001, PKG-HO1-EXECUTOR-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-ADMIN-001
- All gates pass after install: YES
- Clean-room directory: /tmp/cp_29c_root (extracted from CP_BOOTSTRAP.tar.gz to /tmp/cp_29c_cleanroom)

## Issues Encountered
- **test_consolidation_prompt_pack_loads**: Initially failed because the test executor's tmp_path prompt_packs directory did not contain the PRM-CONSOLIDATE-001.txt template. Fixed by writing the template content to the test's prompt_packs directory before rendering.
- No other issues. All 12 new tests pass. Full regression (649 tests) clean. 8/8 gates clean.

## Design Decisions
1. **3-step provider resolution**: `request.provider_id or _resolve_domain_tags(tags) or default_provider` — explicit always wins, then domain tag lookup, then default. Zero behavioral change when domain_tag_routes is empty.
2. **domain_tag_routes supports both string and dict values**: `{"tag": "provider_id"}` or `{"tag": {"provider_id": "..."}}"` for forward compatibility with future route config (model overrides, etc.).
3. **tool_ids_used in cost dict**: Appended per tool call via `cost.setdefault("tool_ids_used", [])`. Does not affect existing tool_calls integer count.
4. **Consolidation idempotency**: `run_consolidation()` re-checks the gate before dispatching. If another turn already consolidated (clearing the gate), this is a no-op.
5. **Overlay provenance**: source_event_ids come directly from the signal accumulator's event_ids list, satisfying HO3Memory.log_overlay's non-empty requirement.
6. **Consolidation WO constraints**: wo_type="consolidate", domain_tags=["consolidation"], budget=4000, turn_limit=1. Single-shot, bounded, deterministic.
