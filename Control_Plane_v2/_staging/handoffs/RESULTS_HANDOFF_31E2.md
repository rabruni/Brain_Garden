# RESULTS — HANDOFF-31E-2: Projection Budget Config (PKG-ADMIN-001)

**Date**: 2026-02-19
**Builder**: Claude Opus 4.6
**Package**: PKG-ADMIN-001 v1.1.0

## Summary

Added `projection_budget` and `projection_mode` configuration to admin_config.json and wired them through main.py's `build_session_host_v2()` to HO2Config.

## Changes Made

### 1. `HOT/config/admin_config.json`
- Added `"projection_budget": 10000` to `budget` section
- Added `"projection"` section with `mode: "shadow"`, `intent_header_budget: 500`, `wo_status_budget: 2000`

### 2. `HOT/schemas/admin_config.schema.json`
- Expanded `budget` schema with full property definitions (10 keys)
- Added `projection` schema section with mode enum (shadow/active/off) + budget fields

### 3. `HOT/admin/main.py`
- Added `projection_cfg = cfg_dict.get("projection", {})` before HO2Config construction
- Wired `projection_budget=budget_cfg.get("projection_budget", 10000)` to HO2Config
- Wired `projection_mode=projection_cfg.get("mode", "shadow")` to HO2Config

### 4. `HOT/tests/test_admin.py`
- Added `ADMIN_CONFIG_PATH` constant
- Added `TestProjectionConfig` class with 6 tests:
  - `test_projection_budget_in_config` — verifies config value
  - `test_projection_mode_in_config` — verifies config value
  - `test_projection_budget_wired_to_ho2config` — e2e wiring with override
  - `test_projection_mode_wired_to_ho2config` — e2e wiring with override
  - `test_projection_config_optional` — defaults when sections absent
  - `test_budget_section_complete` — all 10 budget keys present

## DTT Cycle

- **RED**: 5 of 6 tests failed (test_projection_config_optional passed with defaults)
- **GREEN**: All 6 pass after implementation
- **REFACTOR**: No refactoring needed

## Governance Cycle

| Step | Result |
|------|--------|
| SHA256 hashes computed | 4 files updated in manifest.json |
| Pack PKG-ADMIN-001 | CLEAN (no __pycache__, no .DS_Store) |
| CP_BOOTSTRAP rebuilt | 21 packages, sha256:6cd18f07... |
| Clean-room install | 21 packages installed, 8/8 gates |
| Installed root regression | 790 passed, 3 failed (pre-existing HO3 wiring) |
| Staging projection tests | 6/6 passed |

## Pre-existing Failures (NOT regressions)

3 failures in `TestHO3Wiring` — PKG-HO3-MEMORY-001 not in active 21-package bootstrap. These exist in every run since H-29.

## Test Counts

| Context | Passed | Failed | Notes |
|---------|--------|--------|-------|
| Installed root | 790 | 3 | Pre-existing HO3 wiring |
| Staging (projection only) | 6 | 0 | All new tests pass |

## Manifest Hashes (Updated)

| File | SHA256 |
|------|--------|
| HOT/admin/main.py | sha256:6a281afb1fe235c0c8660fbc261b34ee6f715ead1f649d7a538f506503221d8d |
| HOT/config/admin_config.json | sha256:9c89c714e4d196ea4075fb8c2429c46d04e3e1888dd4175184430ce67d686136 |
| HOT/schemas/admin_config.schema.json | sha256:b7d3b0d39893c14bbadf763ca020dcec9da63a751bc91f27f5527d72abfcbc0a |
| HOT/tests/test_admin.py | sha256:784d463aeac2b83ac21785d848546366f56e08f31e0e8c5a209449884ae14d5c |

## Verdict

**PASS** — All acceptance criteria met. Projection budget and mode flow from admin_config.json through build_session_host_v2() to HO2Config. Defaults are safe (10000 tokens, "shadow" mode). Config is optional — missing sections use defaults.
