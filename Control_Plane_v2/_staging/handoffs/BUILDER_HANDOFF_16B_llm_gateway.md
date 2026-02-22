# BUILDER_HANDOFF_16B: LLM Gateway Rename (PKG-LLM-GATEWAY-001)

## 1. Mission

Create `PKG-LLM-GATEWAY-001` -- a mechanical rename of `PromptRouter` to `LLMGateway` with zero functionality change. The routing intelligence was absorbed into HO2 (v2 architecture); what remains is a deterministic pipe (Log->Send->Log->Count). The name should reflect the actual responsibility. After this handoff, `LLMGateway` is the canonical class name, and all existing `PromptRouter` imports continue to work via backward-compatibility aliases.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design -> Test -> Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-LLM-GATEWAY-001/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` -> install all layers -> install YOUR new package. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit -- all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` -- never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_16B.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results.
10. **Baseline snapshot.** Your results file must include a baseline snapshot.

**Task-specific constraints:**

11. **ZERO functionality change.** This is a rename only. No new methods, no changed signatures, no removed functionality, no new features. If the implementation adds or changes behavior, it is wrong.
12. **Backward-compat aliases required.** `PromptRouter = LLMGateway` must exist in `llm_gateway.py`. The shim `prompt_router.py` must re-export everything from `llm_gateway.py` so existing imports work.
13. **PKG-PROMPT-ROUTER-001 is NOT modified.** This is a NEW package that coexists alongside PKG-PROMPT-ROUTER-001. The old package remains as-is for provenance. PKG-LLM-GATEWAY-001 installs its own files to new paths.

---

## 3. Architecture / Design

This is a mechanical rename. The architecture is a 1:1 mapping:

| Original (PKG-PROMPT-ROUTER-001) | New (PKG-LLM-GATEWAY-001) |
|---|---|
| `HOT/kernel/prompt_router.py` | `HOT/kernel/llm_gateway.py` (renamed copy, class: `LLMGateway`) |
| `PromptRouter` class | `LLMGateway` class (+ `PromptRouter = LLMGateway` alias) |
| N/A | `HOT/kernel/prompt_router.py` (thin re-export shim) |

### Rename Mapping

```
prompt_router.py  -->  llm_gateway.py
  PromptRouter    -->  LLMGateway
  (all else identical: PromptRequest, PromptResponse, RouteOutcome,
   CircuitState, CircuitBreaker, CircuitBreakerConfig, RouterConfig)
```

### Shim Pattern

`prompt_router.py` becomes a thin re-export shim:

```python
"""Backward-compatibility shim. Use llm_gateway.py for new code."""
from llm_gateway import *  # noqa: F401,F403
PromptRouter = LLMGateway  # noqa: F405
```

### Alias in llm_gateway.py

At the bottom of `llm_gateway.py`, after the `LLMGateway` class definition:

```python
# Backward-compatibility alias
PromptRouter = LLMGateway
```

### Adversarial Analysis: Rename Strategy

**Hurdles**: Every existing import (`from prompt_router import PromptRouter`) must keep working. The shim pattern ensures backward compatibility. The alias in `llm_gateway.py` ensures code that imports from the new module also gets the old name.

**Too Much**: Adding any new functionality, changing method signatures, or restructuring internals. This is a rename -- zero new features.

**Synthesis**: New package. `llm_gateway.py` is a renamed copy with `LLMGateway` as primary class. `prompt_router.py` is a re-export shim. `PromptRouter = LLMGateway` alias in both files. All existing tests pass with new names.

### CC-3: Package Supersession

PKG-LLM-GATEWAY-001 exists ALONGSIDE PKG-PROMPT-ROUTER-001. Both packages coexist. New code should import from `llm_gateway`. Old imports from `prompt_router` continue to work via the shim. Archival of PKG-PROMPT-ROUTER-001 is a separate future task.

---

## 4. Implementation Steps

### Step 1: Write tests (DTT)

Create `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py` with all tests from the Test Plan (Section 6). Tests use `tmp_path` fixtures and mock providers. No real LLM calls.

### Step 2: Create llm_gateway.py

Copy `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` to `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/llm_gateway.py`.

Make exactly these changes:
1. Update the module docstring: replace "Prompt router" with "LLM Gateway" in the first line.
2. Rename class `PromptRouter` to `LLMGateway` (the class definition and the `from_config_file` return type annotation).
3. Add `PromptRouter = LLMGateway` alias at the bottom of the file.
4. **Change nothing else.** All dataclasses (`PromptRequest`, `PromptResponse`, `CircuitBreakerConfig`, `RouterConfig`), all enums (`RouteOutcome`, `CircuitState`), all methods, all signatures -- identical.

### Step 3: Create prompt_router.py shim

