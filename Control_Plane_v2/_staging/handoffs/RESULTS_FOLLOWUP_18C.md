# RESULTS: FOLLOWUP-18C — Prompt Pack Templates + Template Loading in HO1

**Date:** 2026-02-15
**Branch:** `migration/tier-primary-layout`
**Status:** COMPLETE

---

## Summary

Implemented prompt pack templates and template rendering in HO1, plus fixed Anthropic provider structured_output extraction. This is the belt-and-suspenders fix for the E2E `output_schema_invalid` failure.

### Root Cause
- FMWK-011 §8 designed prompt packs but zero template files existed
- HO1 sent raw `json.dumps(input_ctx)` to the LLM → LLM returned prose, not JSON
- Provider silently dropped tool_use content when `structured_output` forced `tool_choice`

### Fix (Two Enforcement Layers)
1. **Template instruction** (text): Templates instruct LLM "Respond with valid JSON only..."
2. **structured_output** (tool-use): Forces tool_choice → LLM must produce schema-conformant JSON
3. **Provider extraction**: 2-line fix extracts `tool_use[0].input` as content when text is empty

---

## Changes

### Package A: PKG-HO1-EXECUTOR-001 (v1.0.0 → v1.1.0)

| File | Action | Description |
|------|--------|-------------|
| `HO1/prompt_packs/PRM-CLASSIFY-001.txt` | CREATE | Classify template with `{{user_input}}` |
| `HO1/prompt_packs/PRM-SYNTHESIZE-001.txt` | CREATE | Synthesize template with `{{prior_results}}`, `{{user_input}}`, `{{classification}}`, `{{assembled_context}}` |
| `HO1/prompt_packs/PRM-EXECUTE-001.txt` | CREATE | Execute template with `{{user_input}}`, `{{assembled_context}}` |
| `HO1/kernel/ho1_executor.py` | EDIT | Added `_render_template()` helper; updated both `_build_prompt_request()` paths |
| `HO1/contracts/classify.json` | EDIT | Added `structured_output` to boundary |
| `HO1/contracts/synthesize.json` | EDIT | Added `structured_output` to boundary |
| `HO1/contracts/execute.json` | EDIT | Added `structured_output` to boundary |
| `HO1/tests/test_ho1_executor.py` | EDIT | Added 10 template rendering tests |
| `manifest.json` | EDIT | Added 3 prompt_pack assets, updated hashes |

### Package B: PKG-ANTHROPIC-PROVIDER-001 (v1.1.0 → v1.2.0)

| File | Action | Description |
|------|--------|-------------|
| `HOT/kernel/anthropic_provider.py` | EDIT | 2-line fix: extract `tool_use[0].input` as content |
| `HOT/tests/test_anthropic_provider.py` | EDIT | Added 2 structured_output tests |
| `manifest.json` | EDIT | Updated hashes |

---

## Test Results

### Package-Local Tests
- **PKG-HO1-EXECUTOR-001:** 50 passed (40 existing + 10 new)
- **PKG-ANTHROPIC-PROVIDER-001:** 33 passed (31 existing + 2 new)

### Full Regression
```
234 passed in 2.28s
Packages tested: PKG-WORK-ORDER-001, PKG-HO1-EXECUTOR-001, PKG-HO2-SUPERVISOR-001,
  PKG-LLM-GATEWAY-001, PKG-SESSION-HOST-V2-001, PKG-SHELL-001, PKG-ADMIN-001,
  PKG-ANTHROPIC-PROVIDER-001, PKG-TOKEN-BUDGETER-001
```

### Clean-Room Install
```
Packages: 20 total (20 receipts)
Gates: 8 passed, 0 failed
  G0B: PASS — 110 files owned, 0 orphans
  G1: PASS — 18 chains validated
  G1-COMPLETE: PASS — 18 frameworks checked
  G2: PASS
  G3: PASS
  G4: PASS
  G5: PASS
  G6: PASS — 3 ledger files, 90 entries
```

---

## New Tests Added (12)

### HO1 Template Rendering (10)
1. `test_render_template_substitutes_string_var` — {{user_input}} replaced with string value
2. `test_render_template_substitutes_dict_var` — Dict value rendered as json.dumps, not Python repr
3. `test_render_template_substitutes_list_var` — List value rendered as json.dumps
4. `test_render_template_missing_file_falls_back` — No template → json.dumps fallback
5. `test_render_template_unknown_placeholder_preserved` — {{unknown}} stays literal
6. `test_render_template_appends_additional_context` — additional_context appended after render
7. `test_build_prompt_request_uses_template` — Full flow: contract → rendered prompt
8. `test_build_prompt_request_fallback_uses_template` — SimpleNamespace path also renders
9. `test_classify_template_includes_json_instruction` — Template contains JSON instruction
10. `test_synthesize_template_renders_complex_context` — Dict + list variables rendered as JSON

### Anthropic Provider (2)
11. `test_structured_output_extracts_tool_use_content` — tool_use input extracted as content
12. `test_structured_output_text_response_still_works` — text response unchanged

---

## Design Decisions

1. **Template placeholders = contract input_schema keys** — naming contract between HO2 and HO1
2. **json.dumps for non-string values** — Dict/list → `json.dumps(value, indent=2)`, never `str()`
3. **Graceful degradation** — Missing template falls back to `json.dumps(input_ctx)`
4. **Both paths render** — PromptRequest and SimpleNamespace paths both call `_render_template()`
5. **additional_context appends after render** — Tool results loop unchanged
6. **Belt and suspenders** — Templates instruct, structured_output enforces

---

## E2E Smoke Test (Live API)

```
E2E: classify WO (hello) -> template render -> Anthropic API -> structured output

State: completed
Output: {"speech_act": "greeting", "ambiguity": "low"}
Cost: 776 input + 54 output = 830 tokens, 1 LLM call, 2300ms

E2E PASS: classify returned {speech_act, ambiguity} via structured output
```

**Verified from installed tree:**
- prompt_packs directory present at `INSTALL_ROOT/HO1/prompt_packs/` (3 files)
- All 3 contracts have `structured_output` in boundary
- Provider `tool_use[0].input` extraction fix present at line 122
- Template rendering resolves correctly: `{{user_input}}` → "hello", no unresolved placeholders

---

## Archives Rebuilt
- `PKG-HO1-EXECUTOR-001.tar.gz` — rebuilt with 3 new prompt_pack assets
- `PKG-ANTHROPIC-PROVIDER-001.tar.gz` — rebuilt with provider fix
- `CP_BOOTSTRAP.tar.gz` — rebuilt with updated packages (20 packages, 23 entries)
