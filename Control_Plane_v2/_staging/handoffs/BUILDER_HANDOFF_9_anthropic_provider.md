# BUILDER_HANDOFF_9: PKG-ANTHROPIC-PROVIDER-001 — Anthropic API Provider (stdlib)

## 1. Mission

Build `PKG-ANTHROPIC-PROVIDER-001` — a stdlib-only Anthropic API provider that implements the `LLMProvider` Protocol from `provider.py`. Uses `urllib.request` + `json` (no pip dependencies). Extends `ProviderResponse` with a `content_blocks` field to support tool use responses. Add to CP_BOOTSTRAP.tar.gz as a Layer 3 package.

This is the last piece needed to connect the prompt router to a real LLM. After this, the system can boot all the way to the ADMIN agent.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** New code ships as packages in `_staging/PKG-ANTHROPIC-PROVIDER-001/` with manifest.json, SHA256 hashes, proper dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install all layers → verify YOUR new package installs. All gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** `tar czf ... -C dir $(ls dir)` — never `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`). Prefer Python's `tarfile` module with explicit `arcname` (see Bug #25 in MEMORY.md).
8. **Results file.** When finished, write `_staging/RESULTS_HANDOFF_9.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results.
10. **Baseline snapshot.** Your results file must include a baseline snapshot.

**Task-specific constraints:**

11. **ZERO external dependencies.** stdlib only — `urllib.request`, `json`, `os`, `uuid`, `dataclasses`. No pip. No `anthropic` SDK. No `requests`. No `httpx`. This is non-negotiable.
12. **API key from environment.** Read `ANTHROPIC_API_KEY` from `os.environ`. Never accept it as a constructor string parameter (prevents accidental logging). Raise `ProviderError(code="AUTH_ERROR")` if the env var is missing.
13. **Do NOT modify `provider.py`.** It is owned by PKG-PROMPT-ROUTER-001. Instead, subclass `ProviderResponse` (see Architecture below).
14. **CP_BOOTSTRAP must be rebuilt.** The final archive must contain 13 packages (12 existing + this one). Verify the full install chain still works with 13 packages.

---

## 3. Architecture / Design

### Provider Class

```
AnthropicProvider
├── provider_id: str = "anthropic"
├── _api_key: str           (from ANTHROPIC_API_KEY env var)
├── _base_url: str          (default: "https://api.anthropic.com")
├── _api_version: str       (default: "2023-06-01")
├── _default_model: str     (default: "claude-sonnet-4-5-20250929")
│
└── send(model_id, prompt, max_tokens, temperature, timeout_ms, structured_output)
    ├── Build request JSON (Messages API format)
    ├── POST to /v1/messages via urllib.request
    ├── Parse response JSON
    ├── Map to AnthropicResponse (extends ProviderResponse)
    └── Map HTTP errors to ProviderError
```

### AnthropicResponse (extends ProviderResponse)

`ProviderResponse` is a frozen dataclass with `content: str`. Tool use responses from Claude return `content` as an array of blocks (text + tool_use). We can't modify `provider.py`, so we subclass:

```python
@dataclass(frozen=True)
class AnthropicResponse(ProviderResponse):
    """Extended response that preserves structured content blocks for tool use."""
    content_blocks: tuple = ()  # tuple for frozen compatibility
```

- `content` (str) = concatenated text from all `text` blocks (for logging, display, non-tool-use consumers)
- `content_blocks` (tuple of dicts) = raw content blocks from the API response (preserves `tool_use` block structure)
- `finish_reason` = mapped from Anthropic's `stop_reason` ("end_turn" → "stop", "tool_use" → "tool_use", "max_tokens" → "length")

**Why tuple, not list:** `ProviderResponse` is frozen. Frozen dataclasses require hashable fields. Tuple of dicts isn't technically hashable either, but frozen dataclasses don't actually hash fields — they just prevent assignment. Using `tuple` signals immutability intent. If the agent prefers, `field(default=())` works.

**How the flow runner uses this:** When `finish_reason == "tool_use"`, the flow runner checks `isinstance(response, AnthropicResponse)` and reads `response.content_blocks` to find `tool_use` blocks, execute tools, and build the next request.

### HTTP Request Format

```
POST https://api.anthropic.com/v1/messages
Headers:
  x-api-key: <ANTHROPIC_API_KEY>
  anthropic-version: 2023-06-01
  content-type: application/json

