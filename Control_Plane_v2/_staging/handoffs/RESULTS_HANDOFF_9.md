# RESULTS: HANDOFF-9 — PKG-ANTHROPIC-PROVIDER-001 (Anthropic API Provider)

**Status**: PASS 28/28
**Date**: 2026-02-11
**Platform**: Claude (Opus 4.6)

## Summary

Implemented stdlib-only Anthropic Messages API provider (`urllib.request` + `json`) that implements the `LLMProvider` Protocol from `provider.py`. Extends `ProviderResponse` with `content_blocks` tuple for tool use support. No external dependencies. No retries (router's CircuitBreaker handles that).

## Files Created

| File | Package | Purpose |
|------|---------|---------|
| `PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py` | PKG-ANTHROPIC-PROVIDER-001 | Provider implementation (~110 lines) |
| `PKG-ANTHROPIC-PROVIDER-001/HOT/tests/test_anthropic_provider.py` | PKG-ANTHROPIC-PROVIDER-001 | 28 DTT tests (all mocked, no real API calls) |
| `PKG-ANTHROPIC-PROVIDER-001/manifest.json` | PKG-ANTHROPIC-PROVIDER-001 | Package manifest with SHA256 hashes |
| `PKG-ANTHROPIC-PROVIDER-001.tar.gz` | — | Package archive (3 members) |

## Files Modified

| File | Change |
|------|--------|
| `install.sh` line 37 | Added `PKG-ANTHROPIC-PROVIDER-001` to LAYER3_BUILTIN after PKG-PROMPT-ROUTER-001 |
| `CP_BOOTSTRAP.tar.gz` | Rebuilt with 13 packages (was 12) — 16 members total |

## Implementation Details

### AnthropicResponse(ProviderResponse)
- Frozen dataclass extending `ProviderResponse` with `content_blocks: tuple = ()`
- `content` field contains only concatenated text blocks
- `content_blocks` preserves all raw API blocks (text + tool_use) as immutable tuple

### AnthropicProvider
- Reads `ANTHROPIC_API_KEY` from environment on `__init__` (raises `ProviderError(AUTH_ERROR)` if missing)
- `send()` builds Messages API JSON, POSTs via `urllib.request.Request`
- Stop reason mapping: `end_turn` → `stop`, `max_tokens` → `length`, `tool_use` → `tool_use`
- HTTP error mapping: 400 → `INVALID_REQUEST`, 401/403 → `AUTH_ERROR`, 429 → `RATE_LIMITED`, 500/502/503 → `SERVER_ERROR`
- `URLError` → `TIMEOUT` (retryable)
- Structured output via `tools` + `tool_choice` injection
- Default model: `claude-sonnet-4-5-20250929`
- API version: `2023-06-01`

## Test Results

### test_anthropic_provider.py — 28/28 PASS

| # | Test | Category | Result |
|---|------|----------|--------|
| 1 | `test_reads_api_key_from_env` | Init | PASS |
| 2 | `test_missing_key_raises_auth_error` | Init | PASS |
| 3 | `test_default_provider_id` | Init | PASS |
| 4 | `test_custom_provider_id` | Init | PASS |
| 5 | `test_implements_llm_provider_protocol` | Init | PASS |
| 6 | `test_basic_text_response` | Response | PASS |
| 7 | `test_model_id_in_request` | Request | PASS |
| 8 | `test_max_tokens_in_request` | Request | PASS |
| 9 | `test_temperature_in_request` | Request | PASS |
| 10 | `test_stop_reason_end_turn` | Response | PASS |
| 11 | `test_stop_reason_max_tokens` | Response | PASS |
| 12 | `test_stop_reason_tool_use` | Response | PASS |
| 13 | `test_content_blocks_present` | Tool Use | PASS |
| 14 | `test_content_is_text_only` | Tool Use | PASS |
| 15 | `test_mixed_blocks_preserved` | Tool Use | PASS |
| 16 | `test_structured_output_adds_tools` | Structured | PASS |
| 17 | `test_timeout_error` | Error | PASS |
| 18 | `test_429_rate_limited` | Error | PASS |
| 19 | `test_401_auth_error` | Error | PASS |
| 20 | `test_500_server_error` | Error | PASS |
| 21 | `test_400_invalid_request` | Error | PASS |
| 22 | `test_request_id_from_response` | Response | PASS |
| 23 | `test_token_counts` | Response | PASS |
| 24 | `test_response_is_provider_response_subclass` | Response | PASS |
| 25 | `test_timeout_conversion_ms_to_seconds` | Request | PASS |
| 26 | `test_content_blocks_is_tuple` | Tool Use | PASS |
| 27 | `test_default_model_used_when_empty` | Request | PASS |
| 28 | `test_headers_include_auth_and_version` | Request | PASS |

### Regression Tests — ALL PASS

| Suite | Tests | Result |
|-------|-------|--------|
| test_prompt_router.py | 15 | PASS |
| test_followup_3d.py | 13 | PASS |
| test_followup_3e.py | 12 | PASS |
| test_anthropic_provider.py | 28 | PASS |
| **Total** | **68** | **ALL PASS** |

### Clean-Room Verification

- **13 packages installed** across 4 layers (0-3)
- **8/8 gates PASS** (G0B, G1, G1-COMPLETE, G2, G3, G4, G5, G6)
- **HOT/ledger/**: 3 files (governance.jsonl, packages.jsonl, index.jsonl)
- **78 files owned**, 0 orphans (G0B)
- **11 chains** validated (G1)
- **63 ledger entries** (G6)
- **13 receipts** in HOT/installed/
- Provider imports clean in installed environment (without API key — import only)

## CP_BOOTSTRAP.tar.gz

- **Members**: 16 (13 packages in packages/ + 3 docs)
- **Layer 0**: PKG-GENESIS-000, PKG-KERNEL-001
- **Layer 1**: PKG-VOCABULARY-001, PKG-REG-001
- **Layer 2**: PKG-GOVERNANCE-UPGRADE-001, PKG-FRAMEWORK-WIRING-001, PKG-SPEC-CONFORMANCE-001, PKG-LAYOUT-001
- **Layer 3**: PKG-PHASE2-SCHEMAS-001, PKG-TOKEN-BUDGETER-001, PKG-PROMPT-ROUTER-001, PKG-ANTHROPIC-PROVIDER-001, PKG-LAYOUT-002

## Verification Checklist

- [x] 28 tests pass (test_anthropic_provider.py)
- [x] Clean-room install: 13 packages, 8/8 gates PASS
- [x] Provider imports clean in installed environment
- [x] CP_BOOTSTRAP has 16 members (3 docs + 13 packages)
- [x] Existing staged tests pass (no regressions): 40/40
- [x] All manifest SHA256 hashes correct
- [x] RESULTS_HANDOFF_9.md written
