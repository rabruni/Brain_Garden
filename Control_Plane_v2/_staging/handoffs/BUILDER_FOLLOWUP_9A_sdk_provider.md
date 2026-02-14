# BUILDER_FOLLOWUP_9A: PKG-ANTHROPIC-PROVIDER-001 — Rewrite to Anthropic SDK

## 1. Mission

Rewrite `PKG-ANTHROPIC-PROVIDER-001` to use the official `anthropic` Python SDK instead of raw `urllib.request`. The current stdlib implementation has SSL certificate failures on macOS (and potentially other platforms where system certs are misconfigured). The SDK handles SSL, streaming, tool use parsing, and API versioning transparently. The locked system (`~/AI_ARCH/_locked_system_flattened/core/api_client.py`) proves this approach works in production.

The kernel (Layers 0-2) stays **stdlib-only**. The SDK is a runtime dependency of this **Layer 3 application package only**.

---

## 2. Critical Constraints

1. **ALL work goes in `Control_Plane_v2/_staging/`**. Nothing written to the conflated repo tree. NOT `CP_2.1/_staging/`.
2. **DTT: Design → Test → Then implement.** Write tests FIRST. Every component gets tests before implementation. No exceptions.
3. **Package everything.** Modified code ships in `_staging/PKG-ANTHROPIC-PROVIDER-001/` with updated manifest.json, SHA256 hashes, same dependencies. Follow existing package patterns.
4. **End-to-end verification.** After building, run the full install chain: extract `CP_BOOTSTRAP.tar.gz` → install all 4 layers → verify YOUR modified package installs. All 8 gates must pass.
5. **No hardcoding.** Every threshold, timeout, retry count, rate limit — all config-driven. This is the #1 lesson from 7 layers of prior art.
6. **No file replacement.** Packages must NEVER overwrite another package's files. Use state-gating instead.
7. **Tar archive format:** Use Python's `tarfile` module with explicit `arcname` — NEVER `tar czf ... -C dir .` (the `./` prefix breaks `load_manifest_from_archive`). See Bug #25/#32 in `memory/bugs_fixed.md`.
8. **Results file.** When finished, write `_staging/RESULTS_FOLLOWUP_9A.md` (see `BUILDER_HANDOFF_STANDARD.md`).
9. **Full regression test.** Run ALL staged package tests (not just yours) and report results.
10. **Baseline snapshot.** Your results file must include a baseline snapshot.

**Task-specific constraints:**

11. **`pip install anthropic` is required.** Run `pip install anthropic` as part of setup. This is a Layer 3 application dependency — the kernel (Layers 0-2) remains stdlib-only. Verify `import anthropic` works before starting.
12. **API key from environment only.** Read `ANTHROPIC_API_KEY` from `os.environ`. Never accept it as a constructor string parameter. Raise `ProviderError(code="AUTH_ERROR")` if the env var is missing.
13. **Do NOT modify `provider.py`.** It is owned by PKG-PROMPT-ROUTER-001. Your `AnthropicResponse` subclass stays in your file.
14. **CP_BOOTSTRAP must be rebuilt.** The final archive must contain 13 packages. Verify the full install chain still works.
15. **Preserve the LLMProvider Protocol interface.** The `send()` method signature MUST NOT change. Same args, same return type (AnthropicResponse, which extends ProviderResponse). The router must not need any changes.
16. **No retries in the provider.** The router's CircuitBreaker handles resilience. The provider is a dumb pipe. Unlike the locked system's `RateLimitedClient`, we do NOT add retry logic here — the router already has it.
17. **Add `external_deps` to manifest.json.** The manifest must declare `"external_deps": ["anthropic>=0.40.0"]` so install tooling knows about the pip requirement.

---

## 3. Architecture / Design

### Before (stdlib — BEING REPLACED)

```
AnthropicProvider
├── urllib.request.Request → POST https://api.anthropic.com/v1/messages
├── urllib.request.urlopen → raw HTTP, manual SSL, manual JSON parsing
├── Manual content block parsing
└── Manual error code mapping (urllib.error.HTTPError → ProviderError)
```

### After (SDK)

```
AnthropicProvider
├── anthropic.Anthropic() → SDK client (handles SSL, HTTP, versioning)
├── client.messages.create() → typed response
├── response.content → list of ContentBlock (text, tool_use)
├── response.usage → InputTokens, OutputTokens
└── SDK exceptions → ProviderError mapping
```