Create `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/prompt_router.py`:

```python
"""Backward-compatibility shim. Use llm_gateway.py for new code."""
from llm_gateway import *  # noqa: F401,F403
PromptRouter = LLMGateway  # noqa: F405
```

### Step 4: Create manifest.json

Create `_staging/PKG-LLM-GATEWAY-001/manifest.json` (see Section 5).

### Step 5: Run tests and verify

```bash
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest _staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py -v
```

### Step 6: Build package archive

Build `PKG-LLM-GATEWAY-001.tar.gz` using Python tarfile with explicit arcname (no `./` prefix).

### Step 7: Full regression test

Run ALL staged package tests and report results.

### Step 8: Write results file

Write `_staging/RESULTS_HANDOFF_16B.md` following the standard format.

---

## 5. Package Plan

### New Package

| Field | Value |
|-------|-------|
| Package ID | `PKG-LLM-GATEWAY-001` |
| Layer | 3 |
| spec_id | `SPEC-GATE-001` |
| framework_id | `FMWK-000` |
| plane_id | `hot` |
| Dependencies | `PKG-KERNEL-001`, `PKG-TOKEN-BUDGETER-001` |
| Supersedes | `PKG-PROMPT-ROUTER-001` (coexists; archival deferred) |

**Assets:**

| Path | Classification |
|------|---------------|
| `HOT/kernel/llm_gateway.py` | kernel |
| `HOT/kernel/prompt_router.py` | kernel (backward-compat shim) |
| `HOT/tests/test_llm_gateway.py` | test |
| `manifest.json` | manifest |

**Manifest template:**

```json
{
  "package_id": "PKG-LLM-GATEWAY-001",
  "version": "1.0.0",
  "schema_version": "1.2",
  "title": "LLM Gateway",
  "description": "LLM Gateway (renamed from PromptRouter). Deterministic send-log-count pipe for all LLM calls. Zero functionality change from PKG-PROMPT-ROUTER-001.",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot",
  "layer": 3,
  "supersedes": "PKG-PROMPT-ROUTER-001",
  "dependencies": [
    "PKG-KERNEL-001",
    "PKG-TOKEN-BUDGETER-001"
  ],
  "assets": [
    {
      "path": "HOT/kernel/llm_gateway.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "kernel"
    },
    {
      "path": "HOT/kernel/prompt_router.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "kernel"
    },
    {
      "path": "HOT/tests/test_llm_gateway.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "test"
    }
  ]
}
```

### Modified Packages

None. PKG-PROMPT-ROUTER-001 is NOT modified. PKG-LLM-GATEWAY-001 is a new package that coexists alongside it.

---

## 6. Test Plan

**File:** `_staging/PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py`

All tests use `tmp_path` for isolated ledger paths. Mock providers only -- no real LLM calls, no API keys.

The test file must add these to `sys.path`:
- `_staging/PKG-KERNEL-001/HOT/kernel` (for `LedgerClient`, `LedgerEntry`)
- `_staging/PKG-LLM-GATEWAY-001/HOT/kernel` (for `LLMGateway`, `PromptRouter` alias)
- `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel` (for `provider.py` -- `MockProvider`, `ProviderResponse`)
- `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel` (for `TokenBudgeter`)

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_llm_gateway_class_exists` | `LLMGateway` is importable from `llm_gateway` module |
| 2 | `test_prompt_router_alias_in_gateway` | `PromptRouter` alias in `llm_gateway` module is the same object as `LLMGateway` |
| 3 | `test_route_method_exists` | `LLMGateway` has a `route()` method |
| 4 | `test_from_config_file_exists` | `LLMGateway` has a `from_config_file()` classmethod |
| 5 | `test_register_provider_exists` | `LLMGateway` has a `register_provider()` method |
| 6 | `test_prompt_request_dataclass` | `PromptRequest` is importable from `llm_gateway` |
| 7 | `test_prompt_response_dataclass` | `PromptResponse` is importable from `llm_gateway` |
| 8 | `test_route_outcome_enum` | `RouteOutcome` is importable from `llm_gateway` with all 4 values |
| 9 | `test_circuit_state_enum` | `CircuitState` is importable from `llm_gateway` |
| 10 | `test_router_config_dataclass` | `RouterConfig` is importable from `llm_gateway` |
| 11 | `test_circuit_breaker_config_dataclass` | `CircuitBreakerConfig` is importable from `llm_gateway` |
| 12 | `test_circuit_breaker_class` | `CircuitBreaker` is importable from `llm_gateway` |
| 13 | `test_route_success` | `LLMGateway.route()` returns `PromptResponse` with `SUCCESS` outcome using `MockProvider` |
| 14 | `test_backward_compat_import_shim` | `from prompt_router import PromptRouter` works via the shim and `PromptRouter is LLMGateway` |
| 15 | `test_backward_compat_route_via_shim` | `PromptRouter` imported from shim can `.route()` successfully |
| 16 | `test_all_exports_present` | All public names from original `prompt_router.py` are accessible from `llm_gateway` |
| 17 | `test_no_api_change_route_signature` | `LLMGateway.route()` accepts `PromptRequest` and returns `PromptResponse` (same signature) |
| 18 | `test_no_api_change_constructor` | `LLMGateway.__init__` accepts same parameters as original `PromptRouter.__init__` |

**18 tests total.** Covers: class rename, aliases, all public exports, backward-compat shim, route success path, constructor/method signatures.

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| prompt_router.py (source) | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` | The file being renamed -- copy this |
| provider.py | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` | MockProvider for testing -- import from here |
| test_prompt_router.py | `_staging/PKG-PROMPT-ROUTER-001/HOT/tests/test_prompt_router.py` | Test patterns to follow |
| PKG-PROMPT-ROUTER-001 manifest | `_staging/PKG-PROMPT-ROUTER-001/manifest.json` | Reference for manifest structure |
| Builder standard | `_staging/handoffs/BUILDER_HANDOFF_STANDARD.md` | Results file format, baseline snapshot format |

---

## 8. End-to-End Verification

```bash
# 1. Run package tests
cd Control_Plane_v2/_staging
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest PKG-LLM-GATEWAY-001/HOT/tests/test_llm_gateway.py -v
# Expected: 18 tests pass