Body:
{
  "model": "<model_id>",
  "max_tokens": <max_tokens>,
  "temperature": <temperature>,
  "messages": [{"role": "user", "content": "<prompt>"}]
}
```

If `structured_output` is provided, add it as a tool definition with `tool_choice: {"type": "any"}` to force structured JSON output (this is the standard Anthropic pattern for structured output).

### Error Mapping

| HTTP Status | ProviderError code | retryable |
|------------|-------------------|-----------|
| 401 | `AUTH_ERROR` | false |
| 400 | `INVALID_REQUEST` | false |
| 429 | `RATE_LIMITED` | true |
| 500, 502, 503 | `SERVER_ERROR` | true |
| `urllib.error.URLError` (timeout) | `TIMEOUT` | true |
| `urllib.error.URLError` (other) | `SERVER_ERROR` | true |

### Data Flow

```
PromptRouter.route(request)
  └── provider.send(model_id, prompt, max_tokens, temperature, timeout_ms, structured_output)
        ├── Build JSON body
        ├── urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        ├── urllib.request.urlopen(req, timeout=timeout_ms/1000)
        ├── Parse response: json.loads(response.read())
        ├── Extract text content: "".join(b["text"] for b in blocks if b["type"] == "text")
        ├── Map stop_reason → finish_reason
        └── Return AnthropicResponse(
              content=text_content,
              model=resp["model"],
              input_tokens=resp["usage"]["input_tokens"],
              output_tokens=resp["usage"]["output_tokens"],
              request_id=resp["id"],  # Anthropic returns "msg_xxx" IDs
              provider_id="anthropic",
              finish_reason=mapped_stop_reason,
              content_blocks=tuple(resp["content"])
            )
