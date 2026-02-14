# RESULTS: FOLLOWUP-9A — Rewrite Provider urllib to Anthropic SDK

**Date**: 2026-02-11
**Platform**: Claude (Opus 4.6)
**Status**: PASS (71/71 tests)

## Summary

Rewrote `PKG-ANTHROPIC-PROVIDER-001` from raw `urllib.request` to the official `anthropic` Python SDK (v0.76.0). Layer 3 application package — kernel (Layers 0-2) remains stdlib-only. The `send()` signature and `AnthropicResponse` shape are unchanged; only the transport engine swapped.

## Changes

| File | Action | Description |
|------|--------|-------------|
| `HOT/kernel/anthropic_provider.py` | REWRITE | urllib.request -> anthropic.Anthropic SDK client |
| `HOT/tests/test_anthropic_provider.py` | REWRITE | urllib mocks -> SDK type mocks (Message, TextBlock, ToolUseBlock) |
| `manifest.json` | EDIT | New SHA256 hashes, added `external_deps`, bumped version to 1.1.0 |
| `PKG-ANTHROPIC-PROVIDER-001.tar.gz` | REBUILD | 3 members |
| `CP_BOOTSTRAP.tar.gz` | REBUILD | 16 members (replaced provider archive) |

## Test Results

### Provider Tests (31/31 PASS)

| # | Test | Status |
|---|------|--------|
| 1 | test_reads_api_key_from_env | PASS |
| 2 | test_missing_key_raises_auth_error | PASS |
| 3 | test_default_provider_id | PASS |
| 4 | test_custom_provider_id | PASS |
| 5 | test_implements_llm_provider_protocol | PASS |
| 6 | test_client_created_with_key | PASS |
| 7 | test_no_client_when_key_missing | PASS |
| 8 | test_model_id_in_request | PASS |
| 9 | test_max_tokens_in_request | PASS |
| 10 | test_temperature_in_request | PASS |
| 11 | test_timeout_conversion_ms_to_seconds | PASS |
| 12 | test_default_model_used_when_empty | PASS |
| 13 | test_prompt_as_user_message | PASS |
| 14 | test_basic_text_response | PASS |
| 15 | test_stop_reason_end_turn | PASS |
| 16 | test_stop_reason_max_tokens | PASS |
| 17 | test_stop_reason_tool_use | PASS |
| 18 | test_request_id_from_response | PASS |
| 19 | test_token_counts | PASS |
| 20 | test_response_is_provider_response_subclass | PASS |
| 21 | test_content_blocks_present | PASS |
| 22 | test_content_is_text_only | PASS |
| 23 | test_mixed_blocks_preserved | PASS |
| 24 | test_content_blocks_is_tuple | PASS |
| 25 | test_structured_output_adds_tools | PASS |
| 26 | test_timeout_error | PASS |
| 27 | test_connection_error | PASS |
| 28 | test_429_rate_limited | PASS |
| 29 | test_401_auth_error | PASS |
| 30 | test_400_invalid_request | PASS |
| 31 | test_500_server_error | PASS |

### Regression Tests (40/40 PASS)

| Suite | Count | Status |
|-------|-------|--------|
| test_prompt_router.py | 15/15 | PASS |
| test_followup_3d.py | 13/13 | PASS |
| test_followup_3e.py | 12/12 | PASS |

### Clean-Room Verification

| Check | Result |
|-------|--------|
| CP_BOOTSTRAP.tar.gz members | 16 (3 docs + 13 packages) |
| Packages installed | 13 across 4 layers |
| Gates | 8/8 PASS |
| G0B | 78 files owned, 0 orphans |
| G1 | 11 chains validated |
| G1-COMPLETE | 11 frameworks checked |
| G6 | 3 ledger files, 63 entries |
| Receipts | 13 in HOT/installed/ |
| `import anthropic` in provider | YES |
| `urllib` in provider | NO |
| `external_deps` in manifest | `["anthropic>=0.40.0"]` |
| Import check (installed env) | OK |

## Verification Checklist

- [x] `import anthropic` works (v0.76.0)
- [x] 31 tests pass (test_anthropic_provider.py)
- [x] No `urllib` in anthropic_provider.py
- [x] `import anthropic` in anthropic_provider.py
- [x] Clean-room install: 13 packages, 8/8 gates PASS
- [x] CP_BOOTSTRAP has 16 members
- [x] `external_deps` in manifest.json
- [x] Full regression: 40/40 existing tests pass
- [x] RESULTS_FOLLOWUP_9A.md written

## Key Implementation Notes

- **Catch order matters**: `APITimeoutError` must be caught before `APIConnectionError` because timeout IS-A connection error in the SDK hierarchy.
- **content_blocks are model_dump()**: SDK returns Pydantic v2 model objects; we call `.model_dump()` on each block to get dict representation for the tuple, preserving the same interface as the urllib version.
- **manifest version bumped to 1.1.0**: Reflects the SDK migration while maintaining the same package_id.
- **No changes to provider.py**: The LLMProvider Protocol and ProviderError are owned by PKG-PROMPT-ROUTER-001, untouched.