# 2. Verify package archive contents
tar tzf PKG-LLM-GATEWAY-001.tar.gz
# Expected:
#   manifest.json
#   HOT/kernel/llm_gateway.py
#   HOT/kernel/prompt_router.py
#   HOT/tests/test_llm_gateway.py

# 3. Verify LLMGateway class works
python3 -c "
import sys
from pathlib import Path
staging = Path('.')
sys.path.insert(0, str(staging / 'PKG-KERNEL-001' / 'HOT' / 'kernel'))
sys.path.insert(0, str(staging / 'PKG-LLM-GATEWAY-001' / 'HOT' / 'kernel'))
from llm_gateway import LLMGateway, PromptRouter, PromptRequest, PromptResponse
assert PromptRouter is LLMGateway, 'Alias broken'
print('LLMGateway class: OK')
print(f'PromptRouter is LLMGateway: {PromptRouter is LLMGateway}')
print(f'route method: {hasattr(LLMGateway, \"route\")}')
"
# Expected: All assertions pass

# 4. Verify backward-compat shim
python3 -c "
import sys
from pathlib import Path
staging = Path('.')
sys.path.insert(0, str(staging / 'PKG-KERNEL-001' / 'HOT' / 'kernel'))
sys.path.insert(0, str(staging / 'PKG-LLM-GATEWAY-001' / 'HOT' / 'kernel'))
from prompt_router import PromptRouter, PromptRequest, PromptResponse, RouteOutcome
from llm_gateway import LLMGateway
assert PromptRouter is LLMGateway, 'Shim alias broken'
print('Backward-compat shim: OK')
"
# Expected: All assertions pass

# 5. Full regression
CONTROL_PLANE_ROOT="/tmp/test" python3 -m pytest . -v --ignore=PKG-FLOW-RUNNER-001
# Expected: all pass, no new failures
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/` | CREATE (renamed copy of prompt_router.py) |
| `prompt_router.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/kernel/` | CREATE (thin re-export shim) |
| `test_llm_gateway.py` | `_staging/PKG-LLM-GATEWAY-001/HOT/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-LLM-GATEWAY-001/` | CREATE |
| `RESULTS_HANDOFF_16B.md` | `_staging/` | CREATE |

**Not modified:** Any file in PKG-PROMPT-ROUTER-001 or any other existing package.

---

## 10. Design Principles

1. **Zero functionality change.** This is a rename. If you are tempted to improve, refactor, or extend anything -- stop. The entire value of this package is that it changes exactly one thing: the name.
2. **Backward compatibility is non-negotiable.** Every existing `from prompt_router import PromptRouter` must continue to work. The shim and alias pattern ensures this.
3. **New code uses the new name.** HANDOFF-14 (HO1 Executor) and all future packages should import `LLMGateway` from `llm_gateway`. The old name is for backward compat only.
4. **Coexistence, not replacement.** PKG-LLM-GATEWAY-001 lives alongside PKG-PROMPT-ROUTER-001. Both packages remain installable. Archival is a future task.
5. **provider.py is NOT duplicated.** The `LLMProvider` protocol and `MockProvider` remain in PKG-PROMPT-ROUTER-001. They are imported from there -- not copied into this package.