### Provider Class

```python
class AnthropicProvider:
    provider_id: str = "anthropic"
    _client: anthropic.Anthropic     # SDK client (replaces urllib)

    def __init__(self, provider_id="anthropic"):
        self.provider_id = provider_id
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ProviderError(message="...", code="AUTH_ERROR", retryable=False)
        self._client = anthropic.Anthropic(api_key=api_key)

    def send(self, model_id, prompt, max_tokens=4096, temperature=0.0,
             timeout_ms=30000, structured_output=None) -> AnthropicResponse:
        # Build params
        # Call self._client.messages.create(...)
        # Map response to AnthropicResponse
        # Map SDK exceptions to ProviderError
```

### AnthropicResponse (UNCHANGED)

```python
@dataclass(frozen=True)
class AnthropicResponse(ProviderResponse):
    """Extended response preserving content_blocks for tool use."""
    content_blocks: tuple = ()
```

Same as before. `content` = concatenated text, `content_blocks` = raw blocks as tuple of dicts.

### Error Mapping

| SDK Exception | ProviderError Code | Retryable |
|--------------|-------------------|-----------|
| `anthropic.AuthenticationError` | `AUTH_ERROR` | False |
| `anthropic.PermissionDeniedError` | `AUTH_ERROR` | False |
| `anthropic.BadRequestError` | `INVALID_REQUEST` | False |
| `anthropic.RateLimitError` | `RATE_LIMITED` | True |
| `anthropic.InternalServerError` | `SERVER_ERROR` | True |
| `anthropic.APIConnectionError` | `TIMEOUT` | True |
| `anthropic.APITimeoutError` | `TIMEOUT` | True |
| Any other `anthropic.APIStatusError` | `SERVER_ERROR` | True |

### Stop Reason Mapping (UNCHANGED)

```python
STOP_REASON_MAP = {
    "end_turn": "stop",
    "max_tokens": "length",
    "tool_use": "tool_use",
}
```

### Timeout Handling

The SDK accepts `timeout` in seconds (float). Convert `timeout_ms / 1000.0`. Pass via `self._client.messages.create(..., timeout=timeout_s)`.

### Structured Output (UNCHANGED pattern)

When `structured_output` is not None, pass `tools` and `tool_choice` to `messages.create()` — same as before, just as kwargs instead of manual JSON building.

---

## 4. Implementation Steps

### Step 1: Verify SDK is installed
```bash
pip install anthropic>=0.40.0
python3 -c "import anthropic; print(anthropic.__version__)"
```

### Step 2: Update tests (DTT — tests first)

Edit `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/tests/test_anthropic_provider.py`:

- Replace all `@patch("urllib.request.urlopen")` with `@patch("anthropic.Anthropic")` or mock the client
- Mock `client.messages.create()` to return SDK-shaped response objects
- Add new tests:
  - `test_sdk_client_created_with_key`: Verify `anthropic.Anthropic(api_key=...)` is called
  - `test_timeout_passed_as_seconds`: Verify `timeout_ms` converted to seconds and passed to `create()`
  - `test_api_connection_error_maps_to_timeout`: `anthropic.APIConnectionError` → TIMEOUT
  - `test_api_timeout_error_maps_to_timeout`: `anthropic.APITimeoutError` → TIMEOUT
  - `test_rate_limit_error_maps_correctly`: `anthropic.RateLimitError` → RATE_LIMITED
  - `test_permission_denied_maps_to_auth`: `anthropic.PermissionDeniedError` → AUTH_ERROR
- Keep all existing test BEHAVIORS — just change the mock mechanism
- Minimum 28 tests (same count as H9, all behaviors preserved)

### Step 3: Rewrite anthropic_provider.py

Edit `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py`:

1. Remove `import urllib.request`, `import urllib.error`
2. Add `import anthropic`
3. In `__init__`: create `self._client = anthropic.Anthropic(api_key=api_key)`
4. In `send()`:
   - Build kwargs dict for `messages.create()`
   - Call `response = self._client.messages.create(**kwargs)`
   - Extract text: `"".join(b.text for b in response.content if b.type == "text")`
   - Build content_blocks: `tuple({"type": b.type, ...} for b in response.content)` — convert SDK ContentBlock objects to plain dicts for serialization
   - Map `response.stop_reason` via STOP_REASON_MAP
   - Map `response.usage.input_tokens`, `response.usage.output_tokens`
   - Map `response.id` to `request_id`
   - Return `AnthropicResponse(...)`