```

---

## 4. Implementation Steps

### Step 1: Write tests (DTT)

Create `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/tests/test_anthropic_provider.py` with all tests from the Test Plan (Section 6). All tests mock HTTP — no real API calls in the test suite.

**Mocking strategy:** Use `unittest.mock.patch` on `urllib.request.urlopen` to return mock HTTP responses. Build helper functions to create mock Anthropic API responses.

### Step 2: Implement AnthropicProvider

Create `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py`:

```python
"""Anthropic API provider using stdlib urllib (no external dependencies).

Implements the LLMProvider Protocol for the Anthropic Messages API.
API key is read from ANTHROPIC_API_KEY environment variable.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

# Import from installed kernel (available after PKG-PROMPT-ROUTER-001)
from provider import ProviderError, ProviderResponse


@dataclass(frozen=True)
class AnthropicResponse(ProviderResponse):
    """Extended ProviderResponse preserving structured content blocks."""
    content_blocks: tuple = ()


class AnthropicProvider:
    """Anthropic Messages API provider using stdlib urllib."""

    def __init__(
        self,
        provider_id: str = "anthropic",
        base_url: str = "https://api.anthropic.com",
        api_version: str = "2023-06-01",
        default_model: str = "claude-sonnet-4-5-20250929",
    ):
        self.provider_id = provider_id
        self._base_url = base_url
        self._api_version = api_version
        self._default_model = default_model

        # Read API key from environment — never accept as parameter
        self._api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ProviderError(
                message="ANTHROPIC_API_KEY environment variable not set",
                code="AUTH_ERROR",
            )

    def send(
        self,
        model_id: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout_ms: int = 30000,
        structured_output: Optional[dict[str, Any]] = None,
    ) -> AnthropicResponse:
        # ... implementation
```

The implementation should be ~80-100 lines total. Keep it simple. No retries (the router's CircuitBreaker handles that). No streaming. One POST, one response, one mapping.

### Step 3: Create manifest.json

```json
{
  "package_id": "PKG-ANTHROPIC-PROVIDER-001",
  "version": "1.0.0",
  "schema_version": "1.2",
  "title": "Anthropic API Provider",
  "description": "stdlib-only Anthropic Messages API provider implementing LLMProvider Protocol",
  "spec_id": "SPEC-GATE-001",
  "framework_id": "FMWK-000",
  "plane_id": "hot",
  "layer": 3,
  "dependencies": [
    "PKG-PROMPT-ROUTER-001"
  ],
  "assets": [
    {
      "path": "HOT/kernel/anthropic_provider.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "kernel"
    },
    {
      "path": "HOT/tests/test_anthropic_provider.py",
      "sha256": "<COMPUTE_AFTER_WRITING>",
      "classification": "test"
    }
  ]
}
```

Compute SHA256 for each asset after writing, then update the manifest.

### Step 4: Build PKG-ANTHROPIC-PROVIDER-001.tar.gz

Use Python `tarfile` module (not shell `tar`):

```python
import tarfile
from pathlib import Path

pkg_dir = Path("_staging/PKG-ANTHROPIC-PROVIDER-001")
with tarfile.open("_staging/PKG-ANTHROPIC-PROVIDER-001.tar.gz", "w:gz") as tf:
    for f in sorted(pkg_dir.rglob("*")):
        if f.is_file():
            tf.add(str(f), arcname=str(f.relative_to(pkg_dir)))
```

**Critical:** `arcname=str(f.relative_to(pkg_dir))` — NOT `relative_to(pkg_dir.parent)`. The latter produces `PKG-NAME/HOT/...` paths that break extraction (Bug #32).

### Step 5: Update install.sh

Add `PKG-ANTHROPIC-PROVIDER-001` to the Layer 3 install sequence in `install.sh`. It goes AFTER PKG-PROMPT-ROUTER-001 (since it depends on provider.py).

The Layer 3 section in install.sh has a `LAYER3_BUILTIN` array. Add `PKG-ANTHROPIC-PROVIDER-001` to it, positioned after PKG-PROMPT-ROUTER-001.

### Step 6: Rebuild CP_BOOTSTRAP.tar.gz

Rebuild using Python `tarfile` (not shell tar — Bug #25):

The archive must contain:
- `README.md`, `INSTALL.md`, `install.sh` (top level)
- `packages/` directory with 13 .tar.gz archives

Verify: `tar tzf CP_BOOTSTRAP.tar.gz | wc -l` should show 16 members (3 docs + 13 packages).

### Step 7: Clean-room verification

```bash
TESTDIR=$(mktemp -d)
INSTALLDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$INSTALLDIR"
tar xzf _staging/CP_BOOTSTRAP.tar.gz -C "$TESTDIR"
cd "$TESTDIR"
bash install.sh --root "$INSTALLDIR" --dev
```

Expected: 13 packages installed, 8/8 gates PASS.

### Step 8: Run full regression tests + write results

Run all staged tests. Write `RESULTS_HANDOFF_9.md`.

---

## 5. Package Plan

| Field | Value |
|-------|-------|
| Package ID | `PKG-ANTHROPIC-PROVIDER-001` |
| Layer | 3 |
| spec_id | `SPEC-GATE-001` |
| framework_id | `FMWK-000` |
| plane_id | `hot` |
| Dependencies | `PKG-PROMPT-ROUTER-001` |
| Assets | `HOT/kernel/anthropic_provider.py` (kernel), `HOT/tests/test_anthropic_provider.py` (test) |

---

## 6. Test Plan

**File:** `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/tests/test_anthropic_provider.py`

All tests mock HTTP via `unittest.mock.patch("urllib.request.urlopen")`. No real API calls.

### Helper: `mock_anthropic_response(content_blocks, model, usage, stop_reason)`
Returns a mock HTTP response object with `.read()` returning JSON-encoded Anthropic API response.

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_init_reads_api_key_from_env` | Constructor reads `ANTHROPIC_API_KEY` from `os.environ` |
| 2 | `test_init_missing_api_key_raises_auth_error` | Raises `ProviderError(code="AUTH_ERROR")` when env var missing |
| 3 | `test_provider_id_default` | `provider_id` defaults to `"anthropic"` |
| 4 | `test_provider_id_custom` | `provider_id` can be overridden |
| 5 | `test_implements_protocol` | `isinstance(provider, LLMProvider)` is True |
| 6 | `test_send_basic_text_response` | Simple prompt → `AnthropicResponse` with correct content, model, tokens |
| 7 | `test_send_passes_model_id` | `model_id` appears in the HTTP request body |
| 8 | `test_send_passes_max_tokens` | `max_tokens` appears in the HTTP request body |
| 9 | `test_send_passes_temperature` | `temperature` appears in the HTTP request body |
| 10 | `test_send_maps_stop_reason_end_turn` | Anthropic `"end_turn"` → `finish_reason="stop"` |
| 11 | `test_send_maps_stop_reason_max_tokens` | Anthropic `"max_tokens"` → `finish_reason="length"` |
| 12 | `test_send_maps_stop_reason_tool_use` | Anthropic `"tool_use"` → `finish_reason="tool_use"` |
| 13 | `test_send_tool_use_response_has_content_blocks` | Response with tool_use block → `content_blocks` contains the block |
| 14 | `test_send_tool_use_content_is_text_only` | `content` field = concatenated text blocks (tool_use blocks excluded) |
| 15 | `test_send_mixed_content_blocks` | Response with text + tool_use blocks → content has text, content_blocks has all |
| 16 | `test_send_structured_output_adds_tool` | `structured_output` dict → request body includes `tools` and `tool_choice` |
| 17 | `test_send_timeout_raises_provider_error` | `urllib.error.URLError` with timeout → `ProviderError(code="TIMEOUT", retryable=True)` |
| 18 | `test_send_rate_limited_429` | HTTP 429 → `ProviderError(code="RATE_LIMITED", retryable=True)` |
| 19 | `test_send_auth_error_401` | HTTP 401 → `ProviderError(code="AUTH_ERROR", retryable=False)` |
| 20 | `test_send_server_error_500` | HTTP 500 → `ProviderError(code="SERVER_ERROR", retryable=True)` |
| 21 | `test_send_invalid_request_400` | HTTP 400 → `ProviderError(code="INVALID_REQUEST", retryable=False)` |
| 22 | `test_send_request_id_from_api` | `request_id` comes from Anthropic's `id` field (e.g., `"msg_xxx"`) |
| 23 | `test_send_input_output_tokens` | `input_tokens` and `output_tokens` mapped from `usage` |
| 24 | `test_response_is_provider_response_subclass` | `isinstance(response, ProviderResponse)` is True |
| 25 | `test_send_timeout_ms_converted_to_seconds` | `timeout_ms=5000` → `urlopen(..., timeout=5.0)` |
| 26 | `test_content_blocks_is_tuple` | `content_blocks` is a tuple (not list) — frozen dataclass compatibility |
| 27 | `test_send_default_model` | When `model_id` is empty/None, uses `default_model` from constructor |
| 28 | `test_headers_correct` | Request has `x-api-key`, `anthropic-version`, `content-type` headers |

**28 tests.** Covers: init, protocol compliance, request building, response mapping, error handling, tool use, structured output, edge cases.

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| LLMProvider Protocol + ProviderResponse | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` | The interface you're implementing + the dataclass you're extending |
| MockProvider | Same file | Pattern to follow for send() method signature |
| PromptRouter.route() | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/prompt_router.py` | Understand how the router calls provider.send() |
| Router tests | `_staging/PKG-PROMPT-ROUTER-001/HOT/tests/test_prompt_router.py` | Test patterns, mock patterns |
| Package manifest | `_staging/PKG-PROMPT-ROUTER-001/manifest.json` | Manifest format to follow |
| Package install | `_staging/PKG-KERNEL-001/HOT/scripts/package_install.py` | Understand how packages get installed |
| install.sh | `_staging/install.sh` | Where to add the new package in the Layer 3 sequence |
| Token budgeter | `_staging/PKG-TOKEN-BUDGETER-001/HOT/kernel/token_budgeter.py` | Understand budget integration (router calls this, not you) |
| Builder standard | `_staging/BUILDER_HANDOFF_STANDARD.md` | Results file format, baseline snapshot format |

---

## 8. End-to-End Verification

```bash
# 1. Verify package archive
tar tzf _staging/PKG-ANTHROPIC-PROVIDER-001.tar.gz
# Expected:
#   manifest.json
#   HOT/kernel/anthropic_provider.py
#   HOT/tests/test_anthropic_provider.py

# 2. Verify CP_BOOTSTRAP contents
tar tzf _staging/CP_BOOTSTRAP.tar.gz | sort
# Expected: 16 members (README.md, INSTALL.md, install.sh + packages/ with 13 archives)
# New entry: packages/PKG-ANTHROPIC-PROVIDER-001.tar.gz

# 3. Clean-room install
TESTDIR=$(mktemp -d)
INSTALLDIR=$(mktemp -d)
export CONTROL_PLANE_ROOT="$INSTALLDIR"
tar xzf Control_Plane_v2/_staging/CP_BOOTSTRAP.tar.gz -C "$TESTDIR"
cd "$TESTDIR" && bash install.sh --root "$INSTALLDIR" --dev
# Expected: 13 packages installed, 8/8 gates PASS

# 4. Verify provider is installed
ls "$INSTALLDIR/HOT/kernel/anthropic_provider.py"
# Expected: file exists

# 5. Verify provider can be imported (without API key — just import check)
cd "$INSTALLDIR"
python3 -c "
import sys; sys.path.insert(0, 'HOT/kernel'); sys.path.insert(0, 'HOT/scripts')
from anthropic_provider import AnthropicProvider, AnthropicResponse
from provider import ProviderResponse
print('AnthropicResponse is ProviderResponse subclass:', issubclass(AnthropicResponse, ProviderResponse))
print('OK: provider module imports clean')
"
# Expected: True, OK

# 6. Gate check
python3 "$INSTALLDIR/HOT/scripts/gate_check.py" --root "$INSTALLDIR" --all
# Expected: 8/8 gates PASS

# 7. Run package tests (mocked — no API key needed)
cd "$INSTALLDIR"
CONTROL_PLANE_ROOT="$INSTALLDIR" python3 -m pytest HOT/tests/test_anthropic_provider.py -v
# Expected: 28 pass

# 8. Run full regression
CONTROL_PLANE_ROOT="$INSTALLDIR" python3 -m pytest HOT/tests/ -v
# Expected: all pass, no new failures
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `anthropic_provider.py` | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/` | CREATE |
| `test_anthropic_provider.py` | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/tests/` | CREATE |
| `manifest.json` | `_staging/PKG-ANTHROPIC-PROVIDER-001/` | CREATE |
| `PKG-ANTHROPIC-PROVIDER-001.tar.gz` | `_staging/` | CREATE |
| `install.sh` | `_staging/` | MODIFY (add to Layer 3 sequence) |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (13 packages) |
| `RESULTS_HANDOFF_9.md` | `_staging/` | CREATE |

**Not modified:** `provider.py`, `prompt_router.py`, `token_budgeter.py`, any other existing package. New file only.

---

## 10. Design Principles

1. **stdlib only.** No pip dependencies. `urllib.request` + `json` + `os` + `dataclasses`. If it's not in the Python 3.10 standard library, don't use it.
2. **API key from environment only.** Never accept keys as constructor parameters. Never log keys. `os.environ.get("ANTHROPIC_API_KEY")`.
3. **Extend, don't replace.** `AnthropicResponse` subclasses `ProviderResponse` — all existing code that expects `ProviderResponse` works unchanged. The `content_blocks` field is additive.
4. **No retries.** The router has a CircuitBreaker. The provider is a dumb pipe. Send once, return or raise.
5. **Tool use is structural, not magical.** When Claude returns tool_use blocks, preserve them in `content_blocks`. Set `finish_reason="tool_use"`. Let the flow runner handle the loop. The provider doesn't execute tools.
6. **Fail loud.** Missing API key → immediate `ProviderError`. Bad response → immediate `ProviderError`. Never silently return empty/partial results.

---

## Agent Prompt

```
You are a builder agent for the Control Plane v2 project. Your task is defined in a handoff document.

**YOUR IDENTITY — print this FIRST before doing anything else:**
> **Agent: HANDOFF-9** — PKG-ANTHROPIC-PROVIDER-001: stdlib Anthropic API provider for prompt router

This identifies you in the user's terminal. Always print your identity line as your very first output.

**Read this file FIRST — it is your complete specification:**
`Control_Plane_v2/_staging/BUILDER_HANDOFF_9_anthropic_provider.md`

**Mandatory rules:**
1. ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.
2. DTT: Design → Test → Then implement. Write tests FIRST.
3. Tar archive format: use Python tarfile module with explicit arcname (NEVER shell tar with `./` prefix).
4. End-to-end verification: clean-room install with 13 packages, 8/8 gates PASS.
5. When finished, write your results to `Control_Plane_v2/_staging/RESULTS_HANDOFF_9.md` following the results file format in BUILDER_HANDOFF_STANDARD.md.

**Before writing ANY code, answer these 10 questions to confirm your understanding:**

1. What package are you building and what layer does it install at?
2. What external dependencies does this package use? (Hint: there is a specific, non-negotiable answer.)
3. Where does the Anthropic API key come from? How do you handle a missing key?
4. What HTTP endpoint do you POST to, and what 3 headers are required?
5. provider.py is owned by PKG-PROMPT-ROUTER-001. How do you add `content_blocks` to the response without modifying provider.py?
6. What does `content` (str) contain vs `content_blocks` (tuple) when the response includes tool_use blocks?
7. Map these Anthropic stop_reasons to finish_reason values: "end_turn", "max_tokens", "tool_use".
8. Map these HTTP status codes to ProviderError codes: 401, 429, 500. Which are retryable?
9. How many tests are in the test plan, and do any of them call the real Anthropic API?
10. After building your package, what must CP_BOOTSTRAP.tar.gz contain? (Count: docs + packages)

**STOP AFTER ANSWERING.** Do NOT proceed to implementation until the user reviews your answers and explicitly tells you to go ahead.
```

### Expected Answers (for reviewer)

1. PKG-ANTHROPIC-PROVIDER-001, Layer 3.
2. NONE. Zero external dependencies. stdlib only (urllib.request, json, os, dataclasses). No pip.
3. `os.environ.get("ANTHROPIC_API_KEY")`. Missing → raise `ProviderError(code="AUTH_ERROR")` immediately in `__init__`.
4. `POST https://api.anthropic.com/v1/messages`. Headers: `x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json`.
5. Subclass: `class AnthropicResponse(ProviderResponse)` with `content_blocks: tuple = ()`. It IS a ProviderResponse (inheritance), so it satisfies the return type.
6. `content` = concatenated text from text blocks only (e.g., `"Let me read that file."`). `content_blocks` = full tuple of all blocks including tool_use blocks.
7. `"end_turn"` → `"stop"`, `"max_tokens"` → `"length"`, `"tool_use"` → `"tool_use"`.
8. 401 → `AUTH_ERROR` (not retryable). 429 → `RATE_LIMITED` (retryable). 500 → `SERVER_ERROR` (retryable).
9. 28 tests. Zero real API calls — all mock `urllib.request.urlopen`.
10. 16 members: 3 docs (README.md, INSTALL.md, install.sh) + 13 packages in `packages/` directory.