5. In error handling:
   - Catch `anthropic.AuthenticationError` → ProviderError(AUTH_ERROR)
   - Catch `anthropic.RateLimitError` → ProviderError(RATE_LIMITED)
   - Catch `anthropic.APITimeoutError` → ProviderError(TIMEOUT)
   - Catch `anthropic.APIConnectionError` → ProviderError(TIMEOUT)
   - Catch `anthropic.BadRequestError` → ProviderError(INVALID_REQUEST)
   - Catch `anthropic.APIStatusError` → ProviderError(SERVER_ERROR) as fallback

### Step 4: Update manifest.json

Edit `_staging/PKG-ANTHROPIC-PROVIDER-001/manifest.json`:
- Recompute SHA256 for modified `anthropic_provider.py`
- Recompute SHA256 for modified `test_anthropic_provider.py`
- Add `"external_deps": ["anthropic>=0.40.0"]`
- Keep same package_id, version, dependencies, layer

### Step 5: Rebuild PKG-ANTHROPIC-PROVIDER-001.tar.gz

Use Python `tarfile` module with explicit `arcname`:

```python
import tarfile
from pathlib import Path

pkg_dir = Path("_staging/PKG-ANTHROPIC-PROVIDER-001")
with tarfile.open("_staging/PKG-ANTHROPIC-PROVIDER-001.tar.gz", "w:gz") as tf:
    for full in sorted(pkg_dir.rglob("*")):
        if full.is_file():
            arcname = str(full.relative_to(pkg_dir))
            tf.add(str(full), arcname=arcname)
```

**CRITICAL**: arcname must be `full.relative_to(pkg_dir)` NOT `full.relative_to(pkg_dir.parent)`. The latter produces `PKG-NAME/HOT/...` paths that break install.sh extraction (Bug #32).

### Step 6: Rebuild CP_BOOTSTRAP.tar.gz

Replace the old PKG-ANTHROPIC-PROVIDER-001.tar.gz in CP_BOOTSTRAP:

```python
import tarfile, io
from pathlib import Path

staging = Path("_staging")
old_archive = staging / "CP_BOOTSTRAP.tar.gz"
new_pkg = staging / "PKG-ANTHROPIC-PROVIDER-001.tar.gz"

# Read old archive into memory
members = {}
with tarfile.open(old_archive, "r:gz") as tf:
    for m in tf.getmembers():
        data = tf.extractfile(m)
        members[m.name] = (m, data.read() if data else None)

# Replace the provider package
pkg_data = new_pkg.read_bytes()
info = tarfile.TarInfo(name="packages/PKG-ANTHROPIC-PROVIDER-001.tar.gz")
info.size = len(pkg_data)
members["packages/PKG-ANTHROPIC-PROVIDER-001.tar.gz"] = (info, pkg_data)

# Write new archive
with tarfile.open(old_archive, "w:gz") as tf:
    for name in sorted(members.keys()):
        m, data = members[name]
        if data is not None:
            tf.addfile(m, io.BytesIO(data))
        else:
            tf.addfile(m)
```

### Step 7: Clean-room verification

```bash
TMPDIR=$(mktemp -d)
tar xzf _staging/CP_BOOTSTRAP.tar.gz -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR/cp_test" --dev
# Expect: 13 packages, 8/8 gates PASS
```

### Step 8: Run all tests

```bash
# Your tests
PYTHONPATH=... python3 -m pytest _staging/PKG-ANTHROPIC-PROVIDER-001/HOT/tests/ -v

# Full regression
CONTROL_PLANE_ROOT="$TMPDIR/cp_test" python3 -m pytest _staging/ -v --ignore=<unvalidated>
```

---

## 5. Package Plan

**PKG-ANTHROPIC-PROVIDER-001** (MODIFIED — same package ID, same layer)

| Field | Value |
|-------|-------|
| package_id | PKG-ANTHROPIC-PROVIDER-001 |
| version | 1.0.0 |
| layer | 3 |
| spec_id | SPEC-GATE-001 |
| framework_id | FMWK-000 |
| plane_id | hot |
| dependencies | PKG-PROMPT-ROUTER-001 |
| external_deps | anthropic>=0.40.0 |

Assets (same 2 files, new hashes):

| Path | Classification |
|------|---------------|
| HOT/kernel/anthropic_provider.py | kernel |
| HOT/tests/test_anthropic_provider.py | test |

---

## 6. Test Plan

Minimum 28 tests. All existing behaviors preserved, mock mechanism changed from urllib to SDK.

### Initialization (5 tests)
| # | Test | Validates |
|---|------|-----------|
| 1 | test_reads_api_key_from_env | Key from ANTHROPIC_API_KEY env var |
| 2 | test_missing_key_raises_auth_error | Missing key → ProviderError(AUTH_ERROR) |
| 3 | test_default_provider_id | Default is "anthropic" |
| 4 | test_custom_provider_id | Custom provider_id respected |
| 5 | test_implements_llm_provider_protocol | isinstance(provider, LLMProvider) |

### SDK Client Creation (2 tests)
| # | Test | Validates |
|---|------|-----------|
| 6 | test_sdk_client_created_with_key | anthropic.Anthropic(api_key=...) called |
| 7 | test_sdk_client_not_created_without_key | No client created when key missing |

### Request Building (6 tests)
| # | Test | Validates |
|---|------|-----------|
| 8 | test_model_id_in_request | model_id passed to messages.create() |
| 9 | test_max_tokens_in_request | max_tokens passed |
| 10 | test_temperature_in_request | temperature passed |
| 11 | test_timeout_passed_as_seconds | timeout_ms → seconds conversion |
| 12 | test_default_model_used_when_empty | Empty model_id → default |
| 13 | test_prompt_as_user_message | prompt wrapped in messages=[{"role":"user","content":prompt}] |

### Response Mapping (7 tests)
| # | Test | Validates |
|---|------|-----------|
| 14 | test_basic_text_response | Text content mapped correctly |
| 15 | test_stop_reason_end_turn | end_turn → "stop" |
| 16 | test_stop_reason_max_tokens | max_tokens → "length" |
| 17 | test_stop_reason_tool_use | tool_use → "tool_use" |
| 18 | test_request_id_from_response | response.id → request_id |
| 19 | test_token_counts | usage.input_tokens, output_tokens mapped |
| 20 | test_response_is_provider_response_subclass | isinstance checks |

### Tool Use (4 tests)
| # | Test | Validates |
|---|------|-----------|
| 21 | test_content_blocks_present | content_blocks populated with tool_use |
| 22 | test_content_is_text_only | content = concatenated text blocks only |
| 23 | test_mixed_blocks_preserved | Text + tool_use blocks in content_blocks |
| 24 | test_content_blocks_is_tuple | Immutability (tuple not list) |

### Structured Output (1 test)
| # | Test | Validates |
|---|------|-----------|
| 25 | test_structured_output_adds_tools | tools + tool_choice in create() kwargs |

### Error Handling (6 tests)
| # | Test | Validates |
|---|------|-----------|
| 26 | test_api_timeout_error | APITimeoutError → TIMEOUT, retryable |
| 27 | test_api_connection_error | APIConnectionError → TIMEOUT, retryable |
| 28 | test_rate_limit_error | RateLimitError → RATE_LIMITED, retryable |
| 29 | test_auth_error | AuthenticationError → AUTH_ERROR, not retryable |
| 30 | test_bad_request_error | BadRequestError → INVALID_REQUEST, not retryable |
| 31 | test_server_error | InternalServerError → SERVER_ERROR, retryable |

**Total: 31 tests** (28 original behaviors + 3 new SDK-specific)

---

## 7. Existing Code to Reference

| What | Where | Why |
|------|-------|-----|
| Current provider (BEING REPLACED) | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/anthropic_provider.py` | Understand current structure, keep same interface |
| Current tests (BEING REPLACED) | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/tests/test_anthropic_provider.py` | Keep same test behaviors, change mock mechanism |
| LLMProvider Protocol | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` | Interface contract — DO NOT MODIFY |
| ProviderResponse / ProviderError | `_staging/PKG-PROMPT-ROUTER-001/HOT/kernel/provider.py` | Base classes for response/error |
| Locked system reference | `~/AI_ARCH/_locked_system_flattened/core/api_client.py` | Proven SDK usage pattern (rate limiting, error handling) |
| Locked system requirements | `~/AI_ARCH/_locked_system_flattened/requirements.txt` | `anthropic>=0.18.0` (we use >=0.40.0 for latest) |
| Current manifest | `_staging/PKG-ANTHROPIC-PROVIDER-001/manifest.json` | Update hashes, add external_deps |
| Builder standard | `_staging/BUILDER_HANDOFF_STANDARD.md` | Results file format |
| Bugs list | `memory/bugs_fixed.md` | Tar format bugs (#25, #32), avoid repeating |

---

## 8. End-to-End Verification

```bash
# 1. Verify SDK installed
python3 -c "import anthropic; print(f'SDK version: {anthropic.__version__}')"

# 2. Run provider tests
STAGING="Control_Plane_v2/_staging"
PYTHONPATH="$STAGING/PKG-KERNEL-001/HOT/kernel:$STAGING/PKG-PROMPT-ROUTER-001/HOT/kernel:$STAGING/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel" \
python3 -m pytest "$STAGING/PKG-ANTHROPIC-PROVIDER-001/HOT/tests/test_anthropic_provider.py" -v
# Expected: 31 tests PASS

# 3. Clean-room install
TMPDIR=$(mktemp -d)
tar xzf "$STAGING/CP_BOOTSTRAP.tar.gz" -C "$TMPDIR"
cd "$TMPDIR" && bash install.sh --root "$TMPDIR/cp_test" --dev
# Expected: 13 packages installed, 8/8 gates PASS

# 4. Verify provider file is SDK-based (no urllib)
grep -c "urllib" "$TMPDIR/cp_test/HOT/kernel/anthropic_provider.py"
# Expected: 0

grep -c "import anthropic" "$TMPDIR/cp_test/HOT/kernel/anthropic_provider.py"
# Expected: 1

# 5. Live smoke test (if ANTHROPIC_API_KEY is set)
CONTROL_PLANE_ROOT="$TMPDIR/cp_test" \
PYTHONPATH="$TMPDIR/cp_test/HOT/kernel:$TMPDIR/cp_test/HOT" \
python3 -c "
from anthropic_provider import AnthropicProvider
p = AnthropicProvider()
r = p.send(model_id='claude-sonnet-4-5-20250929', prompt='Say hello', max_tokens=20)
print(f'Response: {r.content}')
print(f'Tokens: {r.input_tokens}+{r.output_tokens}')
"
# Expected: Response text, no SSL errors
```

---

## 9. Files Summary

| File | Location | Action |
|------|----------|--------|
| `anthropic_provider.py` | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/kernel/` | REWRITE (urllib → SDK) |
| `test_anthropic_provider.py` | `_staging/PKG-ANTHROPIC-PROVIDER-001/HOT/tests/` | REWRITE (mock mechanism) |
| `manifest.json` | `_staging/PKG-ANTHROPIC-PROVIDER-001/` | EDIT (new hashes, add external_deps) |
| `PKG-ANTHROPIC-PROVIDER-001.tar.gz` | `_staging/` | REBUILD |
| `CP_BOOTSTRAP.tar.gz` | `_staging/` | REBUILD (replace provider archive) |
| `RESULTS_FOLLOWUP_9A.md` | `_staging/` | CREATE (results file) |

**NOT modified:** `provider.py`, `prompt_router.py`, any Layer 0-2 package, any kernel code.

---

## 10. Design Principles

- **SDK for application, stdlib for kernel.** Layers 0-2 have zero pip dependencies. Layer 3 application packages can use external libraries. The boundary is at the Protocol interface.
- **Provider is a dumb pipe.** No retries, no rate limiting, no caching. The router handles resilience. This is different from the locked system's `RateLimitedClient` — we separate concerns.
- **Content blocks as plain dicts.** Convert SDK ContentBlock objects to plain dicts in `content_blocks`. This keeps the response serializable (JSON-safe) for ledger logging. Don't leak SDK types past the provider boundary.
- **Same interface, different engine.** The `send()` signature is identical. The router doesn't know or care that the implementation changed. If we swap providers again, nothing upstream changes.
- **Fail fast, fail clear.** Every SDK exception maps to a specific ProviderError code. No generic catches. The router's CircuitBreaker needs clear error codes to make decisions.
- **Battle-tested pattern.** The locked system (`api_client.py`) has been in production. We're not inventing — we're adapting a proven approach behind our existing Protocol boundary.
